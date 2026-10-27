"""Property-based test for ``part2_network.validation.assign_quartiles``.

Covers Property 16 (quartile binning is near-equal, order-respecting, and
deterministically tie-broken) of the part2-network spec.

``assign_quartiles`` orders joined P001 Treated_Leads by ascending
``ext_outflow_ratio``, breaks ties by ascending ``client_id`` (Requirement
9.5), and splits the sorted positions into four contiguous, near-equal bins
Q1..Q4 via :func:`numpy.array_split` (Requirement 9.4). This test exercises
that behavior across a generated joined-leads frame.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from part2_network.validation import QUARTILE_LABELS, assign_quartiles


@st.composite
def joined_leads_frames(draw: st.DrawFn) -> pd.DataFrame:
    """Draw a joined-leads DataFrame shaped like the inner-join result.

    Mirrors the columns :func:`assign_quartiles` reads: ``client_id`` (unique
    ids, so the tie-break is well-defined and the expected labels are
    deterministic), ``ext_outflow_ratio`` (floats in ``[0, 1]`` -- with a small
    pool so ties at bin boundaries occur regularly), and ``joined`` (0/1, carried
    through but unused by binning). The frame is given a deliberately non-trivial
    (shuffled, non-range) index so the test confirms labels realign to the
    caller's rows rather than to sort position.
    """
    n = draw(st.integers(min_value=0, max_value=40))

    # Unique client ids as zero-padded strings so lexicographic order is the
    # obvious tie-break order.
    client_numbers = draw(
        st.lists(
            st.integers(min_value=0, max_value=9999),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )
    client_ids = [f"C{number:04d}" for number in client_numbers]

    # A small ratio pool makes ties -- including ties straddling a bin boundary
    # -- common, so the tie-break rule (Requirement 9.5) is actually exercised.
    ratio_pool = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
    ratios = [draw(st.sampled_from(ratio_pool)) for _ in range(n)]

    joined_flags = [draw(st.sampled_from([0, 1])) for _ in range(n)]

    # A shuffled, non-range index to ensure assign_quartiles realigns by index,
    # not by position.
    index_values = draw(
        st.lists(
            st.integers(min_value=0, max_value=10_000),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )

    return pd.DataFrame(
        {
            "client_id": client_ids,
            "ext_outflow_ratio": ratios,
            "joined": joined_flags,
        },
        index=pd.Index(index_values, name="row"),
    )


def _expected_label_order(n: int) -> list[str]:
    """Build the expected per-sorted-position label sequence for ``n`` leads.

    Reproduces :func:`numpy.array_split` sizing independently: the first
    ``n % 4`` bins get ``ceil(n/4)`` positions and the rest get ``floor(n/4)``.
    Returns the flat sequence of labels over the sorted order (all Q1s, then
    Q2s, ...).
    """
    base, remainder = divmod(n, 4)
    sequence: list[str] = []
    for bin_index, label in enumerate(QUARTILE_LABELS):
        size = base + (1 if bin_index < remainder else 0)
        sequence.extend([label] * size)
    return sequence


# Feature: part2-network, Property 16: Quartile binning is near-equal,
# order-respecting, and deterministically tie-broken
@settings(max_examples=200)
@given(joined=joined_leads_frames())
def test_quartile_binning_is_near_equal_ordered_and_tie_broken(joined):
    """``assign_quartiles`` produces near-equal, order-respecting, tie-broken
    quartile labels indexed exactly like its input.

    Validates: Requirements 9.4, 9.5
    """
    labels = assign_quartiles(joined)
    n = len(joined)

    # Index matches input exactly (same values, same order).
    assert list(labels.index) == list(joined.index)

    # Labels are a subset of the four quartile labels.
    assert set(labels.dropna().unique()).issubset(set(QUARTILE_LABELS))

    counts = labels.value_counts()
    bin_sizes = [int(counts.get(label, 0)) for label in QUARTILE_LABELS]

    # Near-equal split (Requirement 9.4). For every n, array_split gives the
    # first n%4 bins ceil(n/4) and the rest floor(n/4) -- so the exact sizes are
    # known, and non-empty bin sizes differ by at most one. For n < 4 some
    # trailing bins are empty (sizes are the floor/ceil split of n/4).
    base, remainder = divmod(n, 4)
    expected_bin_sizes = [
        base + (1 if bin_index < remainder else 0) for bin_index in range(4)
    ]
    assert bin_sizes == expected_bin_sizes

    if n >= 4:
        # All four bins are non-empty and their counts differ by at most one.
        assert min(bin_sizes) >= 1
        assert max(bin_sizes) - min(bin_sizes) <= 1
    else:
        # Fewer than four leads: exactly n bins are non-empty, each of size 1.
        assert sum(bin_sizes) == n
        assert all(size in (0, 1) for size in bin_sizes)

    # Build the expected labels independently from the (ratio, client_id) sort
    # (Requirement 9.5 tie-break) and compare to the function output. This
    # simultaneously verifies: contiguous non-decreasing Q1->Q4 ordering over
    # the sorted order, correct tie-break placement at boundaries, and that each
    # original row maps to the right bin.
    sorted_frame = joined.sort_values(
        ["ext_outflow_ratio", "client_id"], kind="mergesort"
    )
    expected_sequence = _expected_label_order(n)
    expected = pd.Series(
        expected_sequence, index=sorted_frame.index, dtype=object
    ).reindex(joined.index)

    pd.testing.assert_series_equal(
        labels, expected, check_names=False, check_dtype=False
    )

    # Explicit monotonic-ordering cross-check: over the sorted order, every lead
    # in Q1 has ratio <= every lead in Q2 <= Q3 <= Q4 (Requirements 9.4/9.5).
    # (Ties at boundaries are allowed; <= captures that.)
    sorted_labels = labels.reindex(sorted_frame.index).tolist()
    label_rank = {label: rank for rank, label in enumerate(QUARTILE_LABELS)}
    ranks = [label_rank[label] for label in sorted_labels]
    assert ranks == sorted(ranks), "labels must be contiguous and non-decreasing"

    sorted_ratios = sorted_frame["ext_outflow_ratio"].tolist()
    for position in range(1, len(sorted_ratios)):
        if ranks[position] > ranks[position - 1]:
            # At a bin boundary the ratio must not decrease.
            assert sorted_ratios[position] >= sorted_ratios[position - 1]

    # Sanity: nothing above referenced an undefined bound.
    assert math.isfinite(float(n))
    assert isinstance(np.array_split(np.arange(n), 4), list)
