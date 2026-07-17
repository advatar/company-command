"""CompanySpec — the portable, declarative definition of a company.

This is the "instantiate any company" primitive. It is intentionally data:
roles are bundles of skills/tools/scopes/budgets/escalation, not simulated
employees. The compiler (comcmd.compile.compiler) turns a validated spec into an
immutable CompanyRevision and enforces the default-deny rules; the model layer
here only enforces *shape*, not *authority*.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    # Unknown keys are a spec error, not silently ignored: a typo'd field must
    # not degrade authority (e.g. an ignored "approval" block).
    model_config = ConfigDict(extra="forbid")


class Risk(str, Enum):
    """Risk class of an action; maps to an assurance tier in gateway policy."""

    observe = "observe"                # A0
    bounded_internal = "bounded_internal"  # A1
    external_reversible = "external_reversible"  # A2
    consequential = "consequential"    # A3
    prohibited = "prohibited"          # A4


class KPI(_Base):
    id: str
    target: float
    period: str = "quarter"


class Mission(_Base):
    statement: str
    owner: str
    kpis: list[KPI] = Field(default_factory=list)


class ModelProfile(_Base):
    """A capability profile, not a vendor model name (provider neutrality)."""

    capability: str
    max_cost_per_task: float | None = Field(default=None, alias="maxCostPerTask")
    fallback: str = "defer"  # defer | retry_then_defer | ...
    worker_preference: list[str] = Field(default_factory=list, alias="workerPreference")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ToolGrant(_Base):
    allow: list[str] = Field(default_factory=list)


class Budget(_Base):
    monthly: float | None = None


class Escalation(_Base):
    uncertainty_above: float | None = Field(default=None, alias="uncertaintyAbove")
    to: str | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Role(_Base):
    id: str
    purpose: str
    skills: list[str] = Field(default_factory=list)
    model_profile: str | None = Field(default=None, alias="modelProfile")
    tools: ToolGrant = Field(default_factory=ToolGrant)
    data_scopes: list[str] = Field(default_factory=list, alias="dataScopes")
    may_delegate_to: list[str] = Field(default_factory=list, alias="mayDelegateTo")
    # write_authority: does this role emit action intents that cause effects?
    write_authority: bool = Field(default=False, alias="writeAuthority")
    budget: Budget | None = None
    escalation: Escalation | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class StepType(str, Enum):
    work = "work"
    human_gate = "humanGate"
    fanout = "fanout"     # run a role N times in parallel + aggregate
    verify = "verify"     # independent verifiers over a prior artifact (quorum)


class Aggregate(str, Enum):
    majority = "majority"  # modal value of aggregateKey across candidates
    best = "best"          # candidate with the highest scoreKey
    first = "first"        # first successful candidate


class WorkflowStep(_Base):
    id: str
    type: StepType = StepType.work
    run_as: str | None = Field(default=None, alias="runAs")
    needs: list[str] = Field(default_factory=list)
    output_schema: str | None = Field(default=None, alias="outputSchema")
    policy: str | None = None  # for humanGate steps: which action policy governs it
    # loop_bound makes an intentional cycle explicit and finite.
    loop_bound: int | None = Field(default=None, alias="loopBound")

    # fanout: run the role `fanout` times, aggregate by `aggregate` over
    # `aggregate_key` (and `score_key` for 'best').
    fanout: int | None = None
    aggregate: Aggregate | None = None
    aggregate_key: str = Field(default="label", alias="aggregateKey")
    score_key: str = Field(default="score", alias="scoreKey")

    # verify: run `verifiers` independent checks; need `verify_quorum` approvals.
    verifiers: int | None = None
    verify_quorum: int | None = Field(default=None, alias="verifyQuorum")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ExitCriteria(_Base):
    evaluator: str | None = None
    minimum_score: float | None = Field(default=None, alias="minimumScore")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Workflow(_Base):
    id: str
    version: int = 1
    input_schema: str | None = Field(default=None, alias="inputSchema")
    steps: list[WorkflowStep] = Field(default_factory=list)
    exit_criteria: ExitCriteria | None = Field(default=None, alias="exitCriteria")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Approval(_Base):
    # require: passkey | hardware_passkey | none
    require: str = "passkey"
    roles: list[str] = Field(default_factory=list)
    quorum: int = 1
    ttl: str = "10m"

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Domain(str, Enum):
    """Functional domain of an action (per the Company-in-a-Box framing:
    a company is a governed action surface across software/ops/money/legal)."""

    software = "software"
    ops = "ops"
    money = "money"
    legal = "legal"


class Action(_Base):
    id: str
    tool: str
    risk: Risk
    domain: Domain | None = None
    # idempotency: how a repeat of this action is de-duplicated at commit time.
    # Required for any action with side effects (compiler enforces).
    idempotency: str | None = None
    approval: Approval | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MemoryNamespace(_Base):
    id: str
    sources: list[str] = Field(default_factory=list)
    retrieval: str = "hybrid"
    retention: str | None = None
    require_provenance: bool = Field(default=True, alias="requireProvenance")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Memory(_Base):
    canonical: str = "postgres"
    namespaces: list[MemoryNamespace] = Field(default_factory=list)


class Evaluations(_Base):
    required: list[str] = Field(default_factory=list)


class Metadata(_Base):
    name: str
    revision: int = 1


class CompanySpec(_Base):
    api_version: str = Field(default="comcmd.dev/v1alpha1", alias="apiVersion")
    kind: str = "Company"
    metadata: Metadata
    mission: Mission
    model_profiles: dict[str, ModelProfile] = Field(default_factory=dict, alias="modelProfiles")
    roles: list[Role] = Field(default_factory=list)
    workflows: list[Workflow] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    # tools/schemas the company declares it knows about (the closed world the
    # compiler validates references against).
    tools: list[str] = Field(default_factory=list)
    schemas: list[str] = Field(default_factory=list)
    memory: Memory | None = None
    evaluations: Evaluations | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def to_canonical_dict(self) -> dict[str, Any]:
        """Alias-keyed, order-independent dict for content addressing."""
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")
