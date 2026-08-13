"""Rotating file log in logs/ next to the project root."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: str, log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "agent.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.addHandler(handler)
    # also echo to console when run in the foreground
    console = logging.StreamHandler()
    console.setFormatter(handler.formatter)
    root.addHandler(console)
