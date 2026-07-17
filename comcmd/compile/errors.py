from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CompileError:
    code: str
    message: str
    where: str = ""

    def __str__(self) -> str:
        loc = f" [{self.where}]" if self.where else ""
        return f"{self.code}: {self.message}{loc}"


@dataclass
class CompileResult:
    ok: bool
    errors: list[CompileError] = field(default_factory=list)
    revision: object | None = None  # CompanyRevision when ok

    def raise_if_failed(self) -> object:
        if not self.ok:
            joined = "\n".join(f"  - {e}" for e in self.errors)
            raise CompileFailed(f"CompanySpec failed to compile:\n{joined}", self.errors)
        return self.revision


class CompileFailed(Exception):
    def __init__(self, message: str, errors: list[CompileError]):
        super().__init__(message)
        self.errors = errors
