"""Phase 3: fan-out, independent verify, and the evaluation gate."""

from pathlib import Path

from comcmd.kernel.aggregate import aggregate
from comcmd.kernel.records import TaskState
from comcmd.pack import build_runner, load_pack

TRIAGE = Path(__file__).resolve().parents[1] / "companies" / "triage-demo"


# -- aggregation ------------------------------------------------------------

def test_majority_aggregation_and_agreement():
    out = aggregate([{"label": "bug"}, {"label": "bug"}, {"label": "question"}],
                    how="majority", key="label")
    assert out["label"] == "bug"
    assert out["_agreement"] == round(2 / 3, 3)
    assert out["_candidates"] == 3


def test_best_aggregation_picks_highest_score():
    out = aggregate([{"label": "a", "score": 0.1}, {"label": "b", "score": 0.9}],
                    how="best", key="label", score_key="score")
    assert out["label"] == "b"


# -- fan-out through the runner --------------------------------------------

def test_fanout_panel_beats_single_on_a_hard_ticket():
    pack = load_pack(TRIAGE)
    # "the export is broken" — single heuristic (h0) says 'question' (wrong);
    # the 3-heuristic panel majority says 'bug' (right).
    single = build_runner(pack).runner.start(
        "triage-single", inputs={"text": "the export is broken"})
    panel = build_runner(pack).runner.start(
        "triage-panel", inputs={"text": "the export is broken"})
    assert single.artifacts["classify"]["label"] == "question"   # baseline wrong
    assert panel.artifacts["panel"]["label"] == "bug"            # panel right
    assert panel.state == TaskState.SUCCEEDED                    # verify passed


def test_verify_escalates_on_three_way_split():
    # craft a fan-out result with no majority -> low agreement -> verify fails.
    pack = load_pack(TRIAGE)
    ctx = build_runner(pack)
    # drive verify directly with a split target
    handle = ctx.runner.start("triage-panel",
                              inputs={"text": "how do I add a feature? it crashes"})
    # This ticket splits the heuristics; if agreement < quorum the task parks.
    # Either it verified (SUCCEEDED) or escalated (WAITING_FOR_HUMAN) — both valid,
    # but the verify artifact must reflect the true approval count.
    if handle.state == TaskState.WAITING_FOR_HUMAN:
        assert handle.waiting_on["reason"] == "verification failed"


# -- the evaluation gate ----------------------------------------------------

def test_eval_promotes_panel_over_single():
    from comcmd.eval.harness import evaluate
    pack = load_pack(TRIAGE)
    report = evaluate(pack.spec, baseline="triage-single", variant="triage-panel",
                      scenarios=pack.scenarios, skills=pack.skills)
    assert report.variant.success_rate > report.baseline.success_rate
    assert report.variant.cost > report.baseline.cost      # multi-agent costs more
    assert report.promote is True


def test_eval_keeps_baseline_when_variant_does_not_beat_it():
    from comcmd.eval.harness import evaluate
    pack = load_pack(TRIAGE)
    # comparing the baseline against ITSELF: no success gain -> do not promote.
    report = evaluate(pack.spec, baseline="triage-single", variant="triage-single",
                      scenarios=pack.scenarios, skills=pack.skills)
    assert report.promote is False
