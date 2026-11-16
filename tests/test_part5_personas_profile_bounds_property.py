# Feature: persona-segmentation, Property 12: Percentage bounds and size consistency
"""Property-based test for persona profile percentage bounds and size consistency.

Covers Property 12 of the persona-segmentation spec: for any PersonaSet produced
by :func:`part5_personas.profile.build_profiles`, each persona's ``pct_of_leads``
lies in ``[0.0, 100.0]`` rounded to one decimal place, its ``size`` is a
non-negative (in fact positive, since zero-size clusters are omitted) integer, and
the persona sizes sum to the number of clustered leads in the group
(Requirements 4.1, 4.7).

Property 12 is a property of ``build_profiles`` given *any* labels array, so it
does not require real k-prototypes clustering. Each example generates a raw
attribute frame of ``N`` rows (at least one numeric column, optionally one
categorical column) plus an arbitrary integer ``labels`` array of length ``N``
with values drawn from a small set ``range(k)``. This feeds synthetic labels
directly to ``build_profiles``, which keeps 100 iterations fast and robust while
still exercising the real profiling code path end to end.

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from part5_personas.profile import PersonaProfile, build_profiles

# Small category vocabulary for the optional categorical column.
_CATEGORIES = ["X", "Y", "Z", "W"]


@st.composite
def _frame_and_labels(draw):
    """Draw a ``(frame, labels, numeric_cols, categorical_cols)`` tuple.

    The frame carries ``N >= 1`` rows with one numeric column (finite floats) and,
    optionally, one categorical column drawn from a small vocabulary. ``labels`` is
    an ``int`` numpy array of length ``N`` with values in ``range(k)`` for a small
    ``k`` in ``[2, 6]``; because the values are arbitrary, some of the ``k`` labels
    may never occur (exercising the zero-size omission path of Requirement 4.7).
    """
    n = draw(st.integers(min_value=1, max_value=200))
    k = draw(st.integers(min_value=2, max_value=6))

    numeric_values = draw(
        st.lists(
            st.floats(
                min_value=-1e6,
                max_value=1e6,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=n,
            max_size=n,
        )
    )

    data: dict[str, list] = {"num0": numeric_values}
    numeric_cols = ["num0"]
    categorical_cols: list[str] = []

    include_categorical = draw(st.booleans())
    if include_categorical:
        categories = draw(
            st.lists(
                st.sampled_from(_CATEGORIES),
                min_size=n,
                max_size=n,
            )
        )
        data["cat0"] = categories
        categorical_cols = ["cat0"]

    frame = pd.DataFrame(data)

    labels = draw(
        st.lists(
            st.integers(min_value=0, max_value=k - 1),
            min_size=n,
            max_size=n,
        )
    )
    labels_arr = np.asarray(labels, dtype=int)

    return frame, labels_arr, numeric_cols, categorical_cols


@settings(max_examples=100, deadline=None)
@given(data=_frame_and_labels())
def test_profile_percentage_bounds_and_size_consistency(data):
    """Percentage bounds and size consistency.

    **Validates: Requirements 4.1, 4.7**

    For any PersonaSet, each persona's ``pct_of_leads`` is in ``[0.0, 100.0]``
    rounded to one decimal, its ``size`` is a positive integer (zero-size clusters
    are omitted), and the persona sizes sum to the number of clustered leads in the
    group. The set of ``cluster_label`` values present equals the set of distinct
    labels that actually occur in the generated ``labels`` array.
    """
    frame, labels, numeric_cols, categorical_cols = data
    n = len(frame)

    profiles = build_profiles(frame, labels, numeric_cols, categorical_cols)

    assert isinstance(profiles, list)
    assert all(isinstance(p, PersonaProfile) for p in profiles)

    for p in profiles:
        # size is an int-like, non-negative, and strictly positive since zero-size
        # personas are omitted entirely (Requirement 4.7).
        assert int(p.size) == p.size
        assert p.size >= 0
        assert p.size > 0

        # pct_of_leads lies in [0.0, 100.0] (Requirement 4.1).
        assert 0.0 <= p.pct_of_leads <= 100.0

        # pct_of_leads is rounded to one decimal place.
        assert round(p.pct_of_leads, 1) == p.pct_of_leads

    # Sizes sum to the number of clustered leads in the group: every row carries a
    # label and no non-empty cluster is dropped.
    assert sum(p.size for p in profiles) == n

    # The cluster labels present equal the distinct labels that actually occur;
    # empty clusters (labels in range(k) that never occur) are correctly omitted
    # (Requirement 4.7).
    present_labels = {p.cluster_label for p in profiles}
    distinct_labels = {int(label) for label in np.unique(labels)}
    assert present_labels == distinct_labels
