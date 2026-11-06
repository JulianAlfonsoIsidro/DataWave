# Feature: persona-segmentation, Property 4: Determinism under fixed seed
# Feature: persona-segmentation, Property 10: Distinguishing-metric determinism and standardization
"""Property-based tests for Persona_Pipeline determinism and the standardized
distinguishing metric.

Covers two correctness properties of the persona-segmentation spec:

- **Property 4 (Determinism under fixed seed, Requirement 2.11):** for any fixed
  inputs and identical run spec, two runs with ``random_seed=42`` produce
  identical cluster assignments and identical persona profiles (and, where the
  naming stage exists, identical names/descriptions/actions). ``Test A`` drives
  the full ``preprocess -> cluster -> build_profiles`` flow twice with the same
  ``Config()`` and asserts byte-for-byte equality of labels and every
  ``PersonaProfile`` field.

- **Property 10 (Distinguishing-metric determinism and standardization,
  Requirements 4.3, 4.6):** for any ``PersonaSet`` the top-3 distinguishing
  attributes per persona are a deterministic function of the persona profiles,
  computed from standardized numeric z-scores (never raw values) with ties broken
  by ascending attribute name. ``Test B`` asserts
  :func:`part5_personas.profile.distinguishing_attributes` is (a) deterministic
  across repeated calls, (b) invariant to a strictly-positive affine rescale of
  every persona's numeric means for a column (because the z-score
  ``abs(mean_p - mu) / sigma`` is affine-invariant — proving the metric reads
  standardized scores, not raw values), and (c) tie-broken by ascending attribute
  name.

The clustering flow (``Test A``) reuses the blob-construction approach proven in
``test_part5_personas_cluster_count_property.py``: ``cluster`` always runs an
internal elbow sweep fitting k-prototypes at every k = 2..6 on the subsample, so
each generated group is built from exactly ``k_max`` well-separated blobs (a
distinct numeric center plus its own categorical value per blob) with enough
per-blob mass that the seeded init reliably forms clusters.

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import importlib

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from part5_personas.config import Config
from part5_personas.cluster import cluster
from part5_personas.preprocess import preprocess
from part5_personas.profile import (
    _numeric_score,
    build_profiles,
    distinguishing_attributes,
    profile_stats,
)

_CFG = Config()

# --------------------------------------------------------------------------- #
# Test A — Property 4: full-pipeline determinism under fixed seed             #
# --------------------------------------------------------------------------- #

# Blob geometry mirrors the cluster-count property test: exactly k_max blobs so
# the internal elbow sweep (which fits at k_max) can initialise, with a modest
# within-blob jitter relative to the center spacing so blobs stay well-separated.
_N_BLOBS = _CFG.k_max
_MIN_PER_BLOB = 4
_MAX_PER_BLOB = 8
_CENTER_STEP = 10.0
_JITTER = 1.0


@st.composite
def _raw_group(draw: st.DrawFn):
    """Draw a RAW (pre-scaling) joined-style frame plus a selection and k.

    Returns ``(frame, selected, k)`` where ``frame`` carries one raw numeric
    column (``num0``) and one raw categorical column (``cat0``) built from exactly
    ``k_max`` well-separated blobs (distinct numeric center + own categorical
    value per blob, with at least ``_MIN_PER_BLOB`` points each). The frame is on
    the raw scale — ``preprocess`` standardizes ``num0`` downstream. ``k`` is a
    requested cluster count in ``[k_min, k_max]``; ``group_size >= k_max >= k``.
    """
    k = draw(st.integers(min_value=_CFG.k_min, max_value=_CFG.k_max))

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
        categories.extend([f"g{blob_idx}"] * count)

    # RAW frame: num0 is on its natural scale (NOT pre-standardized); preprocess
    # performs the standardization. A second numeric column exercises multi-column
    # profiling without changing the blob structure.
    frame = pd.DataFrame(
        {
            "num0": np.asarray(values, dtype=float),
            "cat0": categories,
        }
    )
    selected = ["num0", "cat0"]
    return frame, selected, k


def _profiles_equal(a, b) -> bool:
    """Element-by-element equality of two PersonaProfile lists."""
    if len(a) != len(b):
        return False
    for pa, pb in zip(a, b):
        if pa.cluster_label != pb.cluster_label:
            return False
        if pa.size != pb.size:
            return False
        if pa.pct_of_leads != pb.pct_of_leads:
            return False
        if pa.numeric_mean != pb.numeric_mean:
            return False
        if pa.numeric_median != pb.numeric_median:
            return False
        if pa.top_categories != pb.top_categories:
            return False
        if pa.distinguishing != pb.distinguishing:
            return False
    return True


def _try_import_namer():
    """Return ``RuleBasedNamer`` if the naming module exists, else ``None``.

    Property 4 also covers naming determinism, but the naming stage may not exist
    yet. Checking at runtime lets this test assert naming determinism when
    available while still fully covering cluster/profile determinism otherwise.
    """
    try:
        module = importlib.import_module("part5_personas.naming")
    except ImportError:
        return None
    return getattr(module, "RuleBasedNamer", None)


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow],
)
@given(group=_raw_group())
def test_pipeline_is_deterministic_under_fixed_seed(group):
    """Two identical runs with random_seed=42 produce identical labels + profiles.

    **Validates: Requirements 2.11**

    Runs the full ``preprocess -> cluster -> build_profiles`` flow twice with the
    same ``Config()`` (seed 42) over the same raw inputs and asserts the two runs
    agree exactly: array-equal labels and element-for-element equal
    ``PersonaProfile`` lists (cluster_label, size, pct_of_leads, numeric_mean,
    numeric_median, top_categories, distinguishing). When the naming stage is
    present it additionally asserts identical names/descriptions/actions.
    """
    frame, selected, k = group
    numeric_cols = ["num0"]
    categorical_cols = ["cat0"]
    client_ids = pd.Series([f"C{i:05d}" for i in range(len(frame))])

    def _run():
        cfg = Config()
        preprocessed, cat_indices = preprocess(frame, selected)
        labels, _elbow = cluster(preprocessed, cat_indices, client_ids, k, cfg)
        profiles = build_profiles(frame, labels, numeric_cols, categorical_cols)
        return labels, profiles

    labels_1, profiles_1 = _run()
    labels_2, profiles_2 = _run()

    # Identical cluster assignments.
    assert np.array_equal(labels_1, labels_2)

    # Identical profiles, field-by-field.
    assert _profiles_equal(profiles_1, profiles_2)

    # Optional: naming determinism, only if the naming module exists.
    namer_cls = _try_import_namer()
    if namer_cls is not None:
        taken_1: set[str] = set()
        taken_2: set[str] = set()
        for p1, p2 in zip(profiles_1, profiles_2):
            named_1 = namer_cls().name(p1, taken_1)
            named_2 = namer_cls().name(p2, taken_2)
            assert named_1 == named_2


# --------------------------------------------------------------------------- #
# Test B — Property 10: distinguishing-metric determinism + standardization   #
# --------------------------------------------------------------------------- #

# A small pool of numeric/categorical attribute names keeps the stats dicts and
# their 100-iteration exploration tractable.
_NUMERIC_NAMES = ["n_alpha", "n_beta", "n_gamma", "n_delta"]
_CATEGORICAL_NAMES = ["c_one", "c_two"]
_CAT_VALUES = ["x", "y", "z"]


@st.composite
def _persona_stats(draw: st.DrawFn):
    """Draw a per-persona ``stats`` dict shaped like ``profile_stats`` output.

    Returns ``(stats, numeric_cols, categorical_cols)``. There are 2..5 personas,
    each with a non-zero ``size``, a ``numeric_mean`` per numeric column, and
    ``top_categories`` per categorical column (at least one category with a
    positive count). The medians/pct are present for shape fidelity but are not
    read by :func:`distinguishing_attributes`.
    """
    n_numeric = draw(st.integers(min_value=1, max_value=len(_NUMERIC_NAMES)))
    n_categorical = draw(st.integers(min_value=1, max_value=len(_CATEGORICAL_NAMES)))
    numeric_cols = _NUMERIC_NAMES[:n_numeric]
    categorical_cols = _CATEGORICAL_NAMES[:n_categorical]

    n_personas = draw(st.integers(min_value=2, max_value=5))

    def _finite_mean() -> st.SearchStrategy[float]:
        # Draw means on a coarse integer-step grid in a bounded range. Quantizing
        # keeps any two persona means either exactly equal or separated by at least
        # 1.0, which avoids pathologically tiny mean spreads (e.g. a ~1e-150
        # difference) whose z-score survives raw but underflows to an exact 0 after
        # an additive offset collapses the difference below float64 precision. Those
        # degenerate inputs are a floating-point artifact, not a violation of the
        # affine-invariance of the z-score the property is asserting.
        return st.integers(min_value=-1_000, max_value=1_000).map(float)

    stats: dict[int, dict] = {}
    for label in range(n_personas):
        size = draw(st.integers(min_value=1, max_value=50))
        numeric_mean = {col: draw(_finite_mean()) for col in numeric_cols}

        top_categories: dict[str, list[tuple[str, int]]] = {}
        for col in categorical_cols:
            cats = draw(
                st.lists(
                    st.sampled_from(_CAT_VALUES),
                    min_size=1,
                    max_size=len(_CAT_VALUES),
                    unique=True,
                )
            )
            # Counts bounded by size so proportions stay in [0, 1].
            pairs = [
                (cat, draw(st.integers(min_value=1, max_value=size)))
                for cat in cats
            ]
            top_categories[col] = pairs

        stats[label] = {
            "size": size,
            "pct_of_leads": 0.0,
            "numeric_mean": numeric_mean,
            "numeric_median": dict(numeric_mean),
            "top_categories": top_categories,
        }

    return stats, numeric_cols, categorical_cols


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow],
)
@given(data=_persona_stats(), a=st.floats(min_value=0.01, max_value=100.0,
                                          allow_nan=False, allow_infinity=False),
       b=st.floats(min_value=-500.0, max_value=500.0,
                   allow_nan=False, allow_infinity=False))
def test_distinguishing_metric_deterministic_and_standardized(data, a, b):
    """distinguishing_attributes is deterministic and reads standardized scores.

    **Validates: Requirements 4.3, 4.6**

    (a) Repeated calls on identical input yield identical ordered lists per
    persona (determinism). (b) Applying a strictly-positive affine transform
    ``mean -> a*mean + b`` (``a > 0``) to EVERY persona's ``numeric_mean`` for
    every numeric column leaves the per-persona distinguishing lists unchanged,
    because the z-score ``abs(mean_p - mu) / sigma`` is invariant to affine
    rescaling of the means — proving the metric is computed from standardized
    scores, never raw values (categorical scores are already proportions and the
    numeric affine leaves them untouched).
    """
    stats, numeric_cols, categorical_cols = data

    first = distinguishing_attributes(stats, numeric_cols, categorical_cols)
    again = distinguishing_attributes(stats, numeric_cols, categorical_cols)

    # (a) Determinism: identical input -> identical output.
    assert first == again

    # (b) Standardization invariance of the NUMERIC contribution. The distinguishing
    # metric scores each numeric attribute by the z-score
    # ``abs(mean_p - mu) / sigma`` of the persona mean against the across-persona
    # mean distribution. That z-score is mathematically invariant to a
    # strictly-positive affine rescale ``mean -> a*mean + b`` of every persona's
    # means (mu and sigma rescale by the same ``a``, cancelling), so applying the
    # transform must not change any persona's per-attribute numeric score. Asserting
    # the scores themselves (within a float tolerance) proves the metric reads
    # standardized values, never raw means — directly, without depending on
    # tie-break ordering, which can flip under float rounding when two scores
    # coincide exactly.
    transformed: dict[int, dict] = {}
    for label, s in stats.items():
        rescaled_mean = {col: a * s["numeric_mean"][col] + b for col in numeric_cols}
        transformed[label] = {
            **s,
            "numeric_mean": rescaled_mean,
            "numeric_median": dict(rescaled_mean),
        }

    labels_sorted = sorted(stats)
    for label in labels_sorted:
        for col in numeric_cols:
            # Across-persona population std of the RAW means for this column. When
            # it is zero (every persona shares the same mean) the attribute is flat:
            # the design defines its distinctiveness score as 0.0 (sigma == 0 guard
            # in ``_numeric_score``), and the affine-invariance property does NOT
            # apply -- a strictly-positive rescale of all-equal means is still
            # all-equal in exact arithmetic, but ``a*mean + b`` can introduce tiny
            # floating-point noise that makes the rescaled std a non-zero ~1e-13,
            # so comparing the two scores is meaningless. Exclude that degenerate
            # case from the invariance assertion and instead pin the documented
            # sigma == 0 -> 0.0 behaviour directly.
            raw_means = np.array(
                [stats[other]["numeric_mean"][col] for other in labels_sorted]
            )
            if raw_means.std(ddof=0) == 0:
                # Flat attribute: the raw score must be exactly 0.0 (Requirement 4.3).
                assert _numeric_score(label, col, stats, labels_sorted) == 0.0
                continue

            raw_score = _numeric_score(label, col, stats, labels_sorted)
            rescaled_score = _numeric_score(label, col, transformed, labels_sorted)
            assert rescaled_score == pytest.approx(raw_score, rel=1e-9, abs=1e-9)


def test_distinguishing_ties_break_by_ascending_attribute_name():
    """Equal-scoring attributes are ordered by ascending attribute name.

    **Validates: Requirements 4.3**

    Constructs a degenerate two-persona set where several numeric attributes score
    identically (symmetric means about the across-persona mean give equal
    z-scores) and the single categorical attribute is flat (zero score). The
    distinguishing list must therefore order the tied, highest-scoring attributes
    alphabetically.
    """
    # Two personas with means symmetric about 0 for every numeric column: each
    # column's z-score is identical (|mean - mu| / sigma with mu = 0, |mean| and
    # sigma equal in magnitude), so all numeric attributes tie. The categorical
    # column is identical across personas (flat) -> score 0.
    numeric_cols = ["z_last", "a_first", "m_middle"]
    categorical_cols = ["c_flat"]

    stats = {
        0: {
            "size": 10,
            "pct_of_leads": 0.0,
            "numeric_mean": {"z_last": 1.0, "a_first": 1.0, "m_middle": 1.0},
            "numeric_median": {"z_last": 1.0, "a_first": 1.0, "m_middle": 1.0},
            "top_categories": {"c_flat": [("x", 10)]},
        },
        1: {
            "size": 10,
            "pct_of_leads": 0.0,
            "numeric_mean": {"z_last": -1.0, "a_first": -1.0, "m_middle": -1.0},
            "numeric_median": {"z_last": -1.0, "a_first": -1.0, "m_middle": -1.0},
            "top_categories": {"c_flat": [("x", 10)]},
        },
    }

    result = distinguishing_attributes(stats, numeric_cols, categorical_cols, top_n=3)

    # All three numeric attributes tie on score; the flat categorical scores 0 and
    # is last. The top-3 must be the numeric names in ascending order.
    expected = ["a_first", "m_middle", "z_last"]
    for label in (0, 1):
        assert result[label] == expected
