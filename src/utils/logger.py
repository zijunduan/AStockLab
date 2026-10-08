from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from src.utils.paths import PROJECT_ROOT, ensure_runtime_directories


_CONFIGURED = False


def configure_logging(log_dir: str | Path | None = None):
    global _CONFIGURED
    if _CONFIGURED:
        return logger
    ensure_runtime_directories()
    directory = Path(log_dir) if log_dir else PROJECT_ROOT / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    logger.remove()
    fmt = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {name}:{function}:{line} | {level} | {message}"
    logger.add(sys.stderr, level="INFO", format=fmt, colorize=False)
    logger.add(directory / "app.log", level="INFO", rotation="10 MB", retention="30 days", encoding="utf-8", format=fmt)
    logger.add(directory / "data.log", level="INFO", filter=lambda r: r["extra"].get("channel") == "data", rotation="10 MB", retention="60 days", encoding="utf-8", format=fmt)
    logger.add(directory / "model.log", level="INFO", filter=lambda r: r["extra"].get("channel") == "model", rotation="10 MB", retention="60 days", encoding="utf-8", format=fmt)
    logger.add(directory / "error.log", level="ERROR", rotation="10 MB", retention="90 days", encoding="utf-8", format=fmt)
    _CONFIGURED = True
    return logger


def get_logger(channel: str = "app"):
    configure_logging()
    return logger.bind(channel=channel)

