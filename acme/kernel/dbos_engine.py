"""DBOS durable execution engine — layer 2 of the ADR-001 durability upgrade.

The Postgres ledger (layer 1) makes the *event log* durable. DBOS adds the
durable *workflow primitives* the in-process runner lacks: step-level
checkpoint/memoization (a completed step is never re-run on resume), durable
queues (enqueued work survives restart), and automatic step retries.

A company's work steps run as DBOS steps inside a DBOS workflow keyed by the
Acme task id, so re-submitting the same task resumes from the last checkpoint
instead of repeating effects. Business events are still appended to the Acme
ledger from inside each step, so the audit trail and the durable execution state
stay consistent.

DBOS is a process-wide singleton and its decorated functions must be defined at
import time, so step dispatch goes through module-level registries the engine
populates before launch. Enabled only when a Postgres DSN is provided; the
in-process runner remains the default for tests and single-node use.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from dbos import DBOS, DBOSConfig, Queue, SetWorkflowID

# step dispatch tables, keyed by (company, step_id); populated before launch
_SKILLS: dict[tuple[str, str], Callable[[], dict[str, Any]]] = {}
_LEDGER_EMIT: dict[str, Callable[[str, dict], None]] = {}


# Steps are retried on transient failure. This is safe because Acme work steps
# are required to be idempotent (read-only; side effects go through the gateway
# as ActionIntents, never performed in the step body).
@DBOS.step(retries_allowed=True, max_attempts=3)
def _run_step(company: str, task_id: str, step_id: str) -> dict[str, Any]:
    skill = _SKILLS.get((company, step_id))
    if skill is None:
        raise KeyError(f"no skill registered for {company}/{step_id}")
    artifact = skill() or {}
    emit = _LEDGER_EMIT.get(company)
    if emit is not None:
        emit(step_id, artifact)
    return artifact


@DBOS.workflow()
def _run_pipeline(company: str, task_id: str, step_ids: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for sid in step_ids:
        out[sid] = _run_step(company, task_id, sid)
    return out


class DbosEngine:
    """Durable execution of a company's work-step pipeline on Postgres via DBOS."""

    def __init__(self, dsn: str, *, name: str = "acme", quiet: bool = True):
        if quiet:
            logging.getLogger("dbos").setLevel(logging.WARNING)
        DBOS(config=DBOSConfig(name=name, database_url=dsn))
        DBOS.launch()
        self._queue = Queue("acme-pipeline")

    def register(self, company: str, skills: dict[str, Callable[[], dict]],
                 ledger_emit: Callable[[str, dict], None] | None = None) -> None:
        for step_id, fn in skills.items():
            _SKILLS[(company, step_id)] = fn
        if ledger_emit is not None:
            _LEDGER_EMIT[company] = ledger_emit

    def run(self, company: str, task_id: str, step_ids: list[str]) -> dict[str, Any]:
        """Run the pipeline durably; re-running the same task_id resumes."""
        with SetWorkflowID(task_id):
            return _run_pipeline(company, task_id, step_ids)

    def enqueue(self, company: str, task_id: str, step_ids: list[str]):
        """Durably enqueue a pipeline run; returns a DBOS workflow handle."""
        with SetWorkflowID(task_id):
            return self._queue.enqueue(_run_pipeline, company, task_id, step_ids)

    def steps_of(self, task_id: str) -> list[str]:
        return [s.function_name for s in DBOS.list_workflow_steps(task_id)]

    def shutdown(self) -> None:
        DBOS.destroy()
