"""Who is being targeted, and how sure the forecast looks (Part 9 round 3).

Pure, read-only, no Streamlit (spec part9-layout-fixes, Requirement 38). It
changes no model, score or segment; it only compares counts that exist.

- :func:`group_shares` compares each group's share of the eligible clients
  with its share of the sendable leads, for one profile column (age band,
  region, socio-economic class). A group whose share moves by
  :data:`FLAG_GAP_PTS` points or more is flagged.
- :func:`past_join_rates` gives, for the past promos, the predicted join rate
  (mean ``p_join`` from ``outputs/scores.csv``) and the actual join rate of
  treated leads, by group.
- :func:`forecast_caution` returns a short note when a run's expected join
  rate is at least :data:`CAUTION_FACTOR` times the historical rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

GROUP_COLUMNS: tuple[tuple[str, str], ...] = (
    ("age_band", "Age Band"),
    ("region", "Region"),
    ("sec_class", "Socio-Economic Class"),
)
FLAG_GAP_PTS = 10.0
CAUTION_FACTOR = 2.0


@dataclass(frozen=True)
class GroupShare:
    group: str
    eligible: int
    sendable: int
    eligible_pct: float
    sendable_pct: float

    @property
    def gap_pts(self) -> float:
        return self.sendable_pct - self.eligible_pct

    @property
    def flagged(self) -> bool:
        return abs(self.gap_pts) >= FLAG_GAP_PTS


def _ids(values: Iterable) -> set[str]:
    return {str(v) for v in values}


def group_shares(dna: pd.DataFrame, eligible_ids: Iterable, sendable_ids: Iterable,
                 column: str) -> list[GroupShare]:
    """Each group's share of the eligible clients and of the sendable leads."""
    if column not in dna.columns or "client_id" not in dna.columns:
        return []
    lookup = dict(zip(dna["client_id"].astype(str), dna[column].astype(str)))
    eligible = [lookup.get(i) for i in _ids(eligible_ids)]
    sendable = [lookup.get(i) for i in _ids(sendable_ids)]
    eligible = [g for g in eligible if g is not None]
    sendable = [g for g in sendable if g is not None]
    e_total, s_total = len(eligible), len(sendable)
    out = []
    for group in sorted(set(eligible) | set(sendable)):
        e, s = eligible.count(group), sendable.count(group)
        out.append(GroupShare(
            group, e, s,
            e / e_total * 100 if e_total else 0.0,
            s / s_total * 100 if s_total else 0.0,
        ))
    return out


@dataclass(frozen=True)
class PastRate:
    group: str
    leads: int
    predicted_pct: float | None
    actual_pct: float | None


def past_join_rates(dna: pd.DataFrame, promo_leads: pd.DataFrame, scores: pd.DataFrame | None,
                    column: str) -> list[PastRate]:
    """Predicted (mean p_join) and actual join rate of treated past leads, by group."""
    need = {"client_id", "promo_id", "control_group", "joined"}
    if column not in dna.columns or not need <= set(promo_leads.columns):
        return []
    treated = promo_leads[promo_leads["control_group"] == 0][["promo_id", "client_id", "joined"]].copy()
    treated["client_id"] = treated["client_id"].astype(str)
    groups = dna[["client_id", column]].copy()
    groups["client_id"] = groups["client_id"].astype(str)
    frame = treated.merge(groups, on="client_id", how="left")
    if scores is not None and {"promo_id", "client_id", "p_join"} <= set(scores.columns):
        s = scores[["promo_id", "client_id", "p_join"]].copy()
        s["client_id"] = s["client_id"].astype(str)
        frame = frame.merge(s, on=["promo_id", "client_id"], how="left")
    out = []
    for group, part in frame.groupby(column, dropna=True):
        predicted = part["p_join"].mean() * 100 if "p_join" in part and part["p_join"].notna().any() else None
        out.append(PastRate(str(group), int(len(part)), predicted, float(part["joined"].mean() * 100)))
    return sorted(out, key=lambda r: r.group)


def historical_join_rate(promo_leads: pd.DataFrame) -> float | None:
    """Join rate of treated past leads, as a fraction (None when unknown)."""
    if not {"control_group", "joined"} <= set(promo_leads.columns):
        return None
    treated = promo_leads[promo_leads["control_group"] == 0]
    return float(treated["joined"].mean()) if len(treated) else None


def forecast_caution(forecast: float, sendable: int, historical: float | None,
                     factor: float = CAUTION_FACTOR) -> str | None:
    """A plain caution when the run's expected join rate looks far above history."""
    if not sendable or historical is None or historical <= 0:
        return None
    rate = forecast / sendable
    if rate < historical * factor:
        return None
    return (
        f"This run expects {rate * 100:.1f}% of sendable leads to join, more than "
        f"{factor:g} times the {historical * 100:.1f}% that joined past promos. "
        "Treat the forecast with care."
    )
