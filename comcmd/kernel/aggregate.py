"""Typed aggregation of fan-out candidate artifacts.

Deterministic: results are aggregated independent of completion order. Ties in
'majority' break toward the value seen at the lowest candidate index (stable).
"""

from __future__ import annotations

from typing import Any


def aggregate(candidates: list[dict], *, how: str, key: str,
              score_key: str = "score") -> dict[str, Any]:
    """Combine candidate artifacts into one, plus vote metadata.

    Returns {**winner, "_votes": {...}, "_agreement": float, "_candidates": n}.
    """
    candidates = [c for c in candidates if isinstance(c, dict)]
    n = len(candidates)
    if n == 0:
        return {"_votes": {}, "_agreement": 0.0, "_candidates": 0}

    if how == "first":
        winner = candidates[0]
        agreement = 1.0
        votes = {}
    elif how == "best":
        winner = max(candidates, key=lambda c: c.get(score_key, float("-inf")))
        agreement = 1.0
        votes = {}
    else:  # majority
        votes: dict[Any, int] = {}
        for c in candidates:
            v = c.get(key)
            votes[v] = votes.get(v, 0) + 1
        # highest count; stable tie-break by first-seen candidate order
        order = []
        for c in candidates:
            if c.get(key) not in order:
                order.append(c.get(key))
        best_val = max(order, key=lambda v: (votes[v], -order.index(v)))
        winner = next(c for c in candidates if c.get(key) == best_val)
        agreement = round(votes[best_val] / n, 3)
        votes = {str(k): v for k, v in votes.items()}

    return {**winner, "_votes": votes, "_agreement": agreement, "_candidates": n}
