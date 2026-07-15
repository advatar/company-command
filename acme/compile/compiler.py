"""Compile a CompanySpec into an immutable CompanyRevision.

The compiler is where authority is validated. It is default-deny by
construction: anything ambiguous — an unknown reference, a write role with no
governing policy, a side-effecting action with no idempotency, a high-risk
action with no approver — is a hard error, never a silent allow.

Validation matrix (see IMPLEMENTATION_PLAN.md §4):
  E-REF-ROLE, E-REF-TOOL, E-REF-SCHEMA, E-REF-WORKFLOW,
  E-AUTH-NOPOLICY, E-CYCLE-UNBOUNDED, E-IDEMPOTENCY,
  E-APPROVER, E-CAP-DEFAULTALLOW, E-VERSION
"""

from __future__ import annotations

from acme.compile.errors import CompileError, CompileResult
from acme.kernel.records import CompanyRevision
from acme.spec.models import CompanySpec, Risk, StepType

SUPPORTED_API_VERSIONS = {"acme.dev/v1alpha1"}

# Risk classes that produce external/durable effects and therefore need both
# idempotency semantics and (for the top two) an eligible approver.
SIDE_EFFECTING = {Risk.external_reversible, Risk.consequential}
NEEDS_APPROVER = {Risk.external_reversible, Risk.consequential}

# Approval strength required per risk (reconciled with STRATEGY.md §7.2):
# external_reversible -> user-verified passkey; consequential -> hardware key.
REQUIRED_APPROVAL = {
    Risk.external_reversible: {"passkey", "hardware_passkey"},
    Risk.consequential: {"hardware_passkey"},
}


