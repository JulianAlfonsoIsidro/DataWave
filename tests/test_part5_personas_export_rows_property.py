# Feature: persona-segmentation, Property 8: Export row count equals the input lead count
# Feature: persona-segmentation, Property 9: Group column correctness
"""Property-based tests for the persona leads export (Requirement 8).

Covers two properties of the leads export module ``part5_personas.export``, which
builds the two downloadable lead variants at the end of a persona run:

- **Property 8 (Export row count equals the input lead count)** -- both export
  variants carry exactly one row per lead present in the Part 4 leads input, with
  the lead's ``client_id`` set and order preserved and no duplicate lead rows
  introduced (Requirements 8.1, 8.3). This holds for the full
  :func:`~part5_personas.export.build_persona_labeled_leads` frame *and* for the
  compact :func:`~part5_personas.export.campaign_leads_export` projection.
- **Property 9 (Group column correctness)** -- each lead that has an assignment
  carries that assignment's ``group`` and ``persona_label`` values, while each lead
  with no assignment -- simulating a ``campaign``-level lead outside the chosen
  Campaign_Lead_Pool, or simply an unmatched lead -- carries an **empty**
  ``persona_label`` *and* an empty ``group`` (Requirements 8.6, 8.7). The compact
  projection agrees with the full frame row-for-row on ``client_id``,
  ``persona_label``, and ``group`` (Requirement 8.8).

Both functions are pure pandas frame construction -- they left-join a caller-built
assignment onto the Part 4 leads and never run k-prototypes clustering -- so each
example generates synthetic Part 4 leads, richer-attribute, and assignment frames
directly with hypothesis (fast and robust). Following the style of
``tests/test_part5_personas_profile_bounds_property.py``, a single ``@st.composite``
generator feeds the synthetic frames in. The generated assignment ``client_id`` set
is always a (possibly proper) subset of the leads' ``client_id`` set, so the
empty-label / out-of-pool path (Requirement 8.7) is exercised whenever that subset
is proper.

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from part5_personas.export import (
    GROUP_COLUMN,
    PERSONA_LABEL_COLUMN,
    build_persona_labeled_leads,
    campaign_leads_export,
)

# A small vocabulary for synthetic group keys and persona labels. Keeping the pool
# small makes distinct leads share groups/labels, which is realistic (many leads per
# persona) and keeps the generated frames compact.
_GROUPS = ["Affluent-Preferred", "Mid-Market", "Mass", "Ready Toppers", "P001"]
_LABELS = ["Steady Savers", "Aspiring Investors", "Cautious Spenders", "Big Earners"]
_CHANNELS = ["In-app", "Email", "SMS"]


@st.composite
def _leads_and_assignment(draw):
    """Draw a ``(leads, richer_attributes, assignment)`` tuple of synthetic frames.

    - ``leads`` carries ``N >= 1`` rows with unique integer ``client_id`` values and
      the remaining Part 4 columns (``best_channel``, ``p_join``, ``control``), plus
      an extra ``promo_id`` column that must be dropped by the export.
    - ``richer_attributes`` carries one row per ``client_id`` for a (possibly proper)
      subset of the leads, with one extra attribute column, so the richer-attribute
      left join is a genuine left join with unmatched leads.
    - ``assignment`` carries ``group`` + ``persona_label`` for a (possibly proper,
      possibly empty) subset of the leads. Leads outside this subset must end up with
      an empty ``persona_label`` and ``group`` (Requirement 8.7).
    """
    n = draw(st.integers(min_value=1, max_value=60))

    # Unique client_ids. Draw a set so ids are distinct, then fix a stable order.
    client_ids = draw(
        st.lists(
            st.integers(min_value=1, max_value=10_000),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )

    best_channel = draw(
        st.lists(st.sampled_from(_CHANNELS), min_size=n, max_size=n)
    )
    p_join = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )
    control = draw(st.lists(st.integers(min_value=0, max_value=1), min_size=n, max_size=n))

    leads = pd.DataFrame(
        {
            "client_id": client_ids,
            "best_channel": best_channel,
            "p_join": p_join,
            "control": control,
            # An extra, non-schema column the export must drop (Requirement 8.1/8.2).
            "promo_id": ["P001"] * n,
        }
    )

    # Assignment: a subset of the leads (possibly empty, possibly proper) so the
    # unassigned / out-of-pool path is exercised. Each assigned lead gets a group +
    # persona_label.
    assigned_mask = draw(
        st.lists(st.booleans(), min_size=n, max_size=n)
    )
    assigned_ids = [cid for cid, keep in zip(client_ids, assigned_mask) if keep]

    groups = draw(
        st.lists(st.sampled_from(_GROUPS), min_size=len(assigned_ids), max_size=len(assigned_ids))
    )
    labels = draw(
        st.lists(st.sampled_from(_LABELS), min_size=len(assigned_ids), max_size=len(assigned_ids))
    )
    assignment = pd.DataFrame(
        {
            "client_id": assigned_ids,
            GROUP_COLUMN: groups,
            PERSONA_LABEL_COLUMN: labels,
        }
    )

    # Richer attributes: one row per client_id for a subset of leads, so the richer
    # left join has unmatched leads too (Requirement 8.4). One extra attr column.
    richer_mask = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    richer_ids = [cid for cid, keep in zip(client_ids, richer_mask) if keep]
    richer_vals = draw(
        st.lists(
            st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
            min_size=len(richer_ids),
            max_size=len(richer_ids),
        )
    )
    richer_attributes = pd.DataFrame(
        {"client_id": richer_ids, "monthly_inflow": richer_vals}
    )

    return leads, richer_attributes, assignment


def _is_empty(value) -> bool:
    """A cell counts as empty when it is NaN/None (the left-join miss marker)."""
    return pd.isna(value)


@settings(max_examples=100, deadline=None)
@given(data=_leads_and_assignment())
def test_export_row_count_and_group_column(data):
    """Export row count equals the input lead count, and group column correctness.

    **Validates: Requirements 8.1, 8.3, 8.6, 8.7**

    Property 8: both the full Persona_Labeled_Leads frame and the compact
    Campaign_Leads_Export carry exactly one row per Part 4 lead, with the
    ``client_id`` set and order preserved and no duplicate ``client_id`` rows
    (Requirements 8.1, 8.3).

    Property 9: every assigned lead carries its assignment's ``group`` and
    ``persona_label``; every unassigned lead (out-of-pool / unmatched) carries an
    empty ``persona_label`` *and* an empty ``group`` (Requirements 8.6, 8.7). The
    compact projection agrees with the full frame row-for-row on ``client_id``,
    ``persona_label``, and ``group`` (Requirement 8.8).
    """
    leads, richer_attributes, assignment = data
    n = len(leads)

    full = build_persona_labeled_leads(leads, richer_attributes, assignment)
    compact = campaign_leads_export(full)

    # --- Property 8: one row per Part 4 lead for BOTH variants (Req 8.1) ---------
    assert len(full) == n
    assert len(compact) == n

    # client_id set and order preserved exactly; no dropped or duplicate leads
    # (Requirement 8.3).
    expected_ids = list(leads["client_id"])
    assert list(full["client_id"]) == expected_ids
    assert list(compact["client_id"]) == expected_ids
    assert full["client_id"].is_unique
    assert compact["client_id"].is_unique

    # Both the persona-label and group columns exist on both variants (Req 8.6).
    for col in (PERSONA_LABEL_COLUMN, GROUP_COLUMN):
        assert col in full.columns
        assert col in compact.columns

    # The compact projection carries exactly the six Campaign_Leads_Export columns.
    assert list(compact.columns) == [
        "client_id",
        PERSONA_LABEL_COLUMN,
        GROUP_COLUMN,
        "best_channel",
        "p_join",
        "control",
    ]

    # --- Property 9: group / persona_label correctness per lead -----------------
    # Expected group/label per client_id from the generated assignment.
    expected_group = dict(zip(assignment["client_id"], assignment[GROUP_COLUMN]))
    expected_label = dict(zip(assignment["client_id"], assignment[PERSONA_LABEL_COLUMN]))

    for _, row in full.iterrows():
        cid = row["client_id"]
        if cid in expected_group:
            # Assigned lead: group and persona_label match the assignment exactly.
            assert row[GROUP_COLUMN] == expected_group[cid]
            assert row[PERSONA_LABEL_COLUMN] == expected_label[cid]
        else:
            # Unassigned lead (out-of-pool / unmatched): BOTH columns empty (Req 8.7).
            assert _is_empty(row[GROUP_COLUMN])
            assert _is_empty(row[PERSONA_LABEL_COLUMN])

    # --- Req 8.8: compact agrees with full row-for-row on id / label / group ----
    for col in ("client_id", PERSONA_LABEL_COLUMN, GROUP_COLUMN):
        full_col = list(full[col])
        compact_col = list(compact[col])
        assert len(full_col) == len(compact_col)
        for a, b in zip(full_col, compact_col):
            if _is_empty(a):
                assert _is_empty(b)
            else:
                assert a == b
