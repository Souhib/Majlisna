from sys import stderr

from loguru import logger


def configure_logger(log_level: str = "DEBUG", serialize: bool = False) -> None:
    """Configure structured logging with Loguru.

    Args:
        log_level: Minimum log level to display.
        serialize: Whether to serialize logs as JSON (for production).
    """
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "{extra[request_id]}{extra[user_id]}{extra[game_id]}"
        "<level>{message}</level>"
    )

    logger.configure(extra={"request_id": "", "user_id": "", "game_id": ""})

    logger.add(
        stderr,
        format=log_format,
        level=log_level.upper(),
        serialize=serialize,
        backtrace=False,
        diagnose=False,
        filter=lambda record: "ipg" in record["file"].path,
    )
