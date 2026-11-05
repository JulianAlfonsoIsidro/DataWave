# Feature: persona-segmentation, Property 3: Persona mix sums to 100% per non-empty cell
"""Property-based test for the per-cell Persona_Mix sum (Property 3).

Covers Property 3 of the persona-segmentation spec: for every non-empty decision
card cell -- a cell whose ``(promo_id, segment_slug)`` has at least one lead with a
persona assignment -- the per-persona shares returned by
:func:`webapp_core.personas.persona_mix_by_cell` sum to 100.0 within
floating-point tolerance, and every such cell is marked ``available=True``
(Requirement 7.1). A cell with no persona assignment is marked ``available=False``
with empty ``shares`` and is therefore NOT asserted to sum to 100.

The test drives ``persona_mix_by_cell`` directly, since Property 3 is a property of
that pure function over *any* ``(labels, cards)`` pair, not of a real clustering
run. Each example generates:

- a set of ``(promo_id, segment_slug)`` cells, some populated with a random number
  of leads assigned to a random set of personas, some left empty (no leads); and
- one card per cell whose ``segment`` is set to the cell's slug itself. Because
  :func:`webapp_core.personas.segment_slug` is idempotent on an already-slugged
  string (``segment_slug(slug) == slug``), the card slugs to the same key the
  labels carry, so the mix lines up per cell.

Including empty cells exercises the ``available=False`` branch and confirms it is
never asserted to sum to 100.

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path`` (never hardcoded here).
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from webapp_core.personas import (
    MIX_TOTAL_PERCENT,
    PersonaMix,
    persona_mix_by_cell,
    segment_slug,
)

# A small pool of promo ids and already-slugged segment labels. Using slugs
# directly as the card segment means segment_slug(slug) == slug, so the card key
# matches the labels' segment_slug cell key with no extra plumbing.
_PROMO_IDS = ["P001", "P002", "P003"]
_SEGMENT_SLUGS = [
    "ready_toppers",
    "willing_but_stretched",
    "untapped_wealth",
    "not_now",
]

# A small persona-name vocabulary; a cell draws its present personas from this.
_PERSONA_NAMES = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]


@st.composite
def _labels_and_cards(draw):
    """Draw a coherent ``(labels, cards)`` pair with empty and non-empty cells.

    Returns a ``(labels, cards)`` tuple:

    - ``labels`` is a ``run_personas``-shaped per-lead frame with columns
      ``client_id``, ``persona_label``, ``promo_id`` and ``segment_slug``. Each
      non-empty cell contributes one row per assigned lead; empty cells contribute
      no rows. Some leads may carry an empty ``persona_label`` (an out-of-pool
      campaign lead) which must not contribute to any cell's mix.
    - ``cards`` is a list of one card dict per cell, each carrying ``promo_id`` and
      ``segment`` where ``segment`` is the cell's slug itself (so it slugs to the
      same key the labels carry).

    The whole-empty case (no cells at all / all cells empty) is reachable so the
    empty-frame and all-``available=False`` paths are exercised.
    """
    # Distinct (promo_id, segment_slug) cells.
    cell_space = [
        (promo_id, slug) for promo_id in _PROMO_IDS for slug in _SEGMENT_SLUGS
    ]
    n_cells = draw(st.integers(min_value=0, max_value=len(cell_space)))
    cells = draw(
        st.lists(
            st.sampled_from(cell_space),
            min_size=n_cells,
            max_size=n_cells,
            unique=True,
        )
    )

    rows: list[dict] = []
    cards: list[dict] = []
    client_counter = 0

    for promo_id, slug in cells:
        # One card per cell; segment is the slug itself so segment_slug(seg)==slug.
        cards.append({"promo_id": promo_id, "segment": slug})

        # Draw how many leads land in this cell (0 => an empty cell).
        n_leads = draw(st.integers(min_value=0, max_value=8))
        for _ in range(n_leads):
            client_counter += 1
            # Most leads get a real persona; some get an empty label (out-of-pool)
            # which must not contribute to the mix.
            persona = draw(
                st.one_of(st.sampled_from(_PERSONA_NAMES), st.just(""))
            )
            rows.append(
                {
                    "client_id": f"C{client_counter:05d}",
                    "persona_label": persona,
                    "promo_id": promo_id,
                    "segment_slug": slug,
                }
            )

    columns = ["client_id", "persona_label", "promo_id", "segment_slug"]
    if rows:
        labels = pd.DataFrame(rows, columns=columns)
        for column in columns:
            labels[column] = labels[column].astype("object")
    else:
        labels = pd.DataFrame({col: pd.Series(dtype="object") for col in columns})

    return labels.reset_index(drop=True), cards


@settings(max_examples=100, deadline=None)
@given(data=_labels_and_cards())
def test_persona_mix_sums_to_100_per_non_empty_cell(data):
    """Persona mix sums to 100% per non-empty cell.

    **Validates: Requirements 7.1**

    For every returned :class:`~webapp_core.personas.PersonaMix` with
    ``available=True``, the per-persona shares sum to ~100.0 (within
    floating-point tolerance). A cell with no persona assignment is marked
    ``available=False`` with empty ``shares`` and is never asserted to sum to 100.
    """
    labels, cards = data

    mixes = persona_mix_by_cell(labels, cards)

    # One mix per card cell, keyed by the card's (promo_id, segment).
    assert set(mixes.keys()) == {
        (str(card["promo_id"]), str(card["segment"])) for card in cards
    }

    for key, mix in mixes.items():
        assert isinstance(mix, PersonaMix)
        if mix.available:
            # A non-empty cell: shares are present and sum to ~100.0 (Req 7.1).
            assert mix.shares
            assert sum(mix.shares.values()) == pytest.approx(
                MIX_TOTAL_PERCENT, abs=1e-6
            )
            # Every share is a positive fraction of the whole.
            assert all(share > 0.0 for share in mix.shares.values())
        else:
            # An empty cell: no assignment, empty shares, NOT asserted to sum.
            assert mix.shares == {}

    # Cross-check: a cell is available exactly when it has at least one assigned
    # (non-empty persona) lead for that card's slugged key.
    for card in cards:
        promo_id = str(card["promo_id"])
        segment = str(card["segment"])
        slug = segment_slug(segment)
        assigned = labels[
            (labels["promo_id"].astype(str) == promo_id)
            & (labels["segment_slug"].astype(str) == slug)
            & (labels["persona_label"].astype(str) != "")
        ]
        expected_available = len(assigned) > 0
        assert mixes[(promo_id, segment)].available == expected_available
