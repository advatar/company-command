"""ActionIntent — a worker's *request* to cause an effect.

Emitting an intent is not authority. The gateway alone authorizes and executes.
The intent's canonical digest binds the exact significant fields (tool, args,
target, amount, environment, audience) so an approval can be pinned one-to-one
to what was actually requested — the anti-TOCTOU primitive.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from comcmd.ids import digest


class ActionIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    company: str
    task_id: str
    step_id: str
    requested_by: str          # principal / role that proposed it
    action_id: str             # references a compiled Action policy
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    # significant, human-meaningful fields surfaced on the approval screen and
    # included verbatim in the digest.
    target: str | None = None
    amount: float | None = None
    environment: str | None = None
    audience: str | None = None

    def canonical(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    @property
    def action_digest(self) -> str:
        return digest(self.canonical())
