import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import grpc
import pytest

from alent_red_core import AlentRed
from alent_red_core.common import Logger

from .config import TestConfig, load_test_config
from .helpers import find_free_port, generate_encryption_key


@pytest.fixture(scope="session")
def test_config() -> TestConfig:
    """Load the test configuration from tests/config.yml once per session.

    Returns:
        Parsed and validated test configuration.
    """
    return load_test_config()


@pytest.fixture(autouse=True)
def init_logger() -> None:
    """Initialize the global Logger before each test.

    The server depends on the Logger being initialized; without it, structlog
    emits garbled output. CLI does this in `__main__.py`, but tests bypass it.
    """
    Logger.init(log_level="DEBUG", log_format="console")


@pytest.fixture
async def server(tmp_path: Path, test_config: TestConfig) -> AsyncIterator[int]:
    """Spin up a fresh server for the test.

    Each test gets its own SQLite DB, blob folder, encryption key, and a
    random free port. The server runs as a background task and is stopped
    on teardown. If the server crashes before becoming ready, the crash is
    surfaced instead of being silently lost.

    Args:
        tmp_path: pytest-provided per-test temp directory.
        test_config: Loaded test configuration (provides readiness timeout).

    Yields:
        The port the server is listening on.
    """
    port = find_free_port()
    blob_path = tmp_path / "blob"
    blob_path.mkdir()

    alent_red = AlentRed(
        sqlite_path=str(tmp_path / "test.db"),
        blob_path=str(blob_path),
        encryption_key=generate_encryption_key(),
    )

    server_task = asyncio.create_task(alent_red.start(host="127.0.0.1", port=port))

    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as readiness_channel:
            readiness_task = asyncio.create_task(readiness_channel.channel_ready())
            done, _pending = await asyncio.wait(
                {readiness_task, server_task},
                return_when=asyncio.FIRST_COMPLETED,
                timeout=test_config.timeouts.server_readiness_seconds,
            )

            if server_task in done:
                # Server died before becoming ready — surface the original exception.
                readiness_task.cancel()
                await server_task

            if readiness_task not in done:
                # Neither completed within the timeout.
                readiness_task.cancel()
                server_task.cancel()
                raise TimeoutError(
                    f"Server failed to become ready within "
                    f"{test_config.timeouts.server_readiness_seconds}s"
                )
    except BaseException:
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass
        raise

    yield port

    await alent_red.stop()
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


@pytest.fixture
async def channel(server: int) -> AsyncIterator[grpc.aio.Channel]:
    """Open a gRPC channel to the test server.

    Args:
        server: Port the server is bound to (from the `server` fixture).

    Yields:
        An async gRPC channel ready for stubs to use.
    """
    async with grpc.aio.insecure_channel(f"127.0.0.1:{server}") as channel:
        yield channel
