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
from acme.gateway.intents import ActionIntent
from acme.kernel.executor import Executor
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
                 worker: Worker, gateway: Gateway, executor: Executor | None = None,
                 durable_engine=None):
        self._rev = revision
        self._ledger = ledger
        self._worker = worker
        self._gateway = gateway
        self._executor = executor
        # When set, work steps run durably-memoized on Postgres via DBOS.
        self._durable = durable_engine
        self._workflows = {w["id"]: w for w in revision.compiled.get("workflows", [])}
        self._roles = {r["id"]: r for r in revision.compiled.get("roles", [])}
        self._actions = {a["id"]: a for a in revision.compiled.get("actions", [])}

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

        if self._durable is not None:
            # Durable-memoized execution over Postgres. Work steps are read-only
            # (side effects go through human gates), so only status+artifact are
            # checkpointed; intents are a human-gate concern, not a work step.
            def thunk() -> dict:
                r = self._worker.run(envelope)
                return {"status": r.status, "artifact": r.artifact or {}}
            d = self._durable.run_step(handle.task_id, step["id"], thunk)
            return WorkerResult(status=d["status"], artifact=d["artifact"])

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
        # A humanGate opens a gateway approval and parks the task. Authorization
        # happens when approve_step() receives a verified assertion.
        intent = self._gate_intent(handle, step)
        outcome = self._gateway.decide(intent)  # opens approval (require_approval)
        waiting = {
            "step": step["id"],
            "policy": step.get("policy"),
            "intent_digest": intent.action_digest,
            "approval": outcome.approval_request,
        }
        return WorkflowRunner._GateResult(TaskState.WAITING_FOR_HUMAN, waiting_on=waiting)

    def _gate_intent(self, handle: TaskHandle, step: dict) -> ActionIntent:
        """Deterministically build the ActionIntent a humanGate authorizes.

        Must be identical at park time and approve time so the action digest
        (and thus the bound approval challenge) is stable.
        """
        policy = step.get("policy")
        action = self._actions.get(policy, {})
        return ActionIntent(
            company=handle.company,
            task_id=handle.task_id,
            step_id=step["id"],
            requested_by=f"workflow:{handle.workflow_id}",
            action_id=policy,
            tool=action.get("tool", ""),
            target=handle.task_id,
            args={"gate": step["id"]},
        )

    def approve_step(self, task_id: str, workflow_id: str, step_id: str,
                     assertion: dict) -> TaskHandle:
        """Submit one approver's assertion for a parked humanGate.

        On reaching quorum the gateway mints a capability, the executor performs
        the effect exactly once, the gate step is recorded succeeded, and the
        task is driven to completion. Below quorum the task stays parked.
        """
        handle = self.resume(task_id, workflow_id)
        wf = self._workflows[workflow_id]
        step = next((s for s in wf["steps"] if s["id"] == step_id), None)
        if step is None or step.get("type") != "humanGate":
            raise WorkflowError(f"{step_id!r} is not a humanGate of {workflow_id!r}")

        intent = self._gate_intent(handle, step)
        outcome = self._gateway.submit_approval(intent, assertion)
        if outcome.decision != "authorized":
            handle.state = TaskState.WAITING_FOR_HUMAN
            handle.waiting_on = {"step": step_id, "reason": outcome.reason,
                                 "approval": outcome.approval_request}
            return handle

        # Authorized: perform the effect exactly once through the executor.
        if self._executor is not None and outcome.capability is not None:
            result = self._executor.execute(outcome.capability, intent)
            self._emit(EventType.execution_receipt, task_id,
                       {"step": step_id, "executed": result.executed,
                        "duplicate": result.duplicate})
        self._emit(EventType.step_succeeded, task_id,
                   {"step": step_id, "artifact": {"authorized": True}})
        # Drive any remaining steps to completion.
        return self.resume(task_id, workflow_id)

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
