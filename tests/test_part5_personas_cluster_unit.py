"""Example-based unit tests for the Persona_Pipeline k-prototypes clustering.

Covers the public API of ``part5_personas.cluster`` with small, deterministic,
in-memory frames (the companion property-based tests live elsewhere). The
cases exercise:

- ``validate_k`` defaulting an unspecified ``k`` to ``cfg.default_k`` (3)
  (Requirement 2.8);
- ``validate_k`` rejecting non-integer and out-of-range ``k`` with a
  ``ValueError`` naming the valid ``[2, 6]`` range, producing no assignments,
  while accepting every integer in ``[2, 6]`` (Requirement 2.10);
- ``elbow_costs`` and ``cluster`` producing a ``{k: cost}`` sweep whose keys
  equal ``ELBOW_K_RANGE`` (``{2, 3, 4, 5, 6}``) with float costs
  (Requirement 2.12).

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from part5_personas.cluster import cluster, elbow_costs, validate_k
from part5_personas.config import ELBOW_K_RANGE, Config


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _preprocessed_frame(n: int = 10) -> tuple[pd.DataFrame, list[int], pd.Series]:
    """Build a small preprocessed frame with two numeric + one categorical col.

    Returns the frame, the positional categorical indices, and aligned
    client ids. The frame has no missing values (as produced by preprocess)
    and enough rows for k-prototypes to fit at k up to 6.
    """
    rng = np.random.default_rng(0)
    frame = pd.DataFrame(
        {
            # Two standardized-style numeric columns (positions 0, 1).
            "num_a": rng.normal(size=n),
            "num_b": rng.normal(size=n),
            # One categorical column (position 2) over a small vocabulary.
            "cat_c": [("X", "Y", "Z")[i % 3] for i in range(n)],
        }
    )
    cat_indices = [2]
    client_ids = pd.Series([f"C{i:03d}" for i in range(n)])
    return frame, cat_indices, client_ids


# --------------------------------------------------------------------------- #
# 1. default k = 3 when unspecified (Requirement 2.8)                         #
# --------------------------------------------------------------------------- #
def test_validate_k_defaults_to_three_when_none():
    """validate_k(None, cfg) returns cfg.default_k (3)."""
    cfg = Config()
    assert validate_k(None, cfg) == 3
    assert validate_k(None, cfg) == cfg.default_k


# --------------------------------------------------------------------------- #
# 2. accept every integer in [2, 6] (Requirement 2.9)                         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("k", [2, 3, 4, 5, 6])
def test_validate_k_accepts_integers_in_range(k):
    """validate_k accepts and returns each integer k in [k_min, k_max]."""
    cfg = Config()
    assert validate_k(k, cfg) == k


def test_validate_k_accepts_numpy_integer():
    """A numpy integer within range is accepted and returned as a plain int."""
    cfg = Config()
    result = validate_k(np.int64(4), cfg)
    assert result == 4
    assert isinstance(result, int)


# --------------------------------------------------------------------------- #
# 3. reject non-integer / out-of-range k naming [2, 6] (Requirement 2.10)     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_k", [1, 7, 0, -3, 100])
def test_validate_k_rejects_out_of_range_integers(bad_k):
    """Out-of-range integers raise ValueError naming the valid [2, 6] range."""
    cfg = Config()
    with pytest.raises(ValueError, match=r"\[2, 6\]"):
        validate_k(bad_k, cfg)


@pytest.mark.parametrize("bad_k", [2.5, 3.0, "3", True, False, None.__class__])
def test_validate_k_rejects_non_integers(bad_k):
    """Non-integer k (float, str, bool, type) raise ValueError naming [2, 6]."""
    cfg = Config()
    with pytest.raises(ValueError, match=r"\[2, 6\]"):
        validate_k(bad_k, cfg)


def test_validate_k_message_mentions_range_and_value():
    """The rejection message names the valid range and the offending value."""
    cfg = Config()
    with pytest.raises(ValueError) as exc_info:
        validate_k(9, cfg)
    message = str(exc_info.value)
    assert "[2, 6]" in message
    assert "9" in message
    assert "integer" in message


# --------------------------------------------------------------------------- #
# 4. elbow costs cover k = 2..6 with float values (Requirement 2.12)          #
# --------------------------------------------------------------------------- #
def test_elbow_costs_cover_k_two_through_six():
    """elbow_costs returns a float cost for each k in ELBOW_K_RANGE."""
    frame, cat_indices, _client_ids = _preprocessed_frame(n=10)
    cfg = Config()
    X = frame.to_numpy(dtype=object)

    costs = elbow_costs(X, cat_indices, cfg)

    assert set(costs.keys()) == set(ELBOW_K_RANGE)
    assert set(costs.keys()) == {2, 3, 4, 5, 6}
    for value in costs.values():
        assert isinstance(value, float)


def test_cluster_elbow_covers_k_two_through_six():
    """cluster returns an elbow dict keyed by ELBOW_K_RANGE with float costs."""
    frame, cat_indices, client_ids = _preprocessed_frame(n=12)
    cfg = Config()

    labels, elbow = cluster(frame, cat_indices, client_ids, 3, cfg)

    # Every row receives exactly one integer label.
    assert len(labels) == len(frame)
    assert labels.dtype.kind in {"i", "u"}

    # Elbow sweep covers k = 2..6 with float costs.
    assert set(elbow.keys()) == set(ELBOW_K_RANGE)
    assert set(elbow.keys()) == {2, 3, 4, 5, 6}
    for value in elbow.values():
        assert isinstance(value, float)


def test_cluster_defaults_k_to_three_when_none():
    """cluster with k=None uses the default k (3) and still produces labels."""
    frame, cat_indices, client_ids = _preprocessed_frame(n=12)
    cfg = Config()

    labels, _elbow = cluster(frame, cat_indices, client_ids, None, cfg)

    assert len(labels) == len(frame)
    # Default k is 3, so labels fall in {0, 1, 2}.
    assert set(np.unique(labels)) <= {0, 1, 2}


def test_cluster_rejects_invalid_k_before_assigning(tmp_path):
    """An out-of-range k raises before any labels are produced."""
    frame, cat_indices, client_ids = _preprocessed_frame(n=12)
    cfg = Config()

    with pytest.raises(ValueError, match=r"\[2, 6\]"):
        cluster(frame, cat_indices, client_ids, 7, cfg)
