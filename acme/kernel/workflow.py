"""Deterministic workflow runner with crash-resume.

Phase 0 in-process implementation of the durable seam that DBOS fills in
Phase 1. Its one non-negotiable property is the Phase 0 exit gate: *a process
can crash at every step and resume without duplicating a durable effect.*

We get that by making the event log authoritative. A step is executed at most
once: before running step S, the runner asks the ledger whether a
``step_succeeded`` event for (task_id, S) already exists; if so it replays the
recorded artifact instead of re-running. Steps run in dependency (``needs``)
order. A ``humanGate`` step routes through the gateway and, absent a verified
approval, parks the task in WAITING_FOR_HUMAN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from acme.gateway.gate import Gateway
from acme.kernel.ledger import Ledger
from acme.kernel.records import CompanyRevision, Event, EventType, TaskState
from acme.ids import content_id
from acme.workers.api import TaskEnvelope, Worker, WorkerResult


class WorkflowError(Exception):
    pass


@dataclass
class TaskHandle:
    company: str
    task_id: str
    workflow_id: str
    state: TaskState = TaskState.READY
    artifacts: dict[str, Any] = field(default_factory=dict)
    waiting_on: dict | None = None


class WorkflowRunner:
    def __init__(self, revision: CompanyRevision, ledger: Ledger,
                 worker: Worker, gateway: Gateway):
        self._rev = revision
        self._ledger = ledger
        self._worker = worker
        self._gateway = gateway
        self._workflows = {w["id"]: w for w in revision.compiled.get("workflows", [])}
        self._roles = {r["id"]: r for r in revision.compiled.get("roles", [])}

    # -- public API ----------------------------------------------------------

    def start(self, workflow_id: str, inputs: dict | None = None) -> TaskHandle:
        if workflow_id not in self._workflows:
            raise WorkflowError(f"unknown workflow {workflow_id!r}")
        task_id = content_id("task", {
            "rev": self._rev.revision_id,
            "wf": workflow_id,
            "inputs": inputs or {},
        })
        # task_created is idempotent: only emit if not already present.
        if not self._completed_steps(task_id) and not self._task_exists(task_id):
            self._emit(EventType.task_created, task_id,
                       {"workflow": workflow_id, "inputs": inputs or {}})
        return self._drive(TaskHandle(self._rev.company_name, task_id, workflow_id),
                           inputs or {})

    def resume(self, task_id: str, workflow_id: str,
               inputs: dict | None = None) -> TaskHandle:
        handle = TaskHandle(self._rev.company_name, task_id, workflow_id)
        # rebuild artifacts already produced
        for step_id, artifact in self._recorded_artifacts(task_id).items():
            handle.artifacts[step_id] = artifact
        return self._drive(handle, inputs or {})

    # -- engine --------------------------------------------------------------

    def _drive(self, handle: TaskHandle, inputs: dict) -> TaskHandle:
        wf = self._workflows[handle.workflow_id]
        steps = wf["steps"]
        done = self._completed_steps(handle.task_id)

        for step in self._in_dependency_order(steps):
            sid = step["id"]
            if sid in done:
                handle.artifacts.setdefault(sid, self._recorded_artifacts(
                    handle.task_id).get(sid))
                continue

            if step.get("type") == "humanGate":
                outcome = self._run_human_gate(handle, step)
                if outcome.state == TaskState.WAITING_FOR_HUMAN:
                    handle.state = TaskState.WAITING_FOR_HUMAN
                    handle.waiting_on = outcome.waiting_on
                    self._set_state(handle)
                    return handle
                done.add(sid)
                continue

            # work step
            self._emit(EventType.step_started, handle.task_id, {"step": sid})
            result = self._run_work_step(handle, step, inputs)
            if result.status == "error":
                handle.state = TaskState.FAILED_RETRYABLE
                self._set_state(handle)
                raise WorkflowError(f"step {sid} failed: {result.usage}")
            artifact = result.artifact or {}
            self._emit(EventType.step_succeeded, handle.task_id,
                       {"step": sid, "artifact": artifact})
            handle.artifacts[sid] = artifact
            done.add(sid)

        handle.state = TaskState.SUCCEEDED
        self._set_state(handle)
        return handle

    def _run_work_step(self, handle: TaskHandle, step: dict, inputs: dict) -> WorkerResult:
        role_id = step.get("runAs")
        role = self._roles.get(role_id, {})
        envelope = TaskEnvelope(
            company=handle.company,
            task_id=handle.task_id,
            step_id=step["id"],
            role=role_id or "",
            model_profile=role.get("modelProfile"),
            inputs={**inputs, "_upstream": {n: handle.artifacts.get(n)
                                            for n in step.get("needs", [])}},
            allowed_tools=tuple(role.get("tools", {}).get("allow", [])),
        )
        result = self._worker.run(envelope)
        # Any intent a worker emits must clear the gateway; none auto-executes.
        for intent in result.intents:
            self._gateway.decide(intent)
        return result

    @dataclass
    class _GateResult:
        state: TaskState
        waiting_on: dict | None = None

    def _run_human_gate(self, handle: TaskHandle, step: dict) -> "WorkflowRunner._GateResult":
        # A humanGate parks the task; the actual authorization happens when an
        # approval assertion arrives (Phase 1). Phase 0: deny-by-default -> wait.
        req = {"step": step["id"], "policy": step.get("policy")}
        self._emit(EventType.approval_requested, handle.task_id, req)
        return WorkflowRunner._GateResult(TaskState.WAITING_FOR_HUMAN, waiting_on=req)

    # -- ledger reconstruction ----------------------------------------------

    def _events(self, task_id: str) -> list[Event]:
        return [se.event for se in self._ledger.read(self._rev.company_name)
                if se.event.task_id == task_id]

    def _task_exists(self, task_id: str) -> bool:
        return any(e.type == EventType.task_created for e in self._events(task_id))

    def _completed_steps(self, task_id: str) -> set[str]:
        return {e.payload["step"] for e in self._events(task_id)
                if e.type == EventType.step_succeeded}

    def _recorded_artifacts(self, task_id: str) -> dict[str, Any]:
        return {e.payload["step"]: e.payload.get("artifact")
                for e in self._events(task_id)
                if e.type == EventType.step_succeeded}

    def _in_dependency_order(self, steps: list[dict]) -> list[dict]:
        by_id = {s["id"]: s for s in steps}
        ordered: list[dict] = []
        seen: set[str] = set()

        def visit(sid: str, stack: tuple[str, ...]) -> None:
            if sid in seen:
                return
            if sid in stack:
                raise WorkflowError(f"cycle at runtime: {' -> '.join(stack + (sid,))}")
            for dep in by_id[sid].get("needs", []):
                visit(dep, stack + (sid,))
            seen.add(sid)
            ordered.append(by_id[sid])

        for s in steps:
            visit(s["id"], ())
        return ordered

    def _emit(self, etype: EventType, task_id: str, payload: dict) -> None:
        self._ledger.append(Event(type=etype, company=self._rev.company_name,
                                  task_id=task_id, payload=payload))

    def _set_state(self, handle: TaskHandle) -> None:
        self._emit(EventType.task_state_changed, handle.task_id,
                   {"state": handle.state.value})
