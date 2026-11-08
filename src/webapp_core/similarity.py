"""Deterministic Similarity_Score between a New Promo and a past campaign.

Eight components, each a pure function of the two profiles, are scored as a
fraction in [0, 1] times a weight (Requirements 11.8, 11.9). A component that
cannot be computed is "Unavailable" (``fraction is None``); the remaining
weights are rescaled so the available maximum points sum to 100
(Requirement 11.11). When no component is available the score is ``None``
("Not Enough Data", Requirement 11.12).

This module is pure: it imports no Streamlit, AWS, LLM, embedding, or network
code (Requirement 11.19).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Mapping

# Requirement 11.9: fixed weights, sum 100.
WEIGHTS: dict[str, float] = {
    "audience": 30,
    "need": 20,
    "product_mechanic": 15,
    "economics": 10,
    "duration": 10,
    "channels": 5,
    "objective": 5,
    "name_summary": 5,
}

# Fixed display/evaluation order of the eight components.
COMPONENT_KEYS: tuple[str, ...] = tuple(WEIGHTS)

# The form's product names map onto the history's product types.
_PRODUCT_ALIASES: dict[str, str] = {
    "savings": "deposit",
    "time deposit": "deposit",
    "deposit": "deposit",
}

# Fixed keyword lexicon: need tag -> trigger substrings (lower-case).
_NEED_LEXICON: dict[str, tuple[str, ...]] = {
    "save": ("saving", "savings", "deposit", "time deposit", "balance", "adb", "grow"),
    "spend": ("spend", "card", "purchase", "cashback", "shopping", "debit", "credit"),
    "borrow": ("loan", "borrow", "credit line", "lending"),
    "invest": ("invest", "fund", "bond", "uitf", "wealth"),
    "protect": ("insurance", "protect", "secure"),
    "transfer": ("transfer", "remit", "payroll", "salary", "inflow", "outflow"),
    "engage": ("app", "digital", "mobile", "engage", "activate", "onboard", "bonus"),
}

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
        "is", "it", "of", "on", "or", "the", "to", "with", "your", "you", "our",
        "this", "that", "promo", "campaign",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class NewPromoProfile:
    """New Promo fields used for similarity (None / empty means missing)."""

    name: str | None = None
    summary: str | None = None
    objective: str | None = None
    product_type: str | None = None
    mechanic: str | None = None
    threshold_php: float | None = None
    eligible_segments: tuple[str, ...] = ()
    channels: tuple[str, ...] = ()
    start: date | None = None
    end: date | None = None


@dataclass(frozen=True)
class CampaignProfile:
    """A past campaign's facts used for similarity and display."""

    promo_id: str
    name: str
    product_type: str
    mechanic: str
    threshold_php: float | None
    reward: str
    start: date | None
    end: date | None
    channels: tuple[str, ...]
    audience_segments: tuple[str, ...]
    opt_in_rate: float | None
    treated_leads: int


@dataclass(frozen=True)
class ComponentScore:
    key: str
    fraction: float | None  # None means Unavailable
    weight: float  # rescaled so available weights sum to 100
    points: float | None  # fraction * weight
    max_points: float | None  # weight, None when unavailable


@dataclass(frozen=True)
class SimilarityResult:
    components: tuple[ComponentScore, ...]
    score: float | None  # 0 to 100, None means Not Enough Data


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def duration_days(start: date, end: date) -> int:
    """Inclusive day count: the same day gives 1."""
    return (end - start).days + 1


def rescale_weights(available: Mapping[str, bool]) -> dict[str, float]:
    """Rescale base weights of available components so they sum to 100.

    Unavailable components get weight 0. If none is available, all are 0.
    """
    total = sum(WEIGHTS[k] for k in WEIGHTS if available.get(k, False))
    if total <= 0:
        return {k: 0.0 for k in WEIGHTS}
    factor = 100.0 / total
    return {
        k: (WEIGHTS[k] * factor if available.get(k, False) else 0.0)
        for k in WEIGHTS
    }


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _norm_set(values: tuple[str, ...]) -> frozenset[str]:
    return frozenset(v.strip().lower() for v in values if v and v.strip())


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float | None:
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def _tokens(text: str | None) -> frozenset[str]:
    words = _WORD_RE.findall(_norm(text))
    return frozenset(w for w in words if w not in _STOP_WORDS)


