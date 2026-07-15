"""Acme operator CLI: compile | run | inspect | schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from acme.compile.compiler import compile_company
from acme.gateway.gate import Gateway
from acme.kernel.ledger import Ledger
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
    spec = load_company_spec(args.company)
    result = compile_company(spec)
    if not result.ok:
        print("COMPILE FAILED (run aborted):", file=sys.stderr)
        for e in result.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    rev = result.revision
    ledger = Ledger(args.ledger or ":memory:")
    gateway = Gateway(ledger, _actions_index(spec))
    runner = WorkflowRunner(rev, ledger, NativeWorker(), gateway)

    handle = runner.start(args.workflow, inputs={})
    print(f"task {handle.task_id}  state={handle.state.value}")
    for sid, art in handle.artifacts.items():
        print(f"  step {sid}: {art}")
    if handle.waiting_on:
        print(f"  waiting_on: {handle.waiting_on}")
    print(f"  ledger chain valid: {ledger.verify_chain(rev.company_name)}")
    return 0


def cmd_inspect(args) -> int:
    ledger = Ledger(args.ledger)
    n = 0
    for se in ledger.read(args.company_name):
        n += 1
        t = se.event.task_id or "-"
        print(f"#{se.seq:04d} {se.event.type.value:20s} task={t} {se.event.payload}")
    print(f"[{n} events]  chain valid: {ledger.verify_chain(args.company_name)}")
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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
