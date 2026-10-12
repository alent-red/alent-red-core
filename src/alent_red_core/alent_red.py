from . import __version__
from .common import Logger
from .database import Database
from .blob import BlobStorage
from .server import Server
from .seeds import PreferenceSetup
from .looper import Looper
from .gateways import GatewayManager


class AlentRed:
    """Top-level orchestrator for the ALENT.RED core system."""

    def __init__(self, sqlite_path: str, blob_path: str, encryption_key: str) -> None:
        self._logger = Logger.get_logger("alent_red")
        self._database = Database(sqlite_path=sqlite_path)
        self._blob = BlobStorage(encryption_key=encryption_key, folder_path=blob_path)
        self._looper = Looper(database=self._database, blob=self._blob)
        self._gateways = GatewayManager(
            looper=self._looper, database=self._database, blob=self._blob
        )
        self._server = Server(
            version=__version__,
            database=self._database,
            blob=self._blob,
            looper=self._looper,
            gateways=self._gateways,
        )

    async def start(self, host: str, port: int) -> None:
        """Start the ALENT.RED core system.

        Args:
            host: Host address to bind the gRPC server.
            port: Port number to bind the gRPC server.
        """
        await self._database.run()
        await PreferenceSetup.run(database=self._database)
        await self._looper.setup()
        await self._gateways.setup()
        await self._server.run(host=host, port=port, enable_reflection=True)

    async def stop(self) -> None:
        """Stop the ALENT.RED core system."""
        await self._server.stop()
        await self._gateways.clean()
        await self._looper.clean()
        await self._database.stop()
