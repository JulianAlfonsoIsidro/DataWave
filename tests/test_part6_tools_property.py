"""Property-based tests that the assistant tools equal the webapp's own numbers.

# Feature: part6-assistant, Property 3: tool outputs equal the webapp's own numbers

Covers Property 3 of the part6-assistant spec (task 3.3): the four tools in
``assistant.tools`` are pure projections / re-runs of the existing
``webapp_core`` surfaces, so every number they surface must equal the webapp's
own number -- the assistant computes no campaign number itself (Requirements
2.2, 2.3, 2.4, 2.5).

Three independent checks, matched to the three computation styles:

- **get_card / compare_segments (Requirements 2.2, 2.3)** -- pure projections of
  ``run_result.cards``. Driven by a Hypothesis strategy that builds a lightweight
  fake run_result (``types.SimpleNamespace(cards=[...], promo_spec=...)``) whose
  cards carry the surfaced ``_CARD_FIELDS`` keys plus a ``segment`` *and* a
  ``client_id`` key. The property pins that each tool's ``data`` equals exactly
  the ``_CARD_FIELDS`` projection of the matching card(s), that an absent segment
  yields ``ok=False``, and that a ``client_id`` never crosses the boundary
  (Requirement 2.6).

- **what_if (Requirement 2.4)** -- a re-run with the replaced threshold. Built
  over the real reloaded Part 1 model and a tiny slice of the real ``data/``
  frames (so the run stays fast and hermetic), then for a few fixed thresholds
  the tool's ``totals_by_segment`` is checked to equal the ``_TOTAL_FIELDS``
  projection of an independent ``run_promo(replace(spec, threshold_php=t), ...)``
  over the same context.

- **past_promo_accuracy (Requirement 2.5)** -- equals ``predicted_vs_actual``.
  Reads the on-disk ``outputs/cards.json`` and ``data/promo_leads.csv`` exactly
  as the tool does and checks the tool's ``(segment, predicted, actual)`` rows
  for a real promo id (``P001``) equal those ``predicted_vs_actual`` returns.

The pipeline-backed checks guard on the real artifacts (``outputs/`` and
``data/``) and skip cleanly if any are missing, though they are expected to be
present. All money/count values generated for the pure projection are finite.
"""

from __future__ import annotations

import json
import math
import types
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from assistant.tools import (
    SEGMENT_LABELS,
    _CARD_FIELDS,
    _TOTAL_FIELDS,
    RunContext,
    compare_segments,
    get_card,
    past_promo_accuracy,
    what_if,
)

# Project paths: the real trained artifacts and the real data/ frames are the
# source for the pipeline-backed checks, resolved from this test file so the
# tests work regardless of the process cwd.
ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"
DATA_DIR = ROOT / "data"
LEADS_DIR = OUTPUTS_DIR / "leads"
CARDS_JSON_PATH = OUTPUTS_DIR / "cards.json"
PROMO_LEADS_PATH = DATA_DIR / "promo_leads.csv"


# ---------------------------------------------------------------------------
# get_card / compare_segments: pure projections of run_result.cards (2.2, 2.3)
# ---------------------------------------------------------------------------

# A segment pool mixing the four real labels with a couple of stray labels that
# compare_segments must drop (not in SEGMENT_LABELS) and get_card can miss.
_SEGMENT_POOL = SEGMENT_LABELS + ["Stray Segment", "Another Stray"]


