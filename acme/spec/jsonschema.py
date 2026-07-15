"""Emit the JSON Schema for CompanySpec.

The schema is a published contract; `acme schema` writes it to schemas/.
"""

from __future__ import annotations

import json
from typing import Any

from acme.spec.models import CompanySpec


def company_json_schema() -> dict[str, Any]:
    schema = CompanySpec.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Acme CompanySpec"
    return schema


def company_json_schema_str() -> str:
    return json.dumps(company_json_schema(), indent=2, sort_keys=True)
