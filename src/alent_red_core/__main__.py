import asyncio
import argparse
from .common import Logger
from .alent_red import AlentRed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="alent-red-core",
        description="ALENT.RED Core — gRPC server for AI agent orchestration.",
    )
    parser.add_argument("--host", required=True, help="Host address to bind the gRPC server.")
    parser.add_argument(
        "--port", required=True, type=int, help="Port number to bind the gRPC server."
    )
    parser.add_argument(
        "--sqlite-path", required=True, dest="sqlite_path", help="Path to the SQLite database file."
    )
    parser.add_argument(
        "--blob-path", required=True, dest="blob_path", help="Path to the blob storage directory."
    )
    parser.add_argument(
        "--encryption-key",
        required=True,
        dest="encryption_key",
        help="AES-256 encryption key for blob storage.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        dest="log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO).",
    )
    parser.add_argument(
        "--log-format",
        default="console",
        dest="log_format",
        choices=["console", "json"],
        help="Log format (default: console).",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    Logger.init(args.log_level, args.log_format)
    logger = Logger.get_logger("main")

    alent_red = AlentRed(
        sqlite_path=args.sqlite_path,
        blob_path=args.blob_path,
        encryption_key=args.encryption_key,
    )

    try:
        logger.info("application_starting")
        await alent_red.start(host=args.host, port=args.port)
    except KeyboardInterrupt:
        logger.info("shutdown_signal_received")
        await alent_red.stop()
        logger.info("application_stopped")


if __name__ == "__main__":
    asyncio.run(main())
