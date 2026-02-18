"""Logging setup."""

import logging
import sys
from pathlib import Path
from typing import Any


def setup_logging(config: dict[str, Any]) -> None:
    """Configure structured logging."""
    level = getattr(logging, config.get("level", "INFO").upper())

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    handlers = [console]
    log_file = config.get("file")
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers)
