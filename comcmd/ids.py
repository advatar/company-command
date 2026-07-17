"""Deterministic identity, canonical JSON, and content digests.

Determinism is a requirement, not a convenience: content-addressed revisions,
hash-chained events, and idempotency keys all depend on a single canonical byte
representation. Everything that gets hashed goes through ``canonical_bytes``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Return a stable JSON string: sorted keys, no insignificant whitespace.

    Rejects NaN/Infinity so a digest can never depend on a non-portable float.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def digest(value: Any) -> str:
    """Content digest of any JSON-serializable value, as ``sha256:<hex>``."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def content_id(prefix: str, value: Any) -> str:
    """A short, deterministic, content-addressed id like ``rev_1f3a…`` (12 hex)."""
    h = hashlib.sha256(canonical_bytes(value)).hexdigest()[:12]
    return f"{prefix}_{h}"
