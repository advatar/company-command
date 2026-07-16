"""CompanyService — the stateful engine behind the HTTP API.

Loads CompanyPacks from a directory and holds the shared runtime: one event
ledger, one durable engine (when a DSN is configured), and shared credential /
approval stores. Each company gets a gateway + executor + runner wired to that
shared runtime. This is what makes Acme a *backend* rather than a one-shot CLI:
a long-running process that starts governed tasks, tracks their state, and drives
the WebAuthn approval ceremony.

Approvals are isolated across companies by the company-scoped action digest, so
one shared approval store is safe. Packs are loaded with trusted=True — the
companies directory is operator-controlled, not customer-uploaded.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import webauthn
from webauthn.helpers import options_to_json

from acme.config import Settings
from acme.gateway.enrollment import CredentialStore
from acme.gateway.webauthn_verifier import WebAuthnVerifier
from acme.kernel import make_ledger
from acme.kernel.executor import Executor
from acme.kernel.records import EventType
from acme.kernel.workflow import WorkflowRunner
from acme.log import get_logger
from acme.pack import CompanyPack, build_runner, load_pack

_log = get_logger(__name__)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


class CompanyService:
    def __init__(self, settings: Settings, companies_dir: str | Path):
        self.settings = settings
        self._dir = Path(companies_dir)
        self._ledger = make_ledger(settings.effective_ledger_url)
        self._durable_engine = None
        if settings.durable:
            from acme.kernel.durable import make_durable_engine
            self._durable_engine = make_durable_engine(settings.database_url)

        # Shared stores (durable when a DSN is set).
        if settings.durable:
            from acme.gateway.stores_pg import PgApprovalStore, PgCredentialStore
            self._creds = PgCredentialStore(settings.database_url)
            self._approvals = PgApprovalStore(settings.database_url, now=time.time)
        else:
            from acme.gateway.approvals import ApprovalStore
            self._creds = CredentialStore()
            self._approvals = ApprovalStore(time.time)

        self._verifier = WebAuthnVerifier(self._creds, rp_id=settings.rp_id,
                                          origin=settings.rp_origin)
        self._packs: dict[str, CompanyPack] = {}
        self._ctx: dict[str, Any] = {}
        self._enroll_challenges: dict[str, bytes] = {}
        self._load_all()

    # -- loading -------------------------------------------------------------

    def _load_all(self) -> None:
        if not self._dir.is_dir():
            return
        for child in sorted(self._dir.iterdir()):
            if (child / "company.yaml").exists():
                try:
                    self._register(load_pack(child, trusted=True))
                except Exception as exc:  # a bad pack must not kill the service
                    _log.warning("skipping company %s: %s", child.name, exc)

    def _register(self, pack: CompanyPack) -> None:
        name = pack.spec.metadata.name
        # Reuse the shared ledger/engine/stores; build_runner would make its own,
        # so wire the runner directly.
        from acme.compile.compiler import compile_company
        from acme.gateway.gate import Gateway
        from acme.workers.native import NativeWorker

        revision = compile_company(pack.spec).raise_if_failed()
        gateway = Gateway(self._ledger, {a.id: a for a in pack.spec.actions},
                          verifier=self._verifier, approval_store=self._approvals)
        executor = Executor(self._ledger, dict(pack.handlers))
        runner = WorkflowRunner(revision, self._ledger, NativeWorker(skills=pack.skills),
                                gateway, executor, durable_engine=self._durable_engine)
        self._packs[name] = pack
        self._ctx[name] = {"revision": revision, "gateway": gateway, "runner": runner}
        _log.info("registered company %s (%d workflows)", name,
                  len(pack.spec.workflows))

    def companies(self) -> list[dict]:
        return [{"name": n,
                 "workflows": [w.id for w in p.spec.workflows],
                 "roles": [r.id for r in p.spec.roles]}
                for n, p in self._packs.items()]

    def _require(self, company: str) -> dict:
        ctx = self._ctx.get(company)
        if ctx is None:
            raise KeyError(company)
        return ctx

    # -- tasks ---------------------------------------------------------------

    def start_task(self, company: str, workflow: str, inputs: dict) -> dict:
        ctx = self._require(company)
        handle = ctx["runner"].start(workflow, inputs=inputs or {})
        return self._handle_view(handle)

    def task_status(self, company: str, task_id: str) -> dict | None:
        events = [se.event for se in self._ledger.read(company)
                  if se.event.task_id == task_id]
        if not events:
            return None
        state, artifacts, workflow, waiting_on = "READY", {}, None, None
        for e in events:
            if e.type == EventType.task_created:
                workflow = e.payload.get("workflow")
            elif e.type == EventType.task_state_changed:
                state = e.payload.get("state", state)
            elif e.type == EventType.step_succeeded:
                artifacts[e.payload["step"]] = e.payload.get("artifact")
            elif e.type == EventType.approval_requested:
                waiting_on = e.payload
        return {"task_id": task_id, "workflow": workflow, "state": state,
                "artifacts": artifacts,
                "waiting_on": waiting_on if state == "WAITING_FOR_HUMAN" else None,
                "chain_valid": self._ledger.verify_chain(company)}

    def _handle_view(self, handle) -> dict:
        return {"task_id": handle.task_id, "workflow": handle.workflow_id,
                "state": handle.state.value, "artifacts": handle.artifacts,
                "waiting_on": handle.waiting_on}

    # -- approvals + WebAuthn ------------------------------------------------

    def pending_approvals(self, company: str) -> list[dict]:
        self._require(company)
        return self._ctx[company]["gateway"].pending_approvals()

    def enroll_options(self, company: str, principal: str) -> dict:
        self._require(company)
        opts = webauthn.generate_registration_options(
            rp_id=self.settings.rp_id, rp_name="Acme", user_name=principal)
        self._enroll_challenges[f"{company}:{principal}"] = opts.challenge
        return {"publicKey": _json(options_to_json(opts))}

    def enroll_verify(self, company: str, principal: str, credential: dict) -> dict:
        self._require(company)
        challenge = self._enroll_challenges.pop(f"{company}:{principal}", None)
        if challenge is None:
            raise ValueError("no enrollment in progress for this principal")
        self._creds.enroll_registration(
            principal, credential=credential, expected_challenge=challenge,
            rp_id=self.settings.rp_id, origin=self.settings.rp_origin)
        return {"enrolled": True, "principal": principal}

    def approval_options(self, company: str, digest: str) -> dict:
        self._require(company)
        gw = self._ctx[company]["gateway"]
        challenge = gw.challenge_for(digest)
        if challenge is None:
            raise KeyError(digest)
        return {"rpId": self.settings.rp_id, "challenge": _b64url(challenge),
                "userVerification": "required"}

    def submit_approval(self, company: str, task_id: str, workflow: str,
                        step: str, assertion: dict) -> dict:
        ctx = self._require(company)
        handle = ctx["runner"].approve_step(task_id, workflow, step, assertion)
        return self._handle_view(handle)

    # -- eval + audit --------------------------------------------------------

    def evaluate(self, company: str, baseline: str, variant: str) -> dict:
        pack = self._packs.get(company)
        if pack is None:
            raise KeyError(company)
        from acme.eval.harness import evaluate
        report = evaluate(pack.spec, baseline=baseline, variant=variant,
                          scenarios=pack.scenarios, skills=pack.skills,
                          handlers=pack.handlers)

        def view(m) -> dict:
            return {**m.__dict__, "success_rate": m.success_rate}

        return {"baseline": view(report.baseline), "variant": view(report.variant),
                "promote": report.promote, "reasons": report.reasons}

    def events(self, company: str, limit: int = 200) -> list[dict]:
        self._require(company)
        out = []
        for se in self._ledger.read(company):
            out.append({"seq": se.seq, "type": se.event.type.value,
                        "task_id": se.event.task_id, "payload": se.event.payload})
        return out[-limit:]


def _json(s: str) -> Any:
    import json
    return json.loads(s)
