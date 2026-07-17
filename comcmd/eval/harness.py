"""The evaluation gate: does multi-agent actually beat a single-agent baseline?

STRATEGY.md §5.2 (and the multi-agent-failure literature) require that a
multi-agent design be *promoted only when measured to beat* a single-agent
baseline on task success — without unacceptable cost, latency, or policy
regressions. This harness runs both variants over a scenario set, measures
success / cost (worker invocations) / latency / policy-denials, and returns a
promotion verdict. Adding agents that don't win here is theater, and the gate
says so.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from comcmd.compile.compiler import compile_company
from comcmd.gateway.gate import Gateway
from comcmd.kernel.executor import Executor
from comcmd.kernel.ledger import Ledger
from comcmd.kernel.records import EventType
from comcmd.kernel.workflow import WorkflowRunner
from comcmd.spec.models import CompanySpec
from comcmd.workers.native import NativeWorker


class _CountingWorker:
    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def run(self, envelope):
        self.calls += 1
        return self._inner.run(envelope)


def _matches(artifacts: dict[str, dict], expected: dict) -> bool:
    """A run succeeds if some produced step artifact satisfies all expected pairs."""
    for art in artifacts.values():
        if isinstance(art, dict) and all(art.get(k) == v for k, v in expected.items()):
            return True
    return False


@dataclass
class VariantMetrics:
    workflow: str
    scenarios: int
    successes: int
    cost: int = 0            # total worker invocations
    latency_s: float = 0.0   # total wall-clock
    policy_denies: int = 0

    @property
    def success_rate(self) -> float:
        return round(self.successes / self.scenarios, 3) if self.scenarios else 0.0


@dataclass
class EvalReport:
    baseline: VariantMetrics
    variant: VariantMetrics
    promote: bool
    reasons: list[str] = field(default_factory=list)


def _run_one(spec: CompanySpec, revision, workflow: str, skills, handlers,
             inputs: dict) -> tuple[dict, int, int]:
    ledger = Ledger(":memory:")
    gateway = Gateway(ledger, {a.id: a for a in spec.actions})
    executor = Executor(ledger, dict(handlers))
    worker = _CountingWorker(NativeWorker(skills=skills))
    runner = WorkflowRunner(revision, ledger, worker, gateway, executor)
    handle = runner.start(workflow, inputs=inputs)
    denies = sum(1 for se in ledger.read(revision.company_name)
                 if se.event.type == EventType.execution_receipt
                 and se.event.payload.get("decision") == "deny")
    return handle.artifacts, worker.calls, denies


def _measure(spec, revision, workflow, skills, handlers, scenarios) -> VariantMetrics:
    m = VariantMetrics(workflow=workflow, scenarios=len(scenarios), successes=0)
    for sc in scenarios:
        t0 = time.perf_counter()
        artifacts, calls, denies = _run_one(spec, revision, workflow, skills,
                                             handlers, sc.get("inputs", {}))
        m.latency_s += time.perf_counter() - t0
        m.cost += calls
        m.policy_denies += denies
        if _matches(artifacts, sc.get("expected", {})):
            m.successes += 1
    m.latency_s = round(m.latency_s, 4)
    return m


def evaluate(spec: CompanySpec, *, baseline: str, variant: str, scenarios: list[dict],
             skills: dict, handlers: dict | None = None,
             max_cost_ratio: float = 6.0) -> EvalReport:
    """Compare a single-agent baseline workflow vs a multi-agent variant."""
    revision = compile_company(spec).raise_if_failed()
    handlers = handlers or {}
    base = _measure(spec, revision, baseline, skills, handlers, scenarios)
    var = _measure(spec, revision, variant, skills, handlers, scenarios)

    reasons: list[str] = []
    beats_success = var.success_rate > base.success_rate
    no_new_denies = var.policy_denies <= base.policy_denies
    cost_ratio = (var.cost / base.cost) if base.cost else float("inf")
    within_cost = cost_ratio <= max_cost_ratio

    if not beats_success:
        reasons.append(f"variant success {var.success_rate} does not beat baseline "
                       f"{base.success_rate}")
    else:
        reasons.append(f"variant success {var.success_rate} > baseline "
                       f"{base.success_rate}")
    if not no_new_denies:
        reasons.append(f"variant introduces policy denials "
                       f"({var.policy_denies} > {base.policy_denies})")
    if not within_cost:
        reasons.append(f"variant cost ratio {round(cost_ratio, 2)}x exceeds "
                       f"{max_cost_ratio}x budget")
    else:
        reasons.append(f"cost {round(cost_ratio, 2)}x baseline")

    promote = beats_success and no_new_denies and within_cost
    return EvalReport(baseline=base, variant=var, promote=promote, reasons=reasons)
