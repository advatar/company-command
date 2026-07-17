"""Triage demo pack — shows the evaluation gate discriminating.

One deterministic classifier skill, index-driven so a fan-out runs three
different heuristics. The single-agent baseline uses heuristic 0 alone (it gets
several tickets wrong); the panel takes the majority of all three (it gets them
right). `comcmd eval` should therefore PROMOTE the panel. Verifiers apply distinct
lenses and must reach quorum before a label is accepted.
"""

from __future__ import annotations

from comcmd.workers.api import TaskEnvelope, WorkerResult

CLASSES = {"bug", "feature", "question"}


def _h0(text: str) -> str:
    if "crash" in text or "error" in text:
        return "bug"
    if "add" in text:
        return "feature"
    return "question"


def _h1(text: str) -> str:
    if "broken" in text or "fail" in text or "crash" in text:
        return "bug"
    if "would like" in text or "please add" in text or "feature" in text:
        return "feature"
    if "?" in text:
        return "question"
    return "bug"


def _h2(text: str) -> str:
    if "how" in text or "?" in text or "what" in text:
        return "question"
    if "support" in text or "add" in text or "feature" in text:
        return "feature"
    if "error" in text or "crash" in text or "broken" in text:
        return "bug"
    return "question"


_HEURISTICS = [_h0, _h1, _h2]


def classify(env: TaskEnvelope) -> WorkerResult:
    text = str(env.inputs.get("text", "")).lower()
    idx = int(env.inputs.get("_candidate", 0)) % len(_HEURISTICS)
    label = _HEURISTICS[idx](text)
    return WorkerResult(status="ok", artifact={"label": label, "score": 1.0})


def verify(env: TaskEnvelope) -> WorkerResult:
    target = env.inputs.get("_verify_target", {}) or {}
    label = target.get("label")
    agreement = float(target.get("_agreement", 1.0))
    lens = int(env.inputs.get("_verifier", 0))
    if lens == 0:
        approve = label in CLASSES            # valid class
    elif lens == 1:
        approve = agreement >= 0.5            # majority actually agreed
    else:
        approve = agreement > 0.33            # not a 3-way split
    return WorkerResult(status="ok", artifact={"approve": bool(approve)})


# Keyed by role id: the 'classifier' role drives both the single 'classify'
# step and the fan-out 'panel' step; 'verifier' drives the 'check' step.
SKILLS = {"classifier": classify, "verifier": verify}
HANDLERS = {}

SCENARIOS = [
    {"inputs": {"text": "app crashes on launch"}, "expected": {"label": "bug"}},
    {"inputs": {"text": "please add dark mode"}, "expected": {"label": "feature"}},
    {"inputs": {"text": "how do I reset my password?"}, "expected": {"label": "question"}},
    {"inputs": {"text": "the export is broken"}, "expected": {"label": "bug"}},
    {"inputs": {"text": "would like a feature to sort tasks"}, "expected": {"label": "feature"}},
    {"inputs": {"text": "login fails with error 500"}, "expected": {"label": "bug"}},
]
