from typing import Any
from sqlalchemy import TypeDecorator, JSON
from pydantic import TypeAdapter


class ModelJSON(TypeDecorator[object]):
    """SQLAlchemy type for Pydantic models and typed collections stored as JSON."""

    impl = JSON
    cache_ok = True

    def __init__(self, pydantic_type: object):
        """Initialize with Pydantic model type or union.

        Args:
            pydantic_type: The Pydantic model class or union type to serialize/deserialize.
        """
        super().__init__()
        self.pydantic_type = pydantic_type
        self._type_adapter: TypeAdapter[Any] = TypeAdapter(pydantic_type)

    def process_bind_param(
        self, value: object | None, dialect: object
    ) -> dict[str, Any] | list[Any] | None:
        """Convert Pydantic value to a JSON-serializable dict or list for storage.

        Args:
            value: Pydantic model instance or None.
            dialect: SQLAlchemy dialect.

        Returns:
            JSON-serializable dict or list, or None.
        """
        if value is None:
            return None
        result = self._type_adapter.dump_python(value, mode="json")
        return result if isinstance(result, (dict, list)) else None

    def process_result_value(
        self, value: dict[str, Any] | list[Any] | None, dialect: object
    ) -> object | None:
        """Convert a JSON dict or list to the Pydantic value.

        Args:
            value: JSON dict or list from database or None.
            dialect: SQLAlchemy dialect.

        Returns:
            Pydantic model instance or None.
        """
        if value is None:
            return None
        result: object = self._type_adapter.validate_python(value)
        return result
