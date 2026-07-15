"""CompanyPack — a company as a portable bundle.

A CompanyPack is a directory with a declarative `company.yaml` and an optional
`pack.py` that supplies the company's deterministic domain logic:

  - `SKILLS`: dict[step_id -> Worker skill]  (what a work step actually does)
  - `HANDLERS`: dict[tool -> executor handler]  (what an authorized effect does)

This is the "instantiate any company" unit and the extraction shape the
MandamusCo Company-in-a-Box plan calls for: the governance core is generic; the
per-company domain (skills + handlers + the manifest) lives in the pack. Domain
logic belongs in packs, never in the kernel.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

from acme.compile.compiler import compile_company
from acme.gateway.gate import Gateway
from acme.gateway.verifier import ApprovalVerifier
from acme.kernel import make_ledger
from acme.kernel.executor import Executor, ToolHandler
from acme.kernel.records import CompanyRevision
from acme.kernel.workflow import WorkflowRunner
from acme.spec.loader import load_company_spec
from acme.spec.models import CompanySpec
from acme.workers.native import NativeWorker, Skill


@dataclass
class CompanyPack:
    directory: Path
    spec: CompanySpec
    skills: dict[str, Skill] = field(default_factory=dict)
    handlers: dict[str, ToolHandler] = field(default_factory=dict)
    scenarios: list[dict] = field(default_factory=list)  # for the evaluation gate


def load_pack(directory: str | Path) -> CompanyPack:
    directory = Path(directory)
    spec = load_company_spec(directory)
    skills: dict[str, Skill] = {}
    handlers: dict[str, ToolHandler] = {}
    scenarios: list[dict] = []

    pack_py = directory / "pack.py"
    if pack_py.exists():
        mod_name = f"acme_pack_{spec.metadata.name.replace('-', '_')}"
        module_spec = importlib.util.spec_from_file_location(mod_name, pack_py)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        skills = dict(getattr(module, "SKILLS", {}))
        handlers = dict(getattr(module, "HANDLERS", {}))
        scenarios = list(getattr(module, "SCENARIOS", []))

    return CompanyPack(directory=directory, spec=spec, skills=skills,
                       handlers=handlers, scenarios=scenarios)


@dataclass
class RunContext:
    runner: WorkflowRunner
    gateway: Gateway
    ledger: object
    revision: CompanyRevision


def build_runner(pack: CompanyPack, *, ledger_url: str | None = None,
                 verifier: ApprovalVerifier | None = None,
                 durable_engine=None) -> RunContext:
    """Compile a pack and wire runner -> gateway -> worker(skills) -> executor(handlers).

    Pass ``durable_engine`` (a launched DbosEngine) to run work steps
    durably-memoized on Postgres; pass a Postgres ``ledger_url`` to make the
    event log durable. With neither, execution is in-process (dev/CI default).
    """
    revision = compile_company(pack.spec).raise_if_failed()
    ledger = make_ledger(ledger_url)
    actions = {a.id: a for a in pack.spec.actions}
    gateway = Gateway(ledger, actions, verifier=verifier)
    executor = Executor(ledger, dict(pack.handlers))
    worker = NativeWorker(skills=pack.skills)
    runner = WorkflowRunner(revision, ledger, worker, gateway, executor,
                            durable_engine=durable_engine)
    return RunContext(runner=runner, gateway=gateway, ledger=ledger, revision=revision)
