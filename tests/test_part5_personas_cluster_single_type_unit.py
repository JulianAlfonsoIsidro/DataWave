"""Unit tests for the single-type clustering fallback (task 5.5, Requirement 2.13).

``KPrototypes`` cannot fit a numeric-only or categorical-only selection, so
``cluster.py`` falls back to a seeded ``KMeans`` / ``KModes``. These tests cover
both degenerate shapes with small synthetic frames built through
``preprocess.preprocess``: the label contract (0..k-1, one label per row),
``validate_k`` reuse (Requirements 2.8-2.10), determinism (2.11), the sampling cap
with full-population assignment (2.9), the elbow sweep (2.12), k-capping on a small
group (3.11), and that a mixed selection still uses ``KPrototypes`` unchanged.

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from kmodes.kprototypes import KPrototypes

from part5_personas import cluster as cluster_module
from part5_personas.cluster import cluster, validate_k
from part5_personas.config import ELBOW_K_RANGE, Config
from part5_personas.preprocess import preprocess

N_BLOBS = 3


def select_model_kind(cat_indices, n_columns):
    """Resolve the helper lazily so non-helper tests are collectable pre-fix."""
    return cluster_module.select_model_kind(cat_indices, n_columns)


def _raw_frame(n: int, shape: str) -> pd.DataFrame:
    """Well-separated raw frame: ``n`` rows over 3 blobs, columns by ``shape``."""
    rng = np.random.default_rng(7)
    blob = np.arange(n) % N_BLOBS
    data: dict[str, object] = {"client_id": [f"C{i:04d}" for i in range(n)]}
    if shape in ("numeric", "mixed"):
        data["num_a"] = blob * 10.0 + rng.normal(scale=0.3, size=n)
        data["num_b"] = blob * -7.0 + rng.normal(scale=0.3, size=n)
    if shape in ("categorical", "mixed"):
        letters = np.array(list("XYZ"))
        data["cat_a"] = letters[blob]
        data["cat_b"] = np.array(["p", "q", "r"])[blob]
        # Mild within-blob variety so there are more unique rows than k=6.
        data["cat_c"] = [f"{letters[b]}{i % 4}" for i, b in enumerate(blob)]
    return pd.DataFrame(data)


def _prep(n: int, shape: str):
    raw = _raw_frame(n, shape)
    selected = [c for c in raw.columns if c != "client_id"]
    frame, cat_indices = preprocess(raw, selected)
    return frame, cat_indices, raw["client_id"]


SINGLE = ["numeric", "categorical"]


def test_select_model_kind():
    assert select_model_kind([], 3) == "kmeans"
    assert select_model_kind([0, 1, 2], 3) == "kmodes"
    assert select_model_kind([1], 3) == "kprototypes"
    assert select_model_kind([0], 1) == "kmodes"


@pytest.mark.parametrize("shape", SINGLE)
def test_shape_is_single_type(shape):
    _frame, cat_indices, _ids = _prep(30, shape)
    expected = "kmeans" if shape == "numeric" else "kmodes"
    assert select_model_kind(cat_indices, _frame.shape[1]) == expected


@pytest.mark.parametrize("shape", SINGLE)
@pytest.mark.parametrize("k", [2, 3, 5])
def test_label_contract(shape, k):
    frame, cat_indices, ids = _prep(60, shape)
    labels, _elbow = cluster(frame, cat_indices, ids, k, Config())
    assert isinstance(labels, np.ndarray) and labels.ndim == 1
    assert labels.dtype.kind in {"i", "u"}
    assert len(labels) == len(frame)
    assert set(np.unique(labels)) <= set(range(k))


@pytest.mark.parametrize("shape", SINGLE)
def test_k_distinct_labels_on_separated_data(shape):
    frame, cat_indices, ids = _prep(60, shape)
    labels, _ = cluster(frame, cat_indices, ids, 3, Config())
    assert sorted(np.unique(labels).tolist()) == [0, 1, 2]
    # Separation is recovered: each blob maps to a single cluster.
    blob = np.arange(60) % N_BLOBS
    for b in range(N_BLOBS):
        assert len(set(labels[blob == b].tolist())) == 1


@pytest.mark.parametrize("shape", SINGLE)
def test_default_k_is_three(shape):
    frame, cat_indices, ids = _prep(60, shape)
    cfg = Config()
    labels, _ = cluster(frame, cat_indices, ids, None, cfg)
    assert set(np.unique(labels)) <= {0, 1, 2}
    explicit, _ = cluster(frame, cat_indices, ids, cfg.default_k, cfg)
    np.testing.assert_array_equal(labels, explicit)


@pytest.mark.parametrize("shape", SINGLE)
@pytest.mark.parametrize("bad_k", [1, 7, 2.5, "3", True])
def test_invalid_k_rejected_before_fitting(shape, bad_k):
    frame, cat_indices, ids = _prep(30, shape)
    with pytest.raises(ValueError, match=r"\[2, 6\]"):
        cluster(frame, cat_indices, ids, bad_k, Config())
    with pytest.raises(ValueError, match=r"\[2, 6\]"):
        validate_k(bad_k, Config())


@pytest.mark.parametrize("shape", SINGLE)
def test_determinism(shape):
    frame, cat_indices, ids = _prep(60, shape)
    l1, e1 = cluster(frame, cat_indices, ids, 3, Config())
    l2, e2 = cluster(frame, cat_indices, ids, 3, Config())
    np.testing.assert_array_equal(l1, l2)
    assert e1 == e2


@pytest.mark.parametrize("shape", SINGLE)
def test_sampling_cap_still_labels_every_row(shape):
    frame, cat_indices, ids = _prep(200, shape)
    cfg = replace(Config(), max_sample_size=50)
    labels, elbow = cluster(frame, cat_indices, ids, 3, cfg)
    assert len(labels) == 200
    assert set(np.unique(labels)) <= {0, 1, 2}
    assert set(elbow) == set(ELBOW_K_RANGE)
    again, _ = cluster(frame, cat_indices, ids, 3, cfg)
    np.testing.assert_array_equal(labels, again)


@pytest.mark.parametrize("shape", SINGLE)
def test_elbow_costs_for_normal_group(shape):
    frame, cat_indices, ids = _prep(60, shape)
    _labels, elbow = cluster(frame, cat_indices, ids, 3, Config())
    assert set(elbow) == {2, 3, 4, 5, 6}
    assert all(isinstance(v, float) for v in elbow.values())
    assert all(v >= 0 for v in elbow.values())


@pytest.mark.parametrize("shape", SINGLE)
def test_small_group_k_capped_and_elbow_skips_infeasible(shape):
    frame, cat_indices, ids = _prep(4, shape)
    labels, elbow = cluster(frame, cat_indices, ids, 4, Config())
    assert len(labels) == 4
    assert set(np.unique(labels)) <= {0, 1, 2, 3}
    assert set(elbow) == {2, 3, 4}
    assert all(isinstance(v, float) for v in elbow.values())


def test_mixed_shape_selects_kprototypes():
    frame, cat_indices, _ids = _prep(60, "mixed")
    assert select_model_kind(cat_indices, frame.shape[1]) == "kprototypes"


def test_mixed_selection_still_uses_kprototypes_unchanged():
    frame, cat_indices, ids = _prep(60, "mixed")
    cfg = Config()
    labels, elbow = cluster(frame, cat_indices, ids, 3, cfg)

    X = frame.to_numpy(dtype=object)
    direct = KPrototypes(n_clusters=3, init="Huang", n_init=1, random_state=cfg.random_seed)
    direct.fit_predict(X, categorical=cat_indices)
    expected = np.asarray(direct.predict(X, categorical=cat_indices), dtype=int)
    np.testing.assert_array_equal(labels, expected)

    for k in ELBOW_K_RANGE:
        m = KPrototypes(n_clusters=k, init="Huang", n_init=1, random_state=cfg.random_seed)
        m.fit_predict(X, categorical=cat_indices)
        assert elbow[k] == float(m.cost_)
