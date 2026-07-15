"""AutoSteam CompanyPack — deterministic domain logic for the game studio.

Mirrors autonomous-steam-studio's design choice: the "agents" are deterministic
Python functions with typed inputs/outputs (rule/template engines), not free
-running models. Side effects (publishing to Steam) never happen in a skill —
the release is an ActionIntent authorized by the gateway and performed by the
registered `steam.publish` handler exactly once.

SKILLS  : step_id -> Worker skill (read-only domain computation)
HANDLERS: tool    -> executor handler (the authorized effect)
"""

from __future__ import annotations

import hashlib

from acme.workers.api import TaskEnvelope, WorkerResult

# Allowed game families (as in autonomous-steam-studio), with core-loop defaults.
FAMILY_DEFAULTS = {
    "puzzle_box": {"core_loop": "arrange-solve", "levels": 24},
    "arcade_score": {"core_loop": "dodge-score", "levels": 1},
    "micro_horror": {"core_loop": "explore-evade", "levels": 6},
    "cozy_toybox": {"core_loop": "tinker-collect", "levels": 8},
    "luck_machine": {"core_loop": "spin-press", "levels": 12},
}

# Opportunity-score weights (config-driven in the real studio).
WEIGHTS = {"demand_signal": 0.5, "competition_intensity": -0.3, "ip_risk": -0.2}


def _score(concept: dict) -> float:
    return round(sum(WEIGHTS[k] * float(concept.get(k, 0.0)) for k in WEIGHTS), 3)


def market(env: TaskEnvelope) -> WorkerResult:
    concept = env.inputs.get("concept", {
        "family": "puzzle_box", "demand_signal": 0.8,
        "competition_intensity": 0.4, "ip_risk": 0.1,
    })
    score = _score(concept)
    return WorkerResult(status="ok", artifact={
        "family": concept.get("family", "puzzle_box"),
        "opportunity_score": score,
        "greenlit": score >= 0.2,
    })


def design(env: TaskEnvelope) -> WorkerResult:
    upstream = env.inputs.get("_upstream", {}).get("market", {}) or {}
    family = upstream.get("family", "puzzle_box")
    defaults = FAMILY_DEFAULTS.get(family, FAMILY_DEFAULTS["puzzle_box"])
    return WorkerResult(status="ok", artifact={
        "family": family, "core_loop": defaults["core_loop"],
        "levels": defaults["levels"], "title": f"{family}-mvp",
    })


def qa(env: TaskEnvelope) -> WorkerResult:
    spec = env.inputs.get("_upstream", {}).get("design", {}) or {}
    levels = int(spec.get("levels", 1))
    # deterministic "playtest": completion proportional to level count, capped
    completion = min(1.0, 0.6 + 0.02 * levels)
    return WorkerResult(status="ok", artifact={
        "static_checks": "pass",
        "playtest_completion": round(completion, 3),
        "passed": completion >= 0.7,
    })


def compliance(env: TaskEnvelope) -> WorkerResult:
    up = env.inputs.get("_upstream", {})
    qa_report = up.get("qa", {}) or {}
    spec = up.get("design", {}) or {}
    build = hashlib.sha256(
        f"{spec.get('title')}:{spec.get('levels')}".encode()).hexdigest()[:12]
    # human_approval_required is always True (as in autonomous-steam-studio)
    recommendation = "approve" if qa_report.get("passed") else "review"
    return WorkerResult(status="ok", artifact={
        "build_hash": build,
        "recommendation": recommendation,
        "human_approval_required": True,
    })


# --- the authorized effect ------------------------------------------------

def publish_to_steam(intent) -> dict:
    return {"published": True, "target": intent.target, "tool": intent.tool}


SKILLS = {
    "market": market,
    "design": design,
    "qa": qa,
    "compliance": compliance,
}

HANDLERS = {
    "steam.publish": publish_to_steam,
}