def compile_company(spec: CompanySpec) -> CompileResult:
    errors: list[CompileError] = []

    def err(code: str, message: str, where: str = "") -> None:
        errors.append(CompileError(code, message, where))

    # Closed-world reference sets.
    role_ids = {r.id for r in spec.roles}
    profile_ids = set(spec.model_profiles.keys())
    tool_ids = set(spec.tools)
    schema_ids = set(spec.schemas)
    workflow_ids = {w.id for w in spec.workflows}
    action_ids = {a.id for a in spec.actions}

    # E-VERSION
    if spec.api_version not in SUPPORTED_API_VERSIONS:
        err("E-VERSION", f"unsupported apiVersion {spec.api_version!r}", "apiVersion")

    # Roles: tools, profiles, delegation targets exist.
    for role in spec.roles:
        for t in role.tools.allow:
            if t not in tool_ids:
                err("E-REF-TOOL", f"role {role.id!r} grants unknown tool {t!r}",
                    f"roles.{role.id}.tools")
        if role.model_profile is not None and role.model_profile not in profile_ids:
            err("E-REF-SCHEMA", f"role {role.id!r} names unknown modelProfile "
                f"{role.model_profile!r}", f"roles.{role.id}.modelProfile")
        for d in role.may_delegate_to:
            if d not in role_ids:
                err("E-REF-ROLE", f"role {role.id!r} may delegate to unknown role "
                    f"{d!r}", f"roles.{role.id}.mayDelegateTo")

    # Actions: idempotency, approver, and approval strength.
    actions_by_id = {a.id: a for a in spec.actions}
    for action in spec.actions:
        if action.tool not in tool_ids:
            err("E-REF-TOOL", f"action {action.id!r} uses unknown tool "
                f"{action.tool!r}", f"actions.{action.id}.tool")

        if action.risk in SIDE_EFFECTING and not action.idempotency:
            err("E-IDEMPOTENCY", f"side-effecting action {action.id!r} "
                f"(risk={action.risk.value}) declares no idempotency semantics",
                f"actions.{action.id}")

        if action.risk in NEEDS_APPROVER:
            appr = action.approval
            if appr is None or not appr.roles:
                err("E-APPROVER", f"high-risk action {action.id!r} "
                    f"(risk={action.risk.value}) has no eligible approver",
                    f"actions.{action.id}.approval")
            else:
                for ar in appr.roles:
                    # approver may be a human principal ("human:board") or a role id
                    if not ar.startswith("human:") and ar not in role_ids:
                        err("E-REF-ROLE", f"action {action.id!r} approver {ar!r} "
                            f"is neither a human principal nor a known role",
                            f"actions.{action.id}.approval.roles")
                allowed = REQUIRED_APPROVAL.get(action.risk, set())
                if appr.require not in allowed:
                    err("E-CAP-DEFAULTALLOW",
                        f"action {action.id!r} requires approval {appr.require!r} "
                        f"but risk {action.risk.value} demands one of "
                        f"{sorted(allowed)}", f"actions.{action.id}.approval.require")

        if action.risk == Risk.prohibited and action.approval is not None:
            err("E-CAP-DEFAULTALLOW", f"prohibited action {action.id!r} must not "
                f"declare an approval path (it can never be authorized)",
                f"actions.{action.id}")

    # Roles with write authority must be governed by at least one action policy.
    # An action governs a role if that role (or a human) can approve it OR the
    # role's granted tools include the action's tool.
    for role in spec.roles:
        if not role.write_authority:
            continue
        governed = any(
            a.tool in set(role.tools.allow)
            for a in spec.actions
        )
        if not governed:
            err("E-AUTH-NOPOLICY", f"role {role.id!r} has writeAuthority but no "
                f"action policy governs any tool it holds", f"roles.{role.id}")

    # Workflows: step references and bounded cycles.
    for wf in spec.workflows:
        step_ids = {s.id for s in wf.steps}
        needs_graph: dict[str, list[str]] = {}
        for step in wf.steps:
            if step.type == StepType.work:
                if step.run_as is None:
                    err("E-REF-ROLE", f"work step {wf.id}.{step.id} has no runAs",
                        f"workflows.{wf.id}.{step.id}")
                elif step.run_as not in role_ids:
                    err("E-REF-ROLE", f"step {wf.id}.{step.id} runAs unknown role "
                        f"{step.run_as!r}", f"workflows.{wf.id}.{step.id}")
            if step.type == StepType.human_gate:
                if step.policy is None or step.policy not in action_ids:
                    err("E-REF-WORKFLOW", f"humanGate {wf.id}.{step.id} references "
                        f"unknown action policy {step.policy!r}",
                        f"workflows.{wf.id}.{step.id}")
            if step.output_schema and step.output_schema not in schema_ids:
                err("E-REF-SCHEMA", f"step {wf.id}.{step.id} outputSchema "
                    f"{step.output_schema!r} unknown", f"workflows.{wf.id}.{step.id}")
            for n in step.needs:
                if n not in step_ids:
                    err("E-REF-WORKFLOW", f"step {wf.id}.{step.id} needs unknown "
                        f"step {n!r}", f"workflows.{wf.id}.{step.id}")
            needs_graph[step.id] = list(step.needs)

        if wf.input_schema and wf.input_schema not in schema_ids:
            err("E-REF-SCHEMA", f"workflow {wf.id} inputSchema {wf.input_schema!r} "
                f"unknown", f"workflows.{wf.id}.inputSchema")

        _check_cycles(wf.id, wf.steps, needs_graph, err)

    if errors:
        return CompileResult(ok=False, errors=errors)

    compiled = _normalize(spec)
    revision = CompanyRevision.make(
        company_name=spec.metadata.name,
        revision=spec.metadata.revision,
        spec_canonical=spec.to_canonical_dict(),
        compiled=compiled,
    )
    return CompileResult(ok=True, revision=revision)


def _check_cycles(wf_id, steps, needs_graph, err) -> None:
    """Reject any dependency cycle that isn't made finite by an explicit bound."""
    bound = {s.id: s.loop_bound for s in steps}
    WHITE, GREY, BLACK = 0, 1, 2
    color = {sid: WHITE for sid in needs_graph}

    def visit(sid: str, stack: list[str]) -> None:
        color[sid] = GREY
        for dep in needs_graph.get(sid, []):
            if color.get(dep) == GREY:
                cyc = stack[stack.index(dep):] + [dep] if dep in stack else [dep]
                if not any(bound.get(x) for x in cyc):
                    err("E-CYCLE-UNBOUNDED", f"workflow {wf_id} has an unbounded "
                        f"cycle: {' -> '.join(cyc)}", f"workflows.{wf_id}")
            elif color.get(dep) == WHITE:
                visit(dep, stack + [dep])
        color[sid] = BLACK

    for sid in needs_graph:
        if color[sid] == WHITE:
            visit(sid, [sid])


def _normalize(spec: CompanySpec) -> dict:
    """Deterministic compiled body: sort collections by id for stable hashing."""
    d = spec.to_canonical_dict()
    if "roles" in d:
        d["roles"] = sorted(d["roles"], key=lambda r: r["id"])
    if "workflows" in d:
        d["workflows"] = sorted(d["workflows"], key=lambda w: w["id"])
    if "actions" in d:
        d["actions"] = sorted(d["actions"], key=lambda a: a["id"])
    return d
