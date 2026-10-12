import logging
import sys
from typing import Optional, cast
import structlog
from structlog.typing import FilteringBoundLogger, Processor


class Logger:
    """Centralized logging management with runtime configuration."""

    _config = {"log_level": "INFO", "log_format": "console"}

    @staticmethod
    def init(log_level: str, log_format: str) -> None:
        """Initialize logging configuration.

        Args:
            log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            log_format: Output format ('console' or 'json').
        """
        Logger._config["log_level"] = log_level
        Logger._config["log_format"] = log_format
        Logger._configure()

    @staticmethod
    def update(log_level: Optional[str] = None, log_format: Optional[str] = None) -> None:
        """Update logging configuration at runtime.

        Args:
            log_level: New log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            log_format: New output format ('console' or 'json').
        """
        if log_level:
            Logger._config["log_level"] = log_level
        if log_format:
            Logger._config["log_format"] = log_format
        Logger._configure()

    @staticmethod
    def get_logger(name: str) -> FilteringBoundLogger:
        """Get a logger instance.

        Args:
            name: Logger name (typically module name).

        Returns:
            Configured structlog logger instance.
        """
        return cast(FilteringBoundLogger, structlog.get_logger(name))

    @staticmethod
    def _configure() -> None:
        """Configure structlog based on current settings."""
        log_level = Logger._config["log_level"].upper()
        log_format = Logger._config["log_format"]

        logging.root.setLevel(log_level)

        processors: list[Processor] = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
        ]

        if log_format == "json":
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.extend([structlog.dev.ConsoleRenderer(colors=True)])

        structlog.configure(
            processors=processors,
            wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
            cache_logger_on_first_use=False,
        )
