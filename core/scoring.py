"""Priority score, 0..100, explainable (statement 3.1 "Priority scoring").

  S = severity / 5                                   how bad
  P = ln(1 + people) / ln(1 + P_REF), max 1          how many (log-damped for fairness)
  F = servings_remaining / F_REF, max 1              how much food is still missing
  C = category weight (hospital 1.0, shelter 0.9, community 0.7, other 0.5)
  D = 1 - clamp((deadline - now - travel_eta) / H, 0, 1)   time pressure, travel included
  W = minutes_waiting / AGING_CAP, max 1             anti-starvation (waiting-time adjustment)
  score = 100 * sum(weight_k * term_k)

A deadline we cannot meet is not a filter: D becomes 1 and the ticket is flagged "at_risk".
We still deliver late rather than drop people.

AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from core.constants import (AGING_CAP_MIN, CATEGORY_DEFAULT, CATEGORY_WEIGHT, F_REF, H_MIN, P_REF,
                            SCORE_TERMS, SEVERITY_MAX)


@dataclass(frozen=True)
class Score:
    value: float                  # 0..100
    breakdown: dict[str, float]   # points contributed by each term; sums to value
    terms: dict[str, float]       # raw term values, each 0..1
    flags: tuple[str, ...]        # at_risk, no_route, eta_unknown, unknown category


def check_weights(weights: dict[str, float]) -> None:
    if set(weights) != set(SCORE_TERMS):
        raise ValueError(f"weights must have exactly {SCORE_TERMS}, got {sorted(weights)}")
    if any(w < 0 for w in weights.values()) or abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError(f"weights must be >= 0 and sum to 1.0, got {weights}")


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def score_ticket(ticket: dict, category: str, now: datetime, best_eta_min: float | None,
                 servings_remaining: int, weights: dict[str, float]) -> Score:
    """ticket: a validated tickets row. best_eta_min: minutes for the fastest feasible
    truck->supplier->requester trip; None = not computed yet, math.inf = no route."""
    check_weights(weights)
    if servings_remaining < 0:
        raise ValueError(f"servings_remaining must be >= 0, got {servings_remaining}")
    flags: list[str] = []

    s = ticket["severity"] / SEVERITY_MAX
    p = min(1.0, math.log1p(ticket["people_affected"]) / math.log1p(P_REF))
    f = min(1.0, servings_remaining / F_REF)
    if category in CATEGORY_WEIGHT:
        c = CATEGORY_WEIGHT[category]
    else:
        c = CATEGORY_DEFAULT
        flags.append(f"category {category!r} not in table: weight {CATEGORY_DEFAULT}")

    minutes_left = (ticket["deadline"] - now).total_seconds() / 60.0
    if best_eta_min is None:
        slack = minutes_left
        flags.append("eta_unknown")
    elif math.isinf(best_eta_min):
        slack = -math.inf
        flags.append("no_route")
    else:
        slack = minutes_left - best_eta_min
    if slack < 0:
        flags.append("at_risk")
    d = 1.0 - _clamp(slack / H_MIN, 0.0, 1.0)

    waited = max(0.0, (now - ticket["created_at"]).total_seconds() / 60.0)
    w = min(1.0, waited / AGING_CAP_MIN)

    terms = {"S": s, "P": p, "F": f, "C": c, "D": d, "W": w}
    breakdown = {k: 100.0 * weights[k] * terms[k] for k in SCORE_TERMS}
    return Score(sum(breakdown.values()), breakdown, terms, tuple(flags))
