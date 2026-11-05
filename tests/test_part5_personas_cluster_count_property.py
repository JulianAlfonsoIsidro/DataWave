# Feature: persona-segmentation, Property 1: Cluster label count equals k (or the capped k)
"""Property-based test for the cluster label count.

Covers Property 1 of the persona-segmentation spec: for any group of leads at or
above ``min_group_size`` and any requested ``k`` in ``[2, 6]``, the number of
distinct persona cluster labels produced for that group equals
``min(k, group_size)`` (Requirements 2.9, 3.11).

:func:`part5_personas.cluster.cluster` fits seeded k-prototypes at the validated
k, assigns the full group to the nearest learned prototype, and internally runs
the Elbow_Plot sweep over k = 2..6 on the group. That sweep fits k-prototypes at
k_max (6), which can only initialise when the group supports six well-separated
clusters. So every generated group is built from exactly ``k_max`` well-separated
blobs: each blob has a distinct numeric center (far apart relative to within-blob
jitter) *and* its own categorical value, with at least one member per blob.
k-prototypes requires at least one categorical column, so the frame carries both
a numeric and a categorical column.

With six natural, well-separated blobs the requested ``k`` (in ``[2, 6]``) drives
how many non-empty clusters the main fit forms: k-prototypes fills all ``k``
clusters, so the distinct-label count equals ``k``. Since ``group_size >= k_max
>= k``, ``min(k, group_size) == k``, which is exactly what the property asserts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part5_personas.cluster import cluster
from part5_personas.config import Config

# Per-blob membership range. A floor of several points per blob (rather than 1)
# keeps groups small enough that 100 k-prototypes fits plus the 2..6 elbow sweep
# per example run quickly, while giving each well-separated blob enough mass that
# the seeded init reliably seeds it. Groups stay far below ``max_sample_size`` so
# the whole group is the fit subsample.
_MIN_PER_BLOB = 4
_MAX_PER_BLOB = 10

# Numeric blob geometry: centers sit on a grid (_CENTER_STEP apart) with a real
# within-blob spread (_JITTER). The spread is a modest fraction of the spacing so
# blobs stay well-separated, yet non-degenerate enough that k-prototypes' seeded
# (random-normal) numeric init can place one seed per blob and reach k non-empty
# clusters instead of collapsing on point-like blobs.
_CENTER_STEP = 10.0
_JITTER = 1.0

_SEED_CFG = Config()


# ``cluster`` fits k-prototypes at k_max during its Elbow_Plot sweep, so the
# group must always support k_max well-separated clusters. Build exactly k_max
# blobs regardless of the requested k.
_N_BLOBS = _SEED_CFG.k_max


@st.composite
def _blobbed_group(draw):
    """Draw a ``k_max``-blob group plus a requested k in ``[k_min, k_max]``.

    Returns ``(frame, cat_indices, client_ids, k)`` where ``frame`` carries one
    numeric column (``num0``) and one categorical column (``cat0``). The group is
    built from exactly ``_N_BLOBS`` ( == ``k_max``) well-separated blobs: each
    blob has a distinct numeric center and its own categorical value, and holds at
    least one point. That guarantees the internal elbow sweep (which fits at
    k_max) can initialise, while the requested ``k`` drives the main fit's
    non-empty cluster count. ``group_size >= k_max >= k``, so ``min(k,
    group_size) == k``.

    k-prototypes requires at least one categorical column, so ``cat_indices``
    points at the ``cat0`` position.
    """
    k = draw(st.integers(min_value=_SEED_CFG.k_min, max_value=_SEED_CFG.k_max))

    # Per-blob membership: at least one point each keeps every blob a single,
    # well-separated, non-empty cluster.
    per_blob = draw(
        st.lists(
            st.integers(min_value=_MIN_PER_BLOB, max_value=_MAX_PER_BLOB),
            min_size=_N_BLOBS,
            max_size=_N_BLOBS,
        )
    )

    rng = np.random.default_rng(draw(st.integers(min_value=0, max_value=10_000)))
    values: list[float] = []
    categories: list[str] = []
    for blob_idx, count in enumerate(per_blob):
        center = blob_idx * _CENTER_STEP
        jitter = rng.uniform(-_JITTER, _JITTER, size=count)
        values.extend((center + jitter).tolist())
        # One distinct categorical value per blob, reinforcing the same split.
        categories.extend([f"g{blob_idx}"] * count)

    # ``cluster`` always receives a *preprocessed* frame, so its numeric column is
    # standardized to zero mean / unit variance (see ``preprocess.scale_numeric``).
    # Standardize here too so the generated data matches that contract: without
    # it, raw-scale numeric values leave k-prototypes' seeded init unable to form
    # k_max non-empty clusters. The blobs stay well-separated after scaling.
    num = np.asarray(values, dtype=float)
    num = (num - num.mean()) / num.std(ddof=0)

    frame = pd.DataFrame({"num0": num, "cat0": categories})
    # cat0 is at positional index 1 within the ordered frame columns.
    cat_indices = [1]
    client_ids = pd.Series([f"C{i:05d}" for i in range(len(values))])
    return frame, cat_indices, client_ids, k


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow],
)
@given(group=_blobbed_group())
def test_cluster_label_count_equals_k(group):
    """Cluster label count equals k (or the capped k).

    **Validates: Requirements 2.9, 3.11**

    For a group built from ``k_max`` well-separated blobs, the number of distinct
    persona cluster labels produced at the requested ``k`` equals ``min(k,
    group_size)``. Each generated group has ``group_size >= k_max >= k``, so the
    expected distinct-label count is exactly ``k``.
    """
    frame, cat_indices, client_ids, k = group
    group_size = len(frame)

    labels, _elbow = cluster(frame, cat_indices, client_ids, k, _SEED_CFG)

    assert labels.shape == (group_size,)

    distinct = len(np.unique(labels))
    expected = min(k, group_size)
    assert distinct == expected, (distinct, expected, k, group_size)
