import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncIterator
from sqlalchemy import event, inspect, Connection, Table, UniqueConstraint
from sqlalchemy.engine import Inspector
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.schema import CreateColumn, CreateIndex
from sqlmodel import SQLModel
from ..common import Logger
from .stores import (
    PreferenceStore,
    ProviderStore,
    LlmModelStore,
    AgentStore,
    BrickStore,
    GatewayStore,
    ConversationStore,
    MessageStore,
)


class Database:
    """Manages database connection and session lifecycle."""

    def __init__(self, sqlite_path: str):
        """Initialize database with given path.

        Args:
            sqlite_path: Path to SQLite database file.
        """
        self._sqlite_path = sqlite_path
        self._engine: AsyncEngine = create_async_engine(
            f"sqlite+aiosqlite:///{sqlite_path}",
            echo=False,
        )
        event.listen(
            self._engine.sync_engine,
            "connect",
            Database._enable_sqlite_foreign_keys,
        )
        self._session_maker = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._logger = Logger.get_logger("database.database")
        self.preferences = PreferenceStore(self)
        self.providers = ProviderStore(self)
        self.llm_models = LlmModelStore(self)
        self.agents = AgentStore(self)
        self.bricks = BrickStore(self)
        self.gateways = GatewayStore(self)
        self.conversations = ConversationStore(self)
        self.messages = MessageStore(self)

    async def run(self) -> None:
        """Create missing tables and reconcile the schema of existing ones."""
        async with self._engine.begin() as connection:
            await connection.run_sync(self._ensure_schema)
        self._logger.info("database_started", sqlite_path=self._sqlite_path)

    async def stop(self) -> None:
        """Close database connections and dispose of engine."""
        await self._engine.dispose()
        self._logger.info("database_stopped", sqlite_path=self._sqlite_path)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide async session context manager.

        Yields:
            AsyncSession for database operations.
        """
        session = self._session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @staticmethod
    def _enable_sqlite_foreign_keys(
        dbapi_connection: sqlite3.Connection, _connection_record: object
    ) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def _ensure_schema(self, connection: Connection) -> None:
        """Create missing tables and reconcile the schema of existing ones (additive only).

        First creates any missing tables and their indexes. Then, for tables that
        already existed before this run, adds any new columns, unique constraints,
        and indexes the models declare but the live database is missing. New columns
        must be nullable or have a default, since existing rows must remain valid.

        Args:
            connection: Active synchronous connection inside the engine transaction.
        """
        self._logger.debug("ensure_schema_started")

        inspector = inspect(connection)
        existing_table_names = set(inspector.get_table_names())

        SQLModel.metadata.create_all(connection)

        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_table_names:
                continue
            self._add_missing_columns(connection, inspector, table.name, table)
            self._add_missing_unique_constraints(connection, inspector, table.name, table)
            self._add_missing_indexes(connection, inspector, table.name, table)

        self._logger.debug("ensure_schema_completed")

    def _add_missing_columns(
        self, connection: Connection, inspector: Inspector, table_name: str, table: Table
    ) -> None:
        existing_column_names = {column["name"] for column in inspector.get_columns(table_name)}

        for column in table.columns:
            if column.name in existing_column_names:
                continue
            column_definition = CreateColumn(column).compile(dialect=sqlite_dialect())
            connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")
            self._logger.info("schema_column_added", table=table_name, column=column.name)

    def _add_missing_unique_constraints(
        self, connection: Connection, inspector: Inspector, table_name: str, table: Table
    ) -> None:
        existing_index_names = {index["name"] for index in inspector.get_indexes(table_name)}

        for constraint in table.constraints:
            if not isinstance(constraint, UniqueConstraint):
                continue
            if constraint.name is None or constraint.name in existing_index_names:
                continue
            column_names = ", ".join(column.name for column in constraint.columns)
            connection.exec_driver_sql(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {constraint.name} "
                f"ON {table_name} ({column_names})"
            )
            self._logger.info(
                "schema_unique_constraint_added", table=table_name, constraint=constraint.name
            )

    def _add_missing_indexes(
        self, connection: Connection, inspector: Inspector, table_name: str, table: Table
    ) -> None:
        existing_index_names = {index["name"] for index in inspector.get_indexes(table_name)}

        for index in table.indexes:
            if index.name is None or index.name in existing_index_names:
                continue
            index_definition = CreateIndex(index, if_not_exists=True).compile(
                dialect=sqlite_dialect()
            )
            connection.exec_driver_sql(str(index_definition))
            self._logger.info("schema_index_added", table=table_name, index=index.name)
