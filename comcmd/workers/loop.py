"""Bounded repository-engineering worker backed by the optional Loop package.

Acme owns the trusted policy and workspace boundary. A TaskEnvelope contributes
goal text and upstream artifacts, but cannot select commands, providers,
timeouts, state paths, or environment variables.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from comcmd.workers.api import TaskEnvelope, WorkerResult


class LoopWorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoopPolicy:
    executor_provider: str = "codex"
    verifier_provider: str = "claude"
    max_iterations: int = 8
    max_minutes: float = 60
    step_timeout_seconds: int = 900
    pass_marker: str = "LOOP_VERDICT: PASS"

    def __post_init__(self) -> None:
        providers = {"codex", "claude"}
        if self.executor_provider not in providers:
            raise ValueError("executor_provider must be 'codex' or 'claude'")
        if self.verifier_provider not in providers:
            raise ValueError("verifier_provider must be 'codex' or 'claude'")
        if self.max_iterations < 1 or self.max_minutes <= 0:
            raise ValueError("Loop limits must be positive")
        if self.step_timeout_seconds < 1:
            raise ValueError("step_timeout_seconds must be positive")
        if not self.pass_marker.strip() or "\n" in self.pass_marker:
            raise ValueError("pass_marker must be one non-empty line")


LoopRun = Callable[
    [dict[str, Any], Path, Mapping[str, str], bool],
    Any,
]


def _default_run(
    raw_config: dict[str, Any],
    workspace: Path,
    environment: Mapping[str, str],
    resume: bool,
) -> Any:
    try:
        from agent_loop.core import Config, Runner
    except ImportError as exc:
        raise LoopWorkerError(
            "Loop support is not installed; install comcmd[loop]"
        ) from exc
    config = Config.from_dict(raw_config)
    return Runner(config, workspace, env=environment).run(resume=resume)


class LoopWorker:
    """Run one bounded Loop in an isolated, task-scoped repository clone."""

    name = "loop"
    _STATE_DIR = ".acme-loop"
    _IDENTITY_FILE = "envelope.json"
    _DEFAULT_ENV = (
        "HOME", "LANG", "LC_ALL", "PATH", "SHELL", "TMPDIR", "USER",
        "XDG_CONFIG_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR",
    )

    def __init__(
        self,
        source_repository: str | Path,
        workspace_root: str | Path,
        *,
        policy: LoopPolicy | None = None,
        environment_allowlist: tuple[str, ...] | None = None,
        runner: LoopRun | None = None,
    ):
        self.source_repository = Path(source_repository).expanduser().resolve()
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.policy = policy or LoopPolicy()
        self.environment_allowlist = (
            environment_allowlist
            if environment_allowlist is not None
            else self._DEFAULT_ENV
        )
        self._runner = runner or _default_run
        if not self.source_repository.is_dir():
            raise ValueError(f"source repository does not exist: {self.source_repository}")
        if self.workspace_root == self.source_repository:
            raise ValueError("workspace_root must differ from source_repository")
        try:
            self.workspace_root.relative_to(self.source_repository)
        except ValueError:
            pass
        else:
            raise ValueError("workspace_root must not be inside source_repository")

    def run(self, envelope: TaskEnvelope) -> WorkerResult:
        try:
            workspace = self._prepare_workspace(envelope)
            state = self._load_state(workspace)
            if state and state.get("status") in {"PASSED", "EXHAUSTED", "FAILED"}:
                return self._result(envelope, workspace, state)

            raw_config = self._config(envelope)
            environment = {
                name: os.environ[name]
                for name in self.environment_allowlist
                if name in os.environ
            }
            resume = bool(state and state.get("status") in {"RUNNING", "STOPPED"})
            state = self._state_dict(
                self._runner(raw_config, workspace, environment, resume)
            )
            return self._result(envelope, workspace, state)
        except LoopWorkerError as exc:
            return WorkerResult(
                status="deferred",
                usage={"worker": self.name, "reason": str(exc)},
            )
        except Exception as exc:
            return WorkerResult(
                status="error",
                usage={"worker": self.name, "error": str(exc)},
            )

    def _config(self, envelope: TaskEnvelope) -> dict[str, Any]:
        return {
            "loop": {
                "goal": self._goal(envelope),
                "max_iterations": self.policy.max_iterations,
                "max_minutes": self.policy.max_minutes,
                "step_timeout_seconds": self.policy.step_timeout_seconds,
                "state_dir": self._STATE_DIR,
            },
            "executor": {"provider": self.policy.executor_provider},
            "verifier": {
                "provider": self.policy.verifier_provider,
                "pass_marker": self.policy.pass_marker,
            },
        }

    def _goal(self, envelope: TaskEnvelope) -> str:
        requested = envelope.inputs.get("goal")
        acceptance = envelope.inputs.get("acceptance")
        upstream = envelope.inputs.get("_upstream", {})
        parts = [
            f"Complete Acme task {envelope.task_id}, step {envelope.step_id}.",
            f"Act as role: {envelope.role or '(unspecified)'}.",
        ]
        if requested:
            parts.append(f"Goal:\n{requested}")
        else:
            parts.append(
                "Goal:\nProduce the repository change required by the task inputs below."
            )
        if acceptance:
            parts.append(f"Acceptance criteria:\n{acceptance}")
        parts.append(
            "Allowed Acme tools (informational; do not perform external effects): "
            + (", ".join(envelope.allowed_tools) or "(none)")
        )
        parts.append(
            "Task inputs and upstream artifacts:\n"
            + json.dumps(
                {"inputs": envelope.inputs, "upstream": upstream},
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        parts.append(
            "Modify only this isolated repository. Do not merge, deploy, publish, "
            "message, purchase, or perform any other external effect. Describe any "
            "needed external effect in the result for Acme to authorize separately."
        )
        return "\n\n".join(parts)

    def _prepare_workspace(self, envelope: TaskEnvelope) -> Path:
        source_commit = (
            self._git("rev-parse", "HEAD", cwd=self.source_repository).strip()
            if self._is_git_repository(self.source_repository)
            else None
        )
        identity = {
            "company": envelope.company,
            "task_id": envelope.task_id,
            "step_id": envelope.step_id,
            "source": str(self.source_repository),
            "base_commit": source_commit,
        }
        token = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode()
        ).hexdigest()[:20]
        workspace = self.workspace_root / token
        identity_path = workspace / self._STATE_DIR / self._IDENTITY_FILE
        if workspace.exists():
            try:
                existing = json.loads(identity_path.read_text())
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                raise LoopWorkerError(
                    f"refusing unrecognized existing workspace: {workspace}"
                ) from exc
            if existing != identity:
                raise LoopWorkerError(f"workspace identity mismatch: {workspace}")
            return workspace

        self.workspace_root.mkdir(parents=True, exist_ok=True)
        if self._is_git_repository(self.source_repository):
            self._git(
                "clone", "--local", "--no-hardlinks", "--quiet",
                str(self.source_repository), str(workspace),
                cwd=self.workspace_root,
            )
        else:
            shutil.copytree(
                self.source_repository,
                workspace,
                ignore=shutil.ignore_patterns(
                    self._STATE_DIR, ".loop", "__pycache__", "*.pyc"
                ),
            )
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        identity_path.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
        return workspace

    def _result(
        self, envelope: TaskEnvelope, workspace: Path, state: dict[str, Any]
    ) -> WorkerResult:
        loop_status = str(state.get("status", "FAILED"))
        status = {
            "PASSED": "ok",
            "EXHAUSTED": "deferred",
            "STOPPED": "deferred",
            "DRY_RUN": "deferred",
            "FAILED": "error",
        }.get(loop_status, "error")
        artifact = {
            "worker": self.name,
            "company": envelope.company,
            "task_id": envelope.task_id,
            "step_id": envelope.step_id,
            "loop": state,
            "workspace": str(workspace),
            **self._repository_evidence(workspace),
        }
        usage = {
            "worker": self.name,
            "loop_run_id": state.get("run_id"),
            "loop_status": loop_status,
            "iterations": state.get("iteration", 0),
            "reason": state.get("reason", ""),
        }
        return WorkerResult(status=status, artifact=artifact, usage=usage)

    def _repository_evidence(self, workspace: Path) -> dict[str, Any]:
        if not self._is_git_repository(workspace):
            return {"base_commit": None, "head_commit": None, "changed_files": []}
        identity = json.loads(
            (workspace / self._STATE_DIR / self._IDENTITY_FILE).read_text()
        )
        base = identity["base_commit"]
        head = self._git("rev-parse", "HEAD", cwd=workspace).strip()
        status = self._git("status", "--short", cwd=workspace)
        status_names = [
            line[3:]
            for line in status.splitlines()
            if len(line) > 3 and not line[3:].startswith(f"{self._STATE_DIR}/")
        ]
        committed_names = self._git(
            "diff", "--name-only", base, cwd=workspace
        ).splitlines()
        changed = list(dict.fromkeys([*committed_names, *status_names]))
        diff = self._git(
            "diff", "--no-ext-diff", "--binary", base, cwd=workspace
        )
        return {
            "base_commit": base,
            "head_commit": head,
            "changed_files": changed,
            "diff": diff[-50_000:],
            "diff_truncated": len(diff) > 50_000,
        }

    def _load_state(self, workspace: Path) -> dict[str, Any] | None:
        path = workspace / self._STATE_DIR / "state.json"
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise LoopWorkerError(f"invalid Loop state: {path}") from exc
        return value if isinstance(value, dict) else None

    @staticmethod
    def _state_dict(state: Any) -> dict[str, Any]:
        if isinstance(state, dict):
            return state
        if is_dataclass(state):
            return asdict(state)
        if hasattr(state, "__dict__"):
            return dict(state.__dict__)
        raise LoopWorkerError("Loop runner returned an unsupported state object")

    @staticmethod
    def _is_git_repository(path: Path) -> bool:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    @staticmethod
    def _git(*args: str, cwd: Path) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            raise LoopWorkerError(
                f"git {' '.join(args)} failed: {proc.stderr.strip()[:400]}"
            )
        return proc.stdout
