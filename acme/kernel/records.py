"""Durable records — the minimum Phase 0 schema.

These are the authoritative business state. Chat is not state; sessions are
replaceable execution details. Everything consequential resolves back to these.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from acme.ids import content_id, digest


class CompanyRevision(BaseModel):
    """An immutable, content-addressed compiled company.

    The id is derived from the canonical compiled body, so the same spec always
    compiles to the same revision id and any change produces a new one.
    """

    model_config = ConfigDict(frozen=True)

    revision_id: str
    company_name: str
    revision: int
    spec_digest: str
    compiled: dict[str, Any]  # normalized, reference-checked company body

    @staticmethod
    def make(company_name: str, revision: int, spec_canonical: dict[str, Any],
             compiled: dict[str, Any]) -> "CompanyRevision":
        body = {
            "company_name": company_name,
            "revision": revision,
            "compiled": compiled,
        }
        return CompanyRevision(
            revision_id=content_id("rev", body),
            company_name=company_name,
            revision=revision,
            spec_digest=digest(spec_canonical),
            compiled=compiled,
        )


class TaskState(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    COMMITTING = "COMMITTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    COMPENSATING = "COMPENSATING"
    CANCELLED = "CANCELLED"


class EventType(str, Enum):
    company_compiled = "company_compiled"
    task_created = "task_created"
    task_state_changed = "task_state_changed"
    step_started = "step_started"
    step_succeeded = "step_succeeded"
    artifact_written = "artifact_written"
    action_intent = "action_intent"
    policy_decision = "policy_decision"
    approval_requested = "approval_requested"
    approval_resolved = "approval_resolved"
    execution_receipt = "execution_receipt"


class Event(BaseModel):
    """One append-only fact. Ledger seals it into a per-company hash chain."""

    model_config = ConfigDict(frozen=True)

    type: EventType
    company: str
    task_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionReceipt(BaseModel):
    """Evidence that a gated action was authorized and executed (or refused)."""

    model_config = ConfigDict(frozen=True)

    intent_digest: str
    decision: str          # auto | require_approval | deny | executed | refused
    tier: str              # A0..A4
    capability_id: str | None = None
    reason: str = ""