def _finite_number() -> st.SearchStrategy:
    """Finite numbers (ints or floats) for the surfaced card totals."""
    return st.one_of(
        st.integers(min_value=0, max_value=10_000),
        st.floats(
            min_value=0.0,
            max_value=1_000_000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )


@st.composite
def _card(draw: st.DrawFn, segment: str) -> dict:
    """One card dict carrying every surfaced field plus segment and client_id.

    The card is intentionally richer than the surfaced projection: it carries a
    ``client_id`` (and a stray ``n_clients`` key) that the tools must never copy
    into their ``data`` (Requirement 2.6).
    """
    card = {
        "segment": segment,
        # Individual-client data that must never cross the tool boundary.
        "client_id": draw(st.text(min_size=1, max_size=8)),
        "n_clients": draw(st.integers(min_value=0, max_value=5000)),
        "action": draw(st.sampled_from(["Include", "Offer lower tier", "Skip"])),
        "dominant_channel": draw(st.sampled_from(["In-app", "Email", "SMS"])),
        "message_angle": draw(st.text(max_size=20)),
        "expected_joiners": draw(_finite_number()),
        "joiners_90_low": draw(_finite_number()),
        "joiners_90_high": draw(_finite_number()),
        "expected_value": draw(_finite_number()),
        "top_drivers": draw(
            st.lists(st.text(min_size=1, max_size=10), max_size=3)
        ),
        "excluded_by_reason": draw(
            st.dictionaries(
                st.text(min_size=1, max_size=10),
                st.integers(min_value=0, max_value=100),
                max_size=3,
            )
        ),
    }
    return card


@st.composite
def _fake_run_result(draw: st.DrawFn) -> types.SimpleNamespace:
    """A fake run_result with a .cards list over a subset of distinct segments.

    Shaped like :class:`webapp_core.run_promo.RunResult` for the two card tools'
    purposes: it exposes a ``.cards`` list (one card per distinct segment drawn)
    and a ``.promo_spec`` placeholder. Segments are unique so each label maps to
    at most one card, matching how a real run carries one card per populated
    ``(promo_id, segment)`` cell.
    """
    segments = draw(
        st.lists(
            st.sampled_from(_SEGMENT_POOL),
            min_size=0,
            max_size=len(_SEGMENT_POOL),
            unique=True,
        )
    )
    cards = [draw(_card(segment)) for segment in segments]
    return types.SimpleNamespace(cards=cards, promo_spec=None)


def _expected_projection(card: dict) -> dict:
    """The exact surfaced projection the card tools must produce for a card."""
    return {field: card.get(field) for field in _CARD_FIELDS}


@settings(max_examples=200)
@given(_fake_run_result())
def test_get_card_mirrors_run_result_cards(run_result):
    """get_card equals the _CARD_FIELDS projection of run_result.cards (Req 2.2).

    For every segment present in the run, ``get_card`` returns ``ok=True`` and
    its ``data`` equals exactly the surfaced projection of that card and carries
    no ``client_id``. For a segment with no card it returns ``ok=False`` with no
    data. Never leaks individual client data (Requirement 2.6).

    **Validates: Requirements 2.2**
    """
    present = {card["segment"]: card for card in run_result.cards}

    for segment in _SEGMENT_POOL:
        result = get_card(segment, run_result)
        assert result.tool_name == "get_card"
        assert "client_id" not in result.data
        if segment in present:
            assert result.ok is True
            assert result.data == _expected_projection(present[segment])
        else:
            assert result.ok is False
            assert result.data == {}


@settings(max_examples=200)
@given(_fake_run_result())
def test_compare_segments_mirrors_run_result_cards(run_result):
    """compare_segments equals the per-segment projection of the cards (Req 2.3).

    The result is ``ok=True`` and its ``data`` maps every card whose segment is a
    real Segment_Label to exactly that card's surfaced projection; stray-segment
    cards are dropped, and no ``client_id`` appears anywhere in the output
    (Requirement 2.6).

    **Validates: Requirements 2.3**
    """
    result = compare_segments(run_result)
    assert result.tool_name == "compare_segments"
    assert result.ok is True

    expected = {
        card["segment"]: _expected_projection(card)
        for card in run_result.cards
        if card["segment"] in SEGMENT_LABELS
    }
    assert result.data == expected

    # No individual client data ever crosses the boundary (Requirement 2.6):
    # the surfaced projection carries exactly the _CARD_FIELDS keys and never a
    # client_id key, for every segment.
    for per_segment in result.data.values():
        assert "client_id" not in per_segment
        assert set(per_segment) == set(_CARD_FIELDS)


# ---------------------------------------------------------------------------
# what_if: a re-run with the replaced threshold (Requirement 2.4)
# ---------------------------------------------------------------------------

_ARTIFACTS_PRESENT = (
    (OUTPUTS_DIR / "model_part1.calibrated.pkl").exists()
    and (DATA_DIR / "customer_dna.csv").exists()
    and (DATA_DIR / "adb_monthly.csv").exists()
    and (OUTPUTS_DIR / "features_part2.csv").exists()
)


def _tiny_context_and_run():
    """Build a RunContext over a tiny real audience and a base RunResult.

    Loads the real Part 1 model and config and a tiny slice (<=15 clients) of
    the real ``data/`` frames -- the same restriction the Part 5 run_promo smoke
    test uses -- so both the base run and every what_if re-run stay fast. The
    RunContext carries this *restricted* data bundle, so what_if re-runs over the
    identical audience, letting the equality check isolate the threshold change.
    """
    from part1_optin.config import Config as Part1Config
    from webapp_core.model_io import load_model
    from webapp_core.run_promo import PromoSpec, run_promo

    model = load_model(OUTPUTS_DIR)
    config = Part1Config()

    customer_dna = pd.read_csv(DATA_DIR / "customer_dna.csv")
    adb_monthly = pd.read_csv(DATA_DIR / "adb_monthly.csv")
    features = pd.read_csv(OUTPUTS_DIR / "features_part2.csv")

    tiny_ids = (
        customer_dna.loc[
            customer_dna["segment"] == "Affluent-Gold", "client_id"
        ]
        .head(15)
        .tolist()
    )
    assert tiny_ids, "expected some Affluent-Gold clients in the fixture data"

    data = {
        "customer_dna": customer_dna[customer_dna["client_id"].isin(tiny_ids)],
        "adb_monthly": adb_monthly[adb_monthly["client_id"].isin(tiny_ids)],
        "features": features[features["client_id"].isin(tiny_ids)],
    }

    spec = PromoSpec(
        promo_id="NEW-001",
        product_type="Savings",
        mechanic="TOP_UP",
        threshold_php=100_000.0,
        reward="Bonus interest",
        eligible_segments=["Affluent-Gold"],
        min_adb=0.0,
        channels=["In-app", "Email", "SMS"],
    )

    base_result = run_promo(spec, model=model, config=config, data=data)
    context = RunContext(model=model, config=config, data=data)
    return context, base_result, run_promo


@pytest.mark.skipif(
    not _ARTIFACTS_PRESENT,
    reason="model/data artifacts under outputs/ and data/ are required",
)
@pytest.mark.parametrize("threshold", [50_000.0, 100_000.0, 250_000.0])
def test_what_if_equals_rerun_with_replaced_threshold(threshold):
    """what_if totals equal a direct run_promo re-run at that threshold (Req 2.4).

    For a fixed tiny audience, ``what_if(t, rr, ctx).data["totals_by_segment"]``
    must equal the ``_TOTAL_FIELDS`` projection of
    ``run_promo(replace(spec, threshold_php=t), ...).cards`` computed
    independently over the same RunContext -- the tool adds no number of its own.

    **Validates: Requirements 2.4**
    """
    context, base_result, run_promo = _tiny_context_and_run()

    result = what_if(threshold, base_result, context)
    assert result.tool_name == "what_if"
    assert result.ok is True
    assert result.data["threshold_php"] == float(threshold)

    # Independent re-run with only the threshold replaced.
    rerun = run_promo(
        replace(base_result.promo_spec, threshold_php=float(threshold)),
        model=context.model,
        config=context.config,
        data=context.data,
    )
    expected_totals = {
        card["segment"]: {field: card.get(field) for field in _TOTAL_FIELDS}
        for card in rerun.cards
        if card.get("segment") in SEGMENT_LABELS
    }

    assert result.data["totals_by_segment"] == expected_totals
    # No individual client data crosses the boundary: each per-segment total
    # carries exactly the _TOTAL_FIELDS keys and never a client_id (Req 2.6).
    for per_segment in result.data["totals_by_segment"].values():
        assert "client_id" not in per_segment
        assert set(per_segment) == set(_TOTAL_FIELDS)


# ---------------------------------------------------------------------------
# past_promo_accuracy: equals predicted_vs_actual (Requirement 2.5)
# ---------------------------------------------------------------------------

_PAST_ARTIFACTS_PRESENT = CARDS_JSON_PATH.exists() and PROMO_LEADS_PATH.exists()


def _nan_safe(value):
    """A comparison-stable key for a float-or-NaN rate (NaN == NaN here)."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return "nan"
    return value


@pytest.mark.skipif(
    not _PAST_ARTIFACTS_PRESENT,
    reason="outputs/cards.json and data/promo_leads.csv are required",
)
@pytest.mark.parametrize("promo_id", ["P001"])
def test_past_promo_accuracy_equals_predicted_vs_actual(promo_id):
    """past_promo_accuracy rows equal predicted_vs_actual for that id (Req 2.5).

    Reads the on-disk ``outputs/cards.json`` and ``data/promo_leads.csv`` exactly
    as the tool does, computes ``predicted_vs_actual`` the same way, and checks
    the tool's ``(segment, predicted, actual)`` rows equal the corresponding rows
    for ``promo_id`` -- the tool adds no number of its own. Never leaks a
    ``client_id`` (Requirement 2.6).

    **Validates: Requirements 2.5**
    """
    from webapp_core.past_promos import (
        predicted_vs_actual,
        read_sendable_ids_by_cell,
    )

    with open(CARDS_JSON_PATH, encoding="utf-8") as fh:
        cards = json.load(fh)
    promo_leads = pd.read_csv(PROMO_LEADS_PATH)

    sendable_ids_by_cell = read_sendable_ids_by_cell(cards, leads_dir=LEADS_DIR)
    expected_rows = [
        {
            "segment": str(row["segment"]),
            "predicted": row["predicted"],
            "actual": row["actual"],
        }
        for row in predicted_vs_actual(cards, promo_leads, sendable_ids_by_cell)
        if str(row["promo_id"]) == promo_id
    ]
    assert expected_rows, f"expected some {promo_id} rows in the fixture data"

    result = past_promo_accuracy(promo_id)
    assert result.tool_name == "past_promo_accuracy"
    assert result.ok is True
    assert result.data["promo_id"] == promo_id

    # Compare as segment -> (predicted, actual), NaN-safe, order-independent.
    def _as_map(rows):
        return {
            row["segment"]: (_nan_safe(row["predicted"]), _nan_safe(row["actual"]))
            for row in rows
        }

    assert _as_map(result.data["segments"]) == _as_map(expected_rows)
    # No individual client data crosses the boundary: each surfaced row carries
    # exactly segment/predicted/actual and never a client_id (Req 2.6).
    for row in result.data["segments"]:
        assert "client_id" not in row
        assert set(row) == {"segment", "predicted", "actual"}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
