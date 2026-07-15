"""Structured logging for Acme library code.

Library modules log via ``get_logger(__name__)``; the CLI configures handlers.
Never log secrets — challenges, assertions, capability material, or private
keys. Log identifiers (task ids, action digests, tiers, decisions) instead.
"""

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def configure(level: str | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    lvl = (level or os.environ.get("ACME_LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=getattr(logging, lvl, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )
    # DBOS is chatty; keep it at WARNING unless explicitly raised.
    logging.getLogger("dbos").setLevel(
        getattr(logging, os.environ.get("ACME_DBOS_LOG_LEVEL", "WARNING"), logging.WARNING))
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name if name.startswith("acme") else f"acme.{name}")