def _need_tags(*texts: str | None) -> frozenset[str]:
    blob = " ".join(_norm(t) for t in texts if t)
    return frozenset(
        tag
        for tag, words in _NEED_LEXICON.items()
        if any(w in blob for w in words)
    )


def _product(value: str | None) -> str:
    v = _norm(value)
    return _PRODUCT_ALIASES.get(v, v)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


# --------------------------------------------------------------------------
# Component fractions (None = Unavailable)
# --------------------------------------------------------------------------

def _audience(cur: NewPromoProfile, past: CampaignProfile) -> float | None:
    return _jaccard(_norm_set(cur.eligible_segments), _norm_set(past.audience_segments))


def _need(cur: NewPromoProfile, past: CampaignProfile) -> float | None:
    a = _need_tags(cur.product_type, cur.mechanic, cur.objective)
    b = _need_tags(past.product_type, past.mechanic, past.reward)
    return _jaccard(a, b)


def _product_mechanic(cur: NewPromoProfile, past: CampaignProfile) -> float | None:
    cp, cm = _product(cur.product_type), _norm(cur.mechanic)
    pp, pm = _product(past.product_type), _norm(past.mechanic)
    if (not cp and not cm) or (not pp and not pm):
        return None
    score = 0.0
    if cp and pp and cp == pp:
        score += 0.5
    if cm and pm and cm == pm:
        score += 0.5
    return score


def _economics(cur: NewPromoProfile, past: CampaignProfile) -> float | None:
    a, b = cur.threshold_php, past.threshold_php
    if a is None or b is None or a != a or b != b or a <= 0 or b <= 0:
        return None
    return min(a, b) / max(a, b)


def _duration(cur: NewPromoProfile, past: CampaignProfile) -> float | None:
    if cur.start is None or cur.end is None or past.start is None or past.end is None:
        return None
    d1 = duration_days(cur.start, cur.end)
    d2 = duration_days(past.start, past.end)
    if d1 <= 0 or d2 <= 0:
        return None
    return min(d1, d2) / max(d1, d2)


def _channels(cur: NewPromoProfile, past: CampaignProfile) -> float | None:
    return _jaccard(_norm_set(cur.channels), _norm_set(past.channels))


def _objective(cur: NewPromoProfile, past: CampaignProfile) -> float | None:
    if not _norm(cur.objective):
        return None
    return _jaccard(_need_tags(cur.objective), _need_tags(past.name, past.reward))


def _name_summary(cur: NewPromoProfile, past: CampaignProfile) -> float | None:
    return _jaccard(
        _tokens(f"{cur.name or ''} {cur.summary or ''}"),
        _tokens(f"{past.name or ''} {past.reward or ''}"),
    )


_FRACTION_FUNCS = {
    "audience": _audience,
    "need": _need,
    "product_mechanic": _product_mechanic,
    "economics": _economics,
    "duration": _duration,
    "channels": _channels,
    "objective": _objective,
    "name_summary": _name_summary,
}


def similarity(current: NewPromoProfile, past: CampaignProfile) -> SimilarityResult:
    """Score how similar a past campaign is to the New Promo (0 to 100)."""
    fractions: dict[str, float | None] = {}
    for key in COMPONENT_KEYS:
        f = _FRACTION_FUNCS[key](current, past)
        fractions[key] = None if f is None else _clamp(f)

    weights = rescale_weights({k: f is not None for k, f in fractions.items()})

    components: list[ComponentScore] = []
    total = 0.0
    any_available = False
    for key in COMPONENT_KEYS:
        f = fractions[key]
        if f is None:
            components.append(ComponentScore(key, None, 0.0, None, None))
            continue
        any_available = True
        w = weights[key]
        pts = f * w
        total += pts
        components.append(ComponentScore(key, f, w, pts, w))

    score = max(0.0, min(100.0, total)) if any_available else None
    return SimilarityResult(components=tuple(components), score=score)
