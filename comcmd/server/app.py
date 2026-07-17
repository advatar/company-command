"""Company Command HTTP API — the backend surface of the engine.

A long-running FastAPI service over a `CompanyService`. Endpoints cover the full
governed lifecycle: start a task, poll its state, list the approval inbox, run
the WebAuthn enroll + approve ceremony, run the evaluation gate, and read the
tamper-evident audit log. This is the process an operator or a UI talks to.

The service never returns secrets: registration/authentication ceremonies return
only the WebAuthn challenge/options the client needs to sign; capabilities and
credential private material never leave the server.
"""

from __future__ import annotations

from typing import Any

import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from comcmd.compile.errors import CompileFailed
from comcmd.config import Settings
from comcmd.log import configure
from comcmd.pack import UntrustedPackError
from comcmd.server.service import CompanyService


class StartTask(BaseModel):
    workflow: str
    inputs: dict[str, Any] = {}


class EnrollStart(BaseModel):
    principal: str


class EnrollVerify(BaseModel):
    principal: str
    credential: dict[str, Any]


class SubmitApproval(BaseModel):
    task_id: str
    workflow: str
    step: str
    assertion: dict[str, Any]


class RunEval(BaseModel):
    baseline: str
    variant: str


def create_app(settings: Settings | None = None,
               companies_dir: str | None = None) -> FastAPI:
    configure()
    settings = settings or Settings.from_env()
    import os
    companies_dir = companies_dir or os.environ.get("COMCMD_COMPANIES_DIR", "companies")
    service = CompanyService(settings, companies_dir)

    app = FastAPI(title="Company Command", version="0.1.0",
                  summary="Autonomous-company control plane")
    app.state.service = service

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        # Health is intentionally public for load balancers. Configure
        # COMCMD_API_TOKEN in every non-local deployment; unset means dev mode.
        if settings.api_token and request.url.path != "/health":
            auth = request.headers.get("authorization", "")
            supplied = auth[7:] if auth.lower().startswith("bearer ") else ""
            if not secrets.compare_digest(supplied, settings.api_token):
                return JSONResponse({"detail": "authentication required"},
                                    status_code=401,
                                    headers={"WWW-Authenticate": "Bearer"})
        return await call_next(request)

    def svc() -> CompanyService:
        return app.state.service

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "durable": settings.durable,
                "companies": [c["name"] for c in svc().companies()]}

    @app.get("/companies")
    def companies() -> list[dict]:
        return svc().companies()

    @app.post("/companies/{company}/tasks")
    def start_task(company: str, body: StartTask) -> dict:
        try:
            return svc().start_task(company, body.workflow, body.inputs)
        except KeyError:
            raise HTTPException(404, f"unknown company or workflow: {company}")

    @app.get("/companies/{company}/tasks/{task_id}")
    def get_task(company: str, task_id: str) -> dict:
        status = svc().task_status(company, task_id)
        if status is None:
            raise HTTPException(404, "unknown task")
        return status

    @app.get("/companies/{company}/approvals")
    def approvals(company: str) -> list[dict]:
        try:
            return svc().pending_approvals(company)
        except KeyError:
            raise HTTPException(404, f"unknown company: {company}")

    @app.post("/companies/{company}/credentials/options")
    def enroll_options(company: str, body: EnrollStart) -> dict:
        try:
            return svc().enroll_options(company, body.principal)
        except KeyError:
            raise HTTPException(404, f"unknown company: {company}")

    @app.post("/companies/{company}/credentials")
    def enroll_verify(company: str, body: EnrollVerify) -> dict:
        try:
            return svc().enroll_verify(company, body.principal, body.credential)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @app.post("/companies/{company}/approvals/{digest}/options")
    def approval_options(company: str, digest: str) -> dict:
        try:
            return svc().approval_options(company, digest)
        except KeyError:
            raise HTTPException(404, "unknown company or pending approval")

    @app.post("/companies/{company}/approvals/submit")
    def submit_approval(company: str, body: SubmitApproval) -> dict:
        try:
            return svc().submit_approval(company, body.task_id, body.workflow,
                                         body.step, body.assertion)
        except KeyError:
            raise HTTPException(404, f"unknown company: {company}")

    @app.post("/companies/{company}/eval")
    def run_eval(company: str, body: RunEval) -> dict:
        try:
            return svc().evaluate(company, body.baseline, body.variant)
        except KeyError:
            raise HTTPException(404, f"unknown company: {company}")

    @app.get("/companies/{company}/events")
    def events(company: str, limit: int = 200) -> list[dict]:
        try:
            return svc().events(company, limit=limit)
        except KeyError:
            raise HTTPException(404, f"unknown company: {company}")

    return app
