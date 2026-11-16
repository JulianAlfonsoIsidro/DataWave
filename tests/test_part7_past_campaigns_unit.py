# -*- coding: utf-8 -*-
"""Unit tests for the smarter Past Promos logic (part7, task 16.5).

Covers inclusive duration, weights, Unavailable components, the opt-in
division guard, paging, sort/filter behavior, and missing-file errors.

**Validates: Requirements 11.3, 11.5, 11.6, 11.7, 11.10, 11.16, 11.18**
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from webapp_core import past_campaigns as pc
from webapp_core.similarity import (
    COMPONENT_KEYS,
    WEIGHTS,
    CampaignProfile,
    NewPromoProfile,
    duration_days,
    rescale_weights,
    similarity,
)


def _profile(pid: str, start: date | None, product: str = "Deposit") -> CampaignProfile:
    return CampaignProfile(
        promo_id=pid, name=f"Promo {pid}", product_type=product, mechanic="Bonus",
        threshold_php=1000.0, reward="Cash", start=start, end=start,
        channels=("SMS",), audience_segments=("Ready Toppers",),
        opt_in_rate=0.1, treated_leads=10,
    )


def _rows(n: int, with_sim: bool = False) -> list[pc.CampaignRow]:
    cur = NewPromoProfile(product_type="Deposit", mechanic="Bonus") if with_sim else None
    profiles = [_profile(f"P{i:03d}", date(2024, 1, 1 + i)) for i in range(n)]
    return pc.build_rows(profiles, cur)


# ---- duration / weights ---------------------------------------------------

def test_same_day_duration_is_one():
    assert duration_days(date(2024, 3, 5), date(2024, 3, 5)) == 1


def test_duration_is_inclusive():
    assert duration_days(date(2024, 3, 1), date(2024, 3, 10)) == 10


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100
    assert len(COMPONENT_KEYS) == 8


def test_rescaled_weights_sum_to_100():
    w = rescale_weights({"audience": True, "channels": True})
    assert sum(w.values()) == pytest.approx(100.0)
    assert w["need"] == 0.0


# ---- Unavailable rendering -----------------------------------------------

def test_unavailable_component_has_no_fraction_or_points():
    cur = NewPromoProfile(product_type="Deposit", mechanic="Bonus")
    result = similarity(cur, _profile("P001", date(2024, 1, 1)))
    by_key = {c.key: c for c in result.components}
    assert by_key["economics"].fraction is None
    assert by_key["economics"].points is None
    assert by_key["economics"].max_points is None
    assert by_key["product_mechanic"].fraction is not None
    assert result.score == pytest.approx(100.0)


def test_no_available_component_is_not_enough_data():
    result = similarity(NewPromoProfile(), _profile("P001", date(2024, 1, 1)))
    assert result.score is None
    assert pc.display_score(result) == pc.NOT_ENOUGH_DATA


# ---- opt-in division guard -----------------------------------------------

def test_opt_in_not_available_with_zero_treated_leads():
    leads = pd.DataFrame({
        "promo_id": ["P001", "P001"], "client_id": ["a", "b"],
        "control_group": [1, 1], "joined": [1, 0],
    })
    rate, treated, joined = pc.opt_in_rate(leads)
    assert (rate, treated, joined) == (None, 0, 0)
    assert pc.format_opt_in(rate) == pc.NOT_AVAILABLE


def test_opt_in_rate_over_treated_only():
    leads = pd.DataFrame({
        "promo_id": ["P001"] * 3, "client_id": ["a", "b", "c"],
        "control_group": [0, 0, 1], "joined": [1, 0, 1],
    })
    rate, treated, joined = pc.opt_in_rate(leads)
    assert (treated, joined) == (2, 1)
    assert pc.format_opt_in(rate) == "50.0%"


def test_campaign_detail_guard_with_zero_treated():
    row = pc.CampaignRow(_profile("P001", date(2024, 1, 1)))
    leads = pd.DataFrame({
        "promo_id": ["P001"], "client_id": ["a"], "control_group": [1], "joined": [1],
    })
    detail = pc.campaign_detail(row, leads, pd.DataFrame(columns=["client_id", "segment"]))
    assert detail.opt_in_rate is None
    assert detail.opt_in_display == pc.NOT_AVAILABLE
    assert detail.duration_days == 1


# ---- paging ---------------------------------------------------------------

def test_paging_5_then_10_then_end_hides_view_more():
    rows = _rows(8)
    visible = pc.INITIAL_VISIBLE
    shown, more = pc.page(rows, visible)
    assert len(shown) == 5 and more is True

    visible = pc.next_visible(visible)
    assert visible == 10
    shown, more = pc.page(rows, visible)
    assert len(shown) == 8 and more is False


def test_view_more_hidden_when_exactly_five():
    shown, more = pc.page(_rows(5), pc.INITIAL_VISIBLE)
    assert len(shown) == 5 and more is False


def test_reset_on_sort_or_filter_change():
    rows = _rows(12)
    visible = pc.next_visible(pc.INITIAL_VISIBLE)  # user clicked View More
    assert len(pc.page(rows, visible)[0]) == 10

    # Changing sort/filter re-pages from INITIAL_VISIBLE over the new list.
    resorted = pc.sort_campaigns(rows, pc.SORT_OLDEST)
    shown, more = pc.page(resorted, pc.INITIAL_VISIBLE)
    assert len(shown) == 5 and more is True

    filtered = pc.filter_campaigns(rows, product_type="Loan")
    shown, more = pc.page(filtered, pc.INITIAL_VISIBLE)
    assert shown == [] and more is False


# ---- sorting --------------------------------------------------------------

def test_default_newest_first():
    out = pc.sort_campaigns(_rows(4))
    assert [r.profile.promo_id for r in out] == ["P003", "P002", "P001", "P000"]


def test_most_similar_unavailable_without_score_falls_back_to_newest():
    rows = _rows(4, with_sim=False)
    assert pc.similarity_available(rows) is False
    out = pc.sort_campaigns(rows, pc.SORT_MOST_SIMILAR)
    assert out == pc.sort_campaigns(rows, pc.SORT_NEWEST)


def test_most_similar_available_with_score():
    rows = _rows(3, with_sim=True)
    assert pc.similarity_available(rows) is True


# ---- missing files --------------------------------------------------------

def _write_history(path):
    pd.DataFrame({
        "promo_id": ["P001"], "promo_name": ["A"], "start_date": ["2024-01-01"],
        "end_date": ["2024-01-02"],
    }).to_csv(path, index=False)


def test_missing_history_names_file(tmp_path):
    with pytest.raises(pc.PastCampaignsDataError) as exc:
        pc.load_promo_history(tmp_path / "promo_history.csv")
    assert "promo_history.csv" in str(exc.value)


def test_missing_leads_names_file_and_returns_no_partial_data(tmp_path):
    hist = tmp_path / "promo_history.csv"
    _write_history(hist)
    leads = tmp_path / "promo_leads.csv"
    with pytest.raises(pc.PastCampaignsDataError) as exc:
        pc.load_all(hist, leads, tmp_path / "customer_dna.csv")
    assert "promo_leads.csv" in str(exc.value)
    assert exc.value.path == leads


def test_missing_dna_is_tolerated(tmp_path):
    frame = pc.load_customer_dna(tmp_path / "customer_dna.csv")
    assert frame.empty
