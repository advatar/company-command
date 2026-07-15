"""Environment-driven settings.

Production configuration comes from the environment, not code. Absence of a
database URL means single-node in-process execution (fine for dev/CI);
presence flips Acme to durable Postgres + DBOS execution. Nothing here logs or
prints secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _model_map(raw: str | None) -> dict[str, str]:
    # "profile=model,profile2=model2"
    out: dict[str, str] = {}
    for pair in (raw or "").split(","):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
    return out


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None      # postgresql://... -> durable; None -> in-process
    rp_id: str = "localhost"             # WebAuthn relying-party id
    rp_origin: str = "https://localhost" # WebAuthn expected origin
    model_url: str | None = None         # OpenAI-compatible endpoint
    model_key: str | None = None
    model_map: dict[str, str] = field(default_factory=dict)  # profile -> model id
    ledger_url: str | None = None        # overrides database_url for the ledger

    @property
    def durable(self) -> bool:
        return bool(self.database_url)

    @property
    def effective_ledger_url(self) -> str | None:
        return self.ledger_url or self.database_url

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Settings":
        e = env if env is not None else os.environ
        return cls(
            database_url=e.get("ACME_DATABASE_URL") or None,
            rp_id=e.get("ACME_RP_ID", "localhost"),
            rp_origin=e.get("ACME_RP_ORIGIN", "https://localhost"),
            model_url=e.get("ACME_MODEL_URL") or None,
            model_key=e.get("ACME_MODEL_KEY") or None,
            model_map=_model_map(e.get("ACME_MODEL_MAP")),
            ledger_url=e.get("ACME_LEDGER_URL") or None,
        )
