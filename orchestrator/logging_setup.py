"""
orchestrator.logging_setup
=============================

Single, centralized logging setup for AEOS.

No logging architecture existed anywhere in the repository before this
phase (only an empty, git-ignored `logs/` directory reserved for future
use). This module is intentionally the ONE place logging is configured.
Future phases/adapters should call `get_logger(__name__)` rather than
calling `logging.basicConfig` or creating new handlers themselves, to
avoid duplicate logging setups.

Configuration:
    Reads LOG_LEVEL from the environment (already declared in
    .env.example) and defaults to "INFO" if unset or invalid.

    Logs to stderr always, and additionally to logs/aeos.log if the
    `logs/` directory exists (it is git-ignored and created on demand
    only when logging is first configured, matching the "no hidden
    state" principle -- the location is documented, not implicit).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_CONFIGURED = False
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "aeos.log"
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _resolve_level() -> int:
    raw = os.environ.get("LOG_LEVEL", "INFO").upper().strip()
    if raw not in _VALID_LEVELS:
        raw = "INFO"
    return getattr(logging, raw)


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = _resolve_level()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    root = logging.getLogger("aeos")
    root.setLevel(level)
    root.propagate = False

    if not root.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

        try:
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError:
            # Filesystem may be read-only in some environments (e.g. CI).
            # Stream logging alone is sufficient; do not fail startup over it.
            pass

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger under the shared 'aeos' root logger.

    Example:
        from orchestrator.logging_setup import get_logger
        logger = get_logger(__name__)
        logger.info("orchestrator started")
    """
    _configure_root()
    return logging.getLogger(f"aeos.{name}")
