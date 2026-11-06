"""k-prototypes (with single-type fallback) clustering for the Persona_Pipeline.

Consumes the *preprocessed* clustering matrix produced by
:mod:`part5_personas.preprocess` (numeric columns already standardized, zero
missing values) plus the positional indices of its categorical columns, and
clusters the leads of a single group with mixed numeric/categorical
k-prototypes. Pure functions over pandas/numpy/kmodes with no Streamlit imports.

Responsibilities, in a deterministic order:

- **k validation** (:func:`validate_k`): default k to ``cfg.default_k`` (3) when
  unspecified (Requirement 2.8); accept an integer k in
  ``[cfg.k_min, cfg.k_max]`` = ``[2, 6]`` (Requirement 2.9); reject a non-integer
  or out-of-range k with a ``ValueError`` naming the valid range and produce no
  assignments (Requirement 2.10). ``bool`` is not accepted as an integer.
- **Seeded subsample** (:func:`subsample_indices`): when the group exceeds
  ``cfg.max_sample_size`` the fit runs on a reproducible subsample of exactly
  ``max_sample_size`` rows, drawn with ``numpy.random.default_rng(random_seed)``
  over the group *sorted by* ``client_id`` so the subsample is a pure function of
  inputs and seed (Requirement 2.9). Otherwise the whole group is the subsample.
- **Model choice** (:func:`select_model_kind`, Requirement 2.13): ``KPrototypes``
  rejects single-type selections, so a numeric-only selection uses seeded
  ``sklearn.cluster.KMeans`` (cost = ``inertia_``), a categorical-only selection
  uses seeded ``kmodes.kmodes.KModes`` (cost = ``cost_``), and a mixed selection
  uses ``KPrototypes`` exactly as before.
- **Fit** (:func:`fit_model`): fit the chosen model seeded with
  ``cfg.random_seed`` (42) so identical inputs and options yield identical
  assignments (Requirements 2.1, 2.11). The result exposes a uniform ``cost_`` and
  ``predict``.
- **Elbow sweep** (:func:`elbow_costs`): fit the chosen model for each k in
  ``ELBOW_K_RANGE`` (2..6) on the *same* subsample, recording ``cost_`` per k
  (Requirement 2.12); k larger than the subsample is skipped.
- **Orchestration** (:func:`cluster`): validate k, pick the seeded subsample, fit
  at k on the subsample, then assign the *full* group to the nearest learned
  prototype so every row gets exactly one label (total coverage, Requirement 2.1),
  and run the elbow sweep on the subsample.

RANDOM: every stochastic operation is seeded — ``KPrototypes`` with
``cfg.random_seed`` and the subsample RNG with ``numpy.random.default_rng``
(``cfg.random_seed``) — so the stage is fully deterministic (Requirement 2.11).

kmodes API note: ``KPrototypes.predict(X, categorical=cat_indices)`` assigns each
row to the nearest fitted prototype using the same mixed dissimilarity the fit
minimizes (euclidean on numeric + ``gamma_`` * matching on categorical). We use
``predict`` for the full-group assignment, which realizes the
"assign to nearest learned prototype" rule directly; ``model.gamma_`` is the
gamma it uses internally (Requirement 2.1 coverage).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from kmodes.kmodes import KModes
from kmodes.kprototypes import KPrototypes
from sklearn.cluster import KMeans

from part5_personas.config import ELBOW_K_RANGE, Config


def validate_k(k: int | None, cfg: Config) -> int:
    """Validate and default the requested cluster count.

    Returns ``cfg.default_k`` when ``k`` is ``None`` (Requirement 2.8). Otherwise
    ``k`` must be a genuine integer within ``[cfg.k_min, cfg.k_max]`` (Requirement
    2.9); a non-integer (including ``bool``, floats, and strings) or an
    out-of-range integer is rejected with a ``ValueError`` naming the valid range
    so no cluster assignments are produced (Requirement 2.10).

    Args:
        k: The requested cluster count, or ``None`` to use the default.
        cfg: Config carrying ``default_k``, ``k_min``, and ``k_max``.

    Returns:
        The validated integer cluster count.

    Raises:
        ValueError: If ``k`` is a non-integer or outside ``[k_min, k_max]``.
    """
    if k is None:
        return cfg.default_k

    # bool is a subclass of int but is not a valid cluster count here.
    if isinstance(k, bool) or not isinstance(k, (int, np.integer)):
        raise ValueError(
            f"k must be an integer in [{cfg.k_min}, {cfg.k_max}]; got {k!r}"
        )

    k_int = int(k)
    if k_int < cfg.k_min or k_int > cfg.k_max:
        raise ValueError(
            f"k must be an integer in [{cfg.k_min}, {cfg.k_max}]; got {k_int}"
        )
    return k_int


def subsample_indices(client_ids: pd.Series | np.ndarray, cfg: Config) -> np.ndarray:
    """Positional indices of the seeded subsample used to fit k-prototypes.

    When the group has at most ``cfg.max_sample_size`` rows the whole group is the
    subsample and the returned indices are ``0..n-1`` in order. When the group is
    larger, exactly ``cfg.max_sample_size`` positions are drawn *without
    replacement* with ``numpy.random.default_rng(cfg.random_seed)`` over the group
    *sorted by* ``client_id`` ascending, making the subsample a pure function of
    inputs and seed (Requirement 2.9). The returned indices are positions into the
    original (unsorted) row order of ``client_ids`` so callers can index the
    aligned preprocessed frame directly.

    Args:
        client_ids: Per-row client identifiers aligned to the preprocessed frame.
        cfg: Config carrying ``max_sample_size`` and ``random_seed``.

    Returns:
        A 1-D ``int`` array of positional indices into the original row order.
    """
    ids = pd.Series(np.asarray(client_ids)).reset_index(drop=True)
    n = len(ids)
    if n <= cfg.max_sample_size:
        return np.arange(n, dtype=int)

    # Positions of the group sorted by client_id (stable), then draw a seeded
    # subset of those sorted positions so the result is reproducible.
    sorted_positions = ids.sort_values(kind="stable").index.to_numpy()
    rng = np.random.default_rng(cfg.random_seed)
    chosen = rng.choice(sorted_positions, size=cfg.max_sample_size, replace=False)
    # Sort the chosen positions so downstream indexing is in stable row order.
    return np.sort(chosen).astype(int)


def _to_matrix(frame: pd.DataFrame) -> np.ndarray:
    """Build the mixed numeric/categorical object matrix kmodes expects.

    kmodes keys categorical columns by positional index into a 2-D matrix whose
    rows mix numeric and categorical values, so the preprocessed frame's columns
    are materialized (in order) into a NumPy ``object`` array.
    """
    return frame.to_numpy(dtype=object)


def select_model_kind(cat_indices: list[int], n_columns: int) -> str:
    """Pick the clustering model for the selection's shape (Requirement 2.13).

    ``KPrototypes`` rejects single-type selections, so: no categorical columns ->
    ``"kmeans"``; every column categorical -> ``"kmodes"``; otherwise
    ``"kprototypes"``. Uses the same type split as ``preprocess.classify_types``.
    """
    if not cat_indices:
        return "kmeans"
    if len(cat_indices) >= n_columns:
        return "kmodes"
    return "kprototypes"


class _FittedModel:
    """Uniform surface (``cost_``, ``predict``) over the three fitted models."""

    def __init__(self, model, kind: str, cat_indices: list[int]) -> None:
        self.model = model
        self.kind = kind
        self._cat = cat_indices or None
        if kind == "kmeans":
            self.cost_ = float(model.inertia_)
        else:
            self.cost_ = float(model.cost_)
        if kind == "kprototypes":
            # kmodes 0.12.x stores the fitted gamma as ``gamma``.
            self.gamma_ = getattr(model, "gamma", None)

    def predict(self, X: np.ndarray, categorical: list[int] | None = None) -> np.ndarray:
        """Assign each row of ``X`` to its nearest fitted prototype."""
        if self.kind == "kmeans":
            return self.model.predict(np.asarray(X, dtype=float))
        if self.kind == "kmodes":
            return self.model.predict(X)
        return self.model.predict(X, categorical=categorical or self._cat)


def fit_model(
    X: np.ndarray,
    cat_indices: list[int],
    k: int,
    cfg: Config,
) -> _FittedModel:
    """Fit the seeded model matching the selection's shape.

    Mixed -> ``KPrototypes`` (unchanged args); numeric-only -> ``KMeans``
    (``n_init=1``, cost = ``inertia_``); categorical-only -> ``KModes``
    (``init="Huang"``, ``n_init=1``, cost = ``cost_``). All are seeded with
    ``cfg.random_seed`` (Requirements 2.1, 2.11, 2.13).
    """
    kind = select_model_kind(cat_indices, X.shape[1])
    if kind == "kmeans":
        model = KMeans(n_clusters=k, n_init=1, random_state=cfg.random_seed)
        model.fit(np.asarray(X, dtype=float))
    elif kind == "kmodes":
        model = KModes(
            n_clusters=k, init="Huang", n_init=1, random_state=cfg.random_seed
        )
        model.fit(X)
    else:
        model = KPrototypes(
            n_clusters=k, init="Huang", n_init=1, random_state=cfg.random_seed
        )
        # fit_predict populates cost_, gamma_, cluster_centroids_, labels_.
        model.fit_predict(X, categorical=cat_indices or None)
    return _FittedModel(model, kind, cat_indices)


def fit_kprototypes(
    X: np.ndarray,
    cat_indices: list[int],
    k: int,
    cfg: Config,
) -> _FittedModel:
    """Backward-compatible alias of :func:`fit_model`."""
    return fit_model(X, cat_indices, k, cfg)

def elbow_costs(
    X_sub: np.ndarray,
    cat_indices: list[int],
    cfg: Config,
) -> dict[int, float]:
    """Cost sweep for the Elbow_Plot over the shared subsample.

    Fits k-prototypes for each k in ``ELBOW_K_RANGE`` (2..6) on the *same* seeded
    subsample ``X_sub`` and records ``model.cost_`` per k into a ``{k: cost}``
    mapping (Requirement 2.12). Every fit is seeded with ``cfg.random_seed`` for
    determinism (Requirement 2.11).

    k-prototypes cannot fit more clusters than there are data points, so a group
    at/above ``cfg.min_group_size`` but smaller than the top of ``ELBOW_K_RANGE``
    (for example a group of 4 leads capped to ``k_used=4`` by Requirement 3.11)
    would otherwise fail the sweep. Any candidate k that exceeds the subsample's
    row count is therefore skipped: the sweep is clamped to the feasible k values
    (those ``<= len(X_sub)``) so the cost curve stays well-formed for small groups.

    Args:
        X_sub: The subsample matrix (same one used for the main fit).
        cat_indices: Positional indices of categorical columns within ``X_sub``.
        cfg: Config carrying ``random_seed``.

    Returns:
        A ``{k: cost_}`` dict with one float cost for each feasible k in
        ``ELBOW_K_RANGE`` (those not exceeding the subsample row count).
    """
    n_points = len(X_sub)
    costs: dict[int, float] = {}
    for k in ELBOW_K_RANGE:
        # k-prototypes requires n_clusters <= n_points; skip infeasible k so a
        # small, k-capped group (Requirement 3.11) can still produce a sweep.
        if int(k) > n_points:
            continue
        model = fit_model(X_sub, cat_indices, int(k), cfg)
        costs[int(k)] = float(model.cost_)
    return costs


def cluster(
    frame_preprocessed: pd.DataFrame,
    cat_indices: list[int],
    client_ids: pd.Series | np.ndarray,
    k: int | None,
    cfg: Config,
) -> tuple[np.ndarray, dict[int, float]]:
    """Cluster one group's preprocessed leads and sweep the elbow costs.

    The deterministic flow (Requirements 2.1, 2.8-2.12):

    1. Validate/default ``k`` (Requirements 2.8, 2.9, 2.10).
    2. Pick the seeded subsample positions from the ``client_id`` order — the whole
       group when it is within ``cfg.max_sample_size`` (Requirement 2.9).
    3. Fit k-prototypes at ``k`` on the subsample (Requirements 2.1, 2.11).
    4. Assign the *full* group to its nearest learned prototype via
       ``model.predict`` so every row gets exactly one label (total coverage,
       Requirement 2.1). When the subsample is the whole group this still assigns
       every original row through the one shared code path.
    5. Sweep the elbow costs over the same subsample (Requirement 2.12).

    Args:
        frame_preprocessed: The preprocessed clustering matrix (standardized
            numeric columns, zero missing values), restricted to the selected
            columns in order.
        cat_indices: Positional indices of the categorical columns within the
            preprocessed frame.
        client_ids: Per-row client identifiers aligned to ``frame_preprocessed``,
            used only to define the deterministic subsample order.
        k: The requested cluster count, or ``None`` for ``cfg.default_k``.
        cfg: The Persona_Pipeline ``Config``.

    Returns:
        A ``(labels, elbow)`` tuple: ``labels`` is a 1-D ``int`` array aligned to
        ``frame_preprocessed`` row order with exactly one cluster index per row,
        and ``elbow`` is the ``{k: cost_}`` sweep over ``ELBOW_K_RANGE``.

    Raises:
        ValueError: If ``k`` is a non-integer or outside ``[k_min, k_max]``
            (Requirement 2.10), raised before any clustering so no assignments are
            produced.
    """
    validated_k = validate_k(k, cfg)

    frame = frame_preprocessed.reset_index(drop=True)
    full_X = _to_matrix(frame)
    categorical = cat_indices or None

    sub_pos = subsample_indices(client_ids, cfg)
    X_sub = full_X[sub_pos]

    model = fit_model(X_sub, cat_indices, validated_k, cfg)

    # Assign the full group to the nearest learned prototype (total coverage).
    labels = np.asarray(model.predict(full_X, categorical=categorical), dtype=int)

    elbow = elbow_costs(X_sub, cat_indices, cfg)
    return labels, elbow
