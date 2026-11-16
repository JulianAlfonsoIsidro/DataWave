"""Example-based edge tests for the Persona_Pipeline grouping flow.

Exercises the group-size and audience-scoping edges of
``part5_personas.grouping.build_persona_sets`` with small, deterministic,
in-memory frames. The companion property-based tests live elsewhere; these
cover exactly the four edges below:

- **Too-small group flag** (Requirement 3.10): a group below
  ``cfg.min_group_size`` is flagged ``too_small=True`` with ``personas == []``,
  ``k_used == 0`` and an empty elbow sweep, and is never clustered.
- **k-cap-to-group-size** (Requirement 3.11): a group at/above
  ``cfg.min_group_size`` but strictly below the requested ``k`` clusters with
  ``k_used`` capped to the group's lead count.
- **Empty business-segment field rejection** (Requirement 3.7): a
  ``business-segment`` run whose chosen field has no non-null values raises a
  ``ValueError`` naming the field, without clustering.
- **Empty campaign pool handling** (Requirement 5.6): a ``campaign`` run whose
  pool matches no ``client_id`` raises :class:`EmptyAudienceError` without
  clustering.

Clustering fits a real k-prototypes model, so groups are kept just at/above the
(overridden) ``min_group_size`` and the clustering columns stay simple (two
numeric + one categorical) so the fits are fast and deterministic. ``Config`` is
tuned with ``dataclasses.replace`` to keep ``min_group_size`` small. Relies on
``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from part5_personas.config import Config
from part5_personas.grouping import (
    CLIENT_ID_COLUMN,
    LEVEL_ALL,
    LEVEL_BUSINESS_SEGMENT,
    LEVEL_CAMPAIGN,
    EmptyAudienceError,
    build_persona_sets,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _frame(n: int, *, start: int = 0, extra: dict | None = None) -> pd.DataFrame:
    """Build a small frame with client_id + two numeric and one categorical col.

    The two numeric columns and the single categorical column form a simple,
    fast-to-fit clustering input. ``extra`` adds any additional columns (for
    example a business-segment field) keyed by column name.
    """
    data = {
        CLIENT_ID_COLUMN: [f"C{i:03d}" for i in range(start, start + n)],
        "num_a": [float(i % 7) for i in range(n)],
        "num_b": [float((i * 3) % 5) for i in range(n)],
        "cat_c": [("X", "Y", "Z")[i % 3] for i in range(n)],
    }
    if extra:
        data.update(extra)
    return pd.DataFrame(data)


_CLUSTERING_ATTRS = ["num_a", "num_b", "cat_c"]


# --------------------------------------------------------------------------- #
# 1. Too-small group flag (Requirement 3.10)                                  #
# --------------------------------------------------------------------------- #
def test_group_below_min_size_is_flagged_without_clustering():
    """A level-``all`` group below min_group_size is flagged, never clustered."""
    cfg = dataclasses.replace(Config(), min_group_size=30)
    # 10 rows is below the default/overridden min_group_size of 30.
    frame = _frame(10)

    sets = build_persona_sets(
        frame,
        level=LEVEL_ALL,
        clustering_attributes=_CLUSTERING_ATTRS,
        cfg=cfg,
    )

    assert len(sets) == 1
    persona_set = sets[0]
    assert persona_set.too_small is True
    assert persona_set.personas == []
    assert persona_set.k_used == 0
    assert persona_set.elbow_costs == {}
    # group_key is "" at level all.
    assert persona_set.group_key == ""


def test_too_small_segment_flagged_but_large_segment_clusters():
    """At business-segment level, a sub-min segment is flagged; a big one clusters."""
    cfg = dataclasses.replace(Config(), min_group_size=5)
    # Segment "big" has 6 rows (>= 5), segment "tiny" has 3 rows (< 5).
    big = _frame(6, start=0, extra={"segment": ["big"] * 6})
    tiny = _frame(3, start=6, extra={"segment": ["tiny"] * 3})
    frame = pd.concat([big, tiny], ignore_index=True)

    sets = build_persona_sets(
        frame,
        level=LEVEL_BUSINESS_SEGMENT,
        clustering_attributes=_CLUSTERING_ATTRS,
        business_segment_field="segment",
        k=2,
        cfg=cfg,
    )

    by_key = {s.group_key: s for s in sets}
    assert set(by_key) == {"big", "tiny"}

    # The too-small segment is flagged and never clustered.
    assert by_key["tiny"].too_small is True
    assert by_key["tiny"].personas == []
    assert by_key["tiny"].k_used == 0
    assert by_key["tiny"].elbow_costs == {}

    # The large-enough segment actually clustered.
    assert by_key["big"].too_small is False
    assert by_key["big"].personas


# --------------------------------------------------------------------------- #
# 2. k-cap-to-group-size (Requirement 3.11)                                   #
# --------------------------------------------------------------------------- #
def test_k_capped_to_group_size_when_below_requested_k():
    """A group at/above min_group_size but below requested k caps k to its size."""
    cfg = dataclasses.replace(Config(), min_group_size=3)
    # Group of size 4, at/above min_group_size (3) but strictly below k (6).
    frame = _frame(4)

    sets = build_persona_sets(
        frame,
        level=LEVEL_ALL,
        clustering_attributes=_CLUSTERING_ATTRS,
        k=6,
        cfg=cfg,
    )

    assert len(sets) == 1
    persona_set = sets[0]
    # k capped to the group's lead count (4), not the requested 6.
    assert persona_set.k_used == 4
    # The group was actually clustered, not flagged too small.
    assert persona_set.too_small is False
    assert persona_set.personas


# --------------------------------------------------------------------------- #
# 3. Empty business-segment field rejection (Requirement 3.7)                 #
# --------------------------------------------------------------------------- #
def test_all_null_business_segment_field_is_rejected():
    """An all-null business_segment_field raises ValueError naming the field."""
    cfg = dataclasses.replace(Config(), min_group_size=3)
    frame = _frame(6, extra={"segment": [None] * 6})

    with pytest.raises(ValueError, match="segment"):
        build_persona_sets(
            frame,
            level=LEVEL_BUSINESS_SEGMENT,
            clustering_attributes=_CLUSTERING_ATTRS,
            business_segment_field="segment",
            cfg=cfg,
        )


def test_missing_business_segment_field_column_is_rejected():
    """A field name absent from the frame raises ValueError naming the field."""
    cfg = dataclasses.replace(Config(), min_group_size=3)
    frame = _frame(6)

    with pytest.raises(ValueError, match="not_a_column"):
        build_persona_sets(
            frame,
            level=LEVEL_BUSINESS_SEGMENT,
            clustering_attributes=_CLUSTERING_ATTRS,
            business_segment_field="not_a_column",
            cfg=cfg,
        )


def test_missing_business_segment_field_name_is_rejected():
    """Business-segment level with no field name raises a ValueError."""
    cfg = dataclasses.replace(Config(), min_group_size=3)
    frame = _frame(6)

    with pytest.raises(ValueError, match="business_segment_field"):
        build_persona_sets(
            frame,
            level=LEVEL_BUSINESS_SEGMENT,
            clustering_attributes=_CLUSTERING_ATTRS,
            business_segment_field=None,
            cfg=cfg,
        )


# --------------------------------------------------------------------------- #
# 4. Empty campaign pool handling (Requirement 5.6)                           #
# --------------------------------------------------------------------------- #
def test_empty_campaign_pool_raises_empty_audience_without_clustering():
    """A campaign pool matching no client_id raises EmptyAudienceError."""
    cfg = dataclasses.replace(Config(), min_group_size=3)
    frame = _frame(6)

    # No frame client_id matches the requested pool ids -> empty pool.
    with pytest.raises(EmptyAudienceError):
        build_persona_sets(
            frame,
            level=LEVEL_CAMPAIGN,
            clustering_attributes=_CLUSTERING_ATTRS,
            campaign_pool_ids=["NOPE-1", "NOPE-2"],
            cfg=cfg,
        )


def test_empty_campaign_pool_error_is_a_value_error():
    """EmptyAudienceError subclasses ValueError, so broad handling still catches it."""
    cfg = dataclasses.replace(Config(), min_group_size=3)
    frame = _frame(6)

    with pytest.raises(ValueError):
        build_persona_sets(
            frame,
            level=LEVEL_CAMPAIGN,
            clustering_attributes=_CLUSTERING_ATTRS,
            campaign_pool_ids=[],
            cfg=cfg,
        )
