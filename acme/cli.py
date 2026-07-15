"""Acme operator CLI: compile | run | inspect | schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from acme.compile.compiler import compile_company
from acme.gateway.gate import Gateway
from acme.kernel import make_ledger
from acme.kernel.workflow import WorkflowRunner
from acme.spec.jsonschema import company_json_schema_str
from acme.spec.loader import load_company_spec
from acme.spec.models import Action
from acme.workers.native import NativeWorker


def _actions_index(spec) -> dict[str, Action]:
    return {a.id: a for a in spec.actions}


def cmd_schema(args) -> int:
    out = company_json_schema_str()
    if args.output:
        Path(args.output).write_text(out + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(out)
    return 0


def cmd_compile(args) -> int:
    spec = load_company_spec(args.company)
    result = compile_company(spec)
    if not result.ok:
        print("COMPILE FAILED:", file=sys.stderr)
        for e in result.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    rev = result.revision
    print(f"OK  {rev.company_name}  revision={rev.revision}")
    print(f"    revision_id = {rev.revision_id}")
    print(f"    spec_digest = {rev.spec_digest}")
    print(f"    roles={len(rev.compiled.get('roles', []))} "
          f"workflows={len(rev.compiled.get('workflows', []))} "
          f"actions={len(rev.compiled.get('actions', []))}")
    return 0


def cmd_run(args) -> int:
    from acme.compile.errors import CompileFailed
    from acme.pack import build_runner, load_pack

    pack = load_pack(args.company)
    try:
        ctx = build_runner(pack, ledger_url=args.ledger)
    except CompileFailed as exc:
        print("COMPILE FAILED (run aborted):", file=sys.stderr)
        for e in exc.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    handle = ctx.runner.start(args.workflow, inputs={})
    print(f"task {handle.task_id}  state={handle.state.value}")
    for sid, art in handle.artifacts.items():
        print(f"  step {sid}: {art}")
    if handle.waiting_on:
        print(f"  waiting_on: {handle.waiting_on}")
    print(f"  ledger chain valid: {ctx.ledger.verify_chain(ctx.revision.company_name)}")
    return 0


def cmd_inspect(args) -> int:
    ledger = make_ledger(args.ledger)
    n = 0
    for se in ledger.read(args.company_name):
        n += 1
        t = se.event.task_id or "-"
        print(f"#{se.seq:04d} {se.event.type.value:20s} task={t} {se.event.payload}")
    print(f"[{n} events]  chain valid: {ledger.verify_chain(args.company_name)}")
    return 0


def cmd_approvals(args) -> int:
    """Operator inbox: actions awaiting human approval, read from the ledger.

    Read-only and cross-process (the ledger is the source of truth). An action
    is pending if it was requested but has no subsequent 'authorized' receipt.
    """
    from acme.kernel.records import EventType

    ledger = make_ledger(args.ledger)
    requested: dict[str, dict] = {}
    authorized: set[str] = set()
    for se in ledger.read(args.company_name):
        e = se.event
        if e.type == EventType.approval_requested:
            d = e.payload.get("intent_digest")
            if d:
                requested[d] = e.payload
        elif e.type == EventType.execution_receipt and e.payload.get("decision") == "authorized":
            d = e.payload.get("intent_digest")
            if d:
                authorized.add(d)

    pending = [(d, p) for d, p in requested.items() if d not in authorized]
    if not pending:
        print("no pending approvals")
        return 0
    for d, p in pending:
        print(f"- {d}")
        print(f"    tier={p.get('tier')} require={p.get('required')} "
              f"quorum={p.get('quorum')} eligible={p.get('eligible')}")
        if p.get("approvers"):
            print(f"    approved_by={p.get('approvers')}")
        if p.get("challenge_b64"):
            print(f"    challenge={p.get('challenge_b64')}")
    print(f"[{len(pending)} pending]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="acme", description="Acme company control plane")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("schema", help="emit the CompanySpec JSON Schema")
    ps.add_argument("-o", "--output")
    ps.set_defaults(func=cmd_schema)

    pc = sub.add_parser("compile", help="compile a company dir/yaml")
    pc.add_argument("company")
    pc.set_defaults(func=cmd_compile)

    pr = sub.add_parser("run", help="compile and run a workflow")
    pr.add_argument("company")
    pr.add_argument("workflow")
    pr.add_argument("--ledger", help="sqlite path (default in-memory)")
    pr.set_defaults(func=cmd_run)

    pi = sub.add_parser("inspect", help="dump a ledger's events")
    pi.add_argument("ledger")
    pi.add_argument("company_name")
    pi.set_defaults(func=cmd_inspect)

    pa = sub.add_parser("approvals", help="operator inbox: pending approvals")
    pa.add_argument("ledger")
    pa.add_argument("company_name")
    pa.set_defaults(func=cmd_approvals)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
