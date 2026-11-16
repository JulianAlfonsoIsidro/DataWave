# Feature: persona-segmentation, Property 2: Every clustered lead is assigned exactly one persona
# Feature: persona-segmentation, Property 11: Sampling-then-assign covers all leads
"""Property-based tests for persona assignment coverage.

Covers two correctness properties of the persona-segmentation spec:

- **Property 2 (Every clustered lead is assigned exactly one persona):** for any
  audience and valid run spec, every lead eligible for clustering appears in the
  labels exactly once with exactly one non-empty persona label (Requirements 2.1,
  5.4, 8.1).
- **Property 11 (Sampling-then-assign covers all leads):** for any group whose
  size exceeds ``max_sample_size``, fitting k-prototypes on the seeded subsample
  then assigning the full group to the nearest learned prototype yields a label
  for every lead in the group — total coverage (Requirements 2.1, 5.4, 8.1).

:func:`part5_personas.cluster.cluster` fits seeded k-prototypes on a subsample
(the whole group when it is within ``cfg.max_sample_size``, otherwise a seeded
``max_sample_size`` draw), then assigns the *full* group to the nearest learned
prototype via ``model.predict``. It also always runs an internal Elbow_Plot
sweep that fits k-prototypes at every k in ``2..6`` on the subsample, so the
fitted subsample must hold at least ``k_max`` (6) rows — kmodes raises when the
cluster count exceeds the data-point count. Every generated group/subsample is
therefore built from exactly ``k_max`` well-separated blobs (distinct numeric
center plus own categorical value) with at least one member each, matching the
preprocessed-frame contract (standardized numeric column, >=1 categorical
column).
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part5_personas.cluster import cluster
from part5_personas.config import Config

# Per-blob membership range. A floor of several points per blob keeps groups
# small enough that 100 k-prototypes fits plus the 2..6 elbow sweep per example
# run quickly, while giving each well-separated blob enough mass that the seeded
# init reliably seeds it.
_MIN_PER_BLOB = 2
_MAX_PER_BLOB = 8

# Numeric blob geometry: centers sit on a grid (_CENTER_STEP apart) with a modest
# within-blob spread (_JITTER), so blobs stay well separated yet non-degenerate.
_CENTER_STEP = 10.0
_JITTER = 1.0

_SEED_CFG = Config()

# ``cluster`` fits k-prototypes at k_max during its elbow sweep, so every fitted
# subsample must support k_max well-separated clusters. Build exactly k_max blobs
# regardless of the requested k.
_N_BLOBS = _SEED_CFG.k_max


def _build_blobbed_frame(per_blob, rng_seed):
    """Build a preprocessed-style frame from ``_N_BLOBS`` well-separated blobs.

    Returns ``(frame, cat_indices, client_ids)`` with one standardized numeric
    column (``num0``) and one categorical column (``cat0``). Each blob has a
    distinct numeric center and its own categorical value, with ``per_blob[i]``
    members, so the group reliably forms ``k_max`` non-empty clusters. The numeric
    column is standardized to zero mean / unit variance to match the preprocessed
    contract (see ``preprocess.scale_numeric``).
    """
    rng = np.random.default_rng(rng_seed)
    values: list[float] = []
    categories: list[str] = []
    for blob_idx, count in enumerate(per_blob):
        center = blob_idx * _CENTER_STEP
        jitter = rng.uniform(-_JITTER, _JITTER, size=count)
        values.extend((center + jitter).tolist())
        categories.extend([f"g{blob_idx}"] * count)

    num = np.asarray(values, dtype=float)
    num = (num - num.mean()) / num.std(ddof=0)

    frame = pd.DataFrame({"num0": num, "cat0": categories})
    # cat0 is at positional index 1 within the ordered frame columns.
    cat_indices = [1]
    client_ids = pd.Series([f"C{i:05d}" for i in range(len(values))])
    return frame, cat_indices, client_ids


@st.composite
def _whole_group(draw):
    """Draw a modest group (whole-group fit path) plus a valid k.

    Returns ``(frame, cat_indices, client_ids, k)``. The group is built from
    ``_N_BLOBS`` ( == ``k_max``) well-separated blobs with ``group_size`` well
    below the real ``max_sample_size`` (2000), so the whole group is the fit
    subsample. ``group_size >= k_max >= k``.
    """
    k = draw(st.integers(min_value=_SEED_CFG.k_min, max_value=_SEED_CFG.k_max))
    per_blob = draw(
        st.lists(
            st.integers(min_value=_MIN_PER_BLOB, max_value=_MAX_PER_BLOB),
            min_size=_N_BLOBS,
            max_size=_N_BLOBS,
        )
    )
    rng_seed = draw(st.integers(min_value=0, max_value=10_000))
    frame, cat_indices, client_ids = _build_blobbed_frame(per_blob, rng_seed)
    return frame, cat_indices, client_ids, k


@st.composite
def _oversized_group(draw):
    """Draw a group larger than a small overridden ``max_sample_size`` cap.

    Returns ``(frame, cat_indices, client_ids, k, small_cfg)`` where ``small_cfg``
    is ``Config()`` with ``max_sample_size`` overridden to a small value. The
    group always exceeds that cap so :func:`cluster` fits on a seeded subsample
    (the sampling path) and then assigns the full group.

    The subsample is a seeded *random* draw of ``small`` rows, and :func:`cluster`
    always fits the Elbow_Plot sweep at k_max (6) on that subsample. So the
    subsample itself must robustly support six well-separated clusters regardless
    of which rows the seed happens to pick. We therefore (a) keep ``small``
    comfortably above ``k_max`` so the draw is never a bare six points, and (b)
    give every row a distinct, widely spaced numeric value (a fine grid with a
    large span) so any ``small``-row subsample carries six separable numeric
    locations with a healthy spread for the numeric centroid init. One categorical
    value per blob still reinforces the split. ``k <= k_max <= small`` and
    ``k <= group_size``.
    """
    # Keep the subsample comfortably larger than k_max so the seeded draw always
    # has well more than six distinct, well-separated points to initialise on.
    small = draw(st.integers(min_value=2 * _SEED_CFG.k_max, max_value=24))
    k = draw(st.integers(min_value=_SEED_CFG.k_min, max_value=_SEED_CFG.k_max))

    # Group size strictly exceeds the cap but stays modest.
    group_size = draw(st.integers(min_value=small + 1, max_value=small + 24))

    # Every row is a distinct, widely spaced numeric grid point spanning a large
    # range, so any subsample keeps a substantial numeric spread (non-degenerate
    # centroid init). Categorical value cycles through k_max labels so the fit
    # sees the full categorical alphabet.
    values = [float(i) * _CENTER_STEP for i in range(group_size)]
    categories = [f"g{i % _N_BLOBS}" for i in range(group_size)]

    num = np.asarray(values, dtype=float)
    num = (num - num.mean()) / num.std(ddof=0)

    frame = pd.DataFrame({"num0": num, "cat0": categories})
    cat_indices = [1]
    client_ids = pd.Series([f"C{i:05d}" for i in range(group_size)])

    small_cfg = dataclasses.replace(_SEED_CFG, max_sample_size=small)
    return frame, cat_indices, client_ids, k, small_cfg


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow],
)
@given(group=_whole_group())
def test_every_clustered_lead_assigned_exactly_one_persona(group):
    """Every clustered lead is assigned exactly one persona.

    **Validates: Requirements 2.1, 5.4, 8.1**

    For a modest group clustered without sampling, :func:`cluster` returns one
    label per row, every label is a real assigned cluster index in ``range(k)``,
    and no row is left unlabeled (no NaN / no ``-1``). That establishes exactly
    one non-empty persona label per clustered lead.
    """
    frame, cat_indices, client_ids, k = group
    group_size = len(frame)

    labels, _elbow = cluster(frame, cat_indices, client_ids, k, _SEED_CFG)

    # Exactly one label per lead (total coverage, no duplicates, no drops).
    assert labels.shape == (group_size,)
    # Integer labels, each a real assigned cluster in range(k): no NaN, no -1.
    assert np.issubdtype(labels.dtype, np.integer)
    assert labels.min() >= 0
    assert labels.max() < k
    assert np.all(np.isin(labels, np.arange(k)))


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow],
)
@given(group=_oversized_group())
def test_sampling_then_assign_covers_all_leads(group):
    """Sampling-then-assign covers all leads.

    **Validates: Requirements 2.1, 5.4, 8.1**

    When the group exceeds the (overridden small) ``max_sample_size``,
    :func:`cluster` fits on the seeded subsample and assigns the *full* group to
    the nearest learned prototype. Every lead in the full group gets a label even
    though the fit saw only ``max_sample_size`` rows: one integer label per row,
    all in ``range(k)``, with no unlabeled rows.
    """
    frame, cat_indices, client_ids, k, small_cfg = group
    group_size = len(frame)

    # Precondition: this example must exercise the sampling path.
    assert group_size > small_cfg.max_sample_size

    labels, _elbow = cluster(frame, cat_indices, client_ids, k, small_cfg)

    # Total coverage: every lead in the full group is labeled exactly once.
    assert labels.shape == (group_size,)
    assert np.issubdtype(labels.dtype, np.integer)
    assert labels.min() >= 0
    assert labels.max() < k
    assert np.all(np.isin(labels, np.arange(k)))
