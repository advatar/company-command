"""Load a CompanySpec from YAML/JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from comcmd.spec.models import CompanySpec


def load_company_spec(path: str | Path) -> CompanySpec:
    p = Path(path)
    if p.is_dir():
        p = p / "company.yaml"
    raw: Any = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{p}: top-level document must be a mapping")
    return CompanySpec.model_validate(raw)
