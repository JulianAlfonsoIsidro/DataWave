"""Persona profiling for the Persona_Pipeline.

Turns a group's clustered leads into one :class:`PersonaProfile` per non-empty
cluster: a size, a percentage of the clustered leads, numeric means/medians, the
top categories per categorical attribute, and the top-3 attributes that most
distinguish the persona from the other personas in the same set. Pure functions
over pandas/numpy with no Streamlit imports.

Crucially, the input ``frame`` is the **raw (pre-scaling) joined attribute
values**, not the scaled clustering matrix, so means, medians, and category
counts are reported on the real, interpretable scale — the profile reports real
values, never standardized ones. The *distinguishing* metric, by contrast, is
computed from standardized / proportion-difference scores (design D2), never from
raw values, so attributes measured on different scales are comparable.

Responsibilities, in a deterministic order:

- **Per-persona stats** (:func:`profile_stats`): ``size`` as a non-negative
  integer lead count and ``pct_of_leads`` as ``size / total * 100`` rounded to one
  decimal and clamped to ``[0.0, 100.0]`` (Requirement 4.1); the mean and median of
  each numeric attribute; and the top-3 ``(category, count)`` pairs per categorical
  attribute, falling back to *all* present categories when fewer than 3 are present
  (Requirements 4.1, 4.2). Category ties break deterministically by descending
  count then ascending category value.
- **Distinguishing attributes** (:func:`distinguishing_attributes`, design D2 /
  Requirement 4.3): for a numeric attribute the standardized z-score of the
  persona's mean against the across-persona distribution of persona means
  (``abs(mean_p - mu) / sigma``, ``0.0`` when ``sigma == 0``); for a categorical
  attribute the maximum absolute proportion difference of any category against the
  pooled other-personas proportion (``0.0`` when there is only one persona or all
  other personas are empty). The 3 attributes with the largest scores are selected,
  ties broken by ascending attribute name, so the ranking is a pure deterministic
  function of the profiles. When fewer than 3 attributes were clustered on, all of
  them are reported.
- **Zero-size omission** (:func:`build_profiles`): clusters with zero leads are
  omitted from the set entirely rather than profiled or named (Requirement 4.7).

:func:`build_profiles` is the public entry point. It groups the clustered leads by
cluster label, drops empty clusters, computes per-persona stats, then computes the
distinguishing attributes across the whole set (the metric is cross-persona, so it
needs every persona's stats first). The returned profiles are ordered by ascending
cluster label, which fixes a stable naming order for the later naming stage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PersonaProfile:
    """Computed statistics for one persona (one non-empty cluster).

    All reported numeric/categorical values are on the **raw** attribute scale
    (means, medians, category counts), while :attr:`distinguishing` is derived
    from standardized scores (design D2). Zero-size clusters are never turned into
    a ``PersonaProfile`` (Requirement 4.7).
    """

    cluster_label: int
    """The raw k-prototypes cluster label this profile summarizes."""
    size: int
    """Non-negative count of leads in the cluster (Requirement 4.1)."""
    pct_of_leads: float
    """Share of the group's clustered leads, ``0.0``-``100.0``, 1 decimal (Req 4.1)."""
    numeric_mean: dict[str, float]
    """Mean of each numeric attribute over the cluster's raw values."""
    numeric_median: dict[str, float]
    """Median of each numeric attribute over the cluster's raw values."""
    top_categories: dict[str, list[tuple[str, int]]]
    """Top-3 ``(category, count)`` per categorical attribute, or all when fewer
    than 3 are present (Requirements 4.1, 4.2)."""
    distinguishing: list[str]
    """Top-3 distinguishing attribute names (design D2 / Requirement 4.3)."""


def _top_categories_for(column: pd.Series, top_n: int = 3) -> list[tuple[str, int]]:
    """Top-``top_n`` ``(category, count)`` pairs for one categorical column.

    Counts the non-missing values, orders by descending count with ties broken by
    ascending category value (so the result is deterministic), and keeps at most
    ``top_n`` entries. When the column has fewer than ``top_n`` distinct categories,
    every present category is returned (Requirement 4.2). Category keys are coerced
    to ``str`` so the mapping is uniform regardless of the source dtype (for example
    ``{0, 1}`` ownership flags).

    Args:
        column: The categorical column restricted to one cluster's rows.
        top_n: The maximum number of categories to return.

    Returns:
        An ordered list of ``(category_str, count)`` pairs, longest-count first.
    """
    non_missing = column.dropna()
    if non_missing.empty:
        return []

    counts = non_missing.value_counts()
    # Build a frame so we can sort by (descending count, ascending category value)
    # deterministically regardless of the original value_counts ordering.
    ordered = sorted(
        counts.items(),
        key=lambda item: (-int(item[1]), str(item[0])),
    )
    return [(str(category), int(count)) for category, count in ordered[:top_n]]


def profile_stats(
    frame: pd.DataFrame,
    labels: np.ndarray,
    numeric_cols: list[str],
    categorical_cols: list[str],
) -> dict[int, dict]:
    """Per-cluster raw-scale statistics for every non-empty cluster.

    Groups ``frame`` rows by their cluster ``labels`` and, for each non-empty
    cluster, computes its ``size``, ``pct_of_leads`` (``size / total * 100`` rounded
    to one decimal and clamped to ``[0.0, 100.0]``, Requirement 4.1), the mean and
    median of each numeric attribute, and the top categories of each categorical
    attribute (Requirements 4.1, 4.2). All statistics use the **raw** attribute
    values in ``frame`` so they stay interpretable.

    Zero-size clusters simply never appear in the result, which realizes the
    zero-size omission rule (Requirement 4.7).

    Args:
        frame: The raw (pre-scaling) joined attribute values, one row per lead,
            carrying the ``numeric_cols`` and ``categorical_cols``.
        labels: A 1-D cluster label per row, aligned to ``frame`` row order.
        numeric_cols: The numeric attribute names to summarize.
        categorical_cols: The categorical attribute names to summarize.

    Returns:
        A ``{cluster_label: stats}`` mapping ordered by ascending label, where each
        ``stats`` dict holds ``size``, ``pct_of_leads``, ``numeric_mean``,
        ``numeric_median``, and ``top_categories``.
    """
    work = frame.reset_index(drop=True)
    label_series = pd.Series(np.asarray(labels), index=work.index, name="_cluster")
    total = len(work)

    stats: dict[int, dict] = {}
    for label in sorted(pd.unique(label_series)):
        mask = label_series == label
        size = int(mask.sum())
        if size == 0:
            # Zero-size clusters are omitted entirely (Requirement 4.7).
            continue

        cluster_frame = work.loc[mask]

        pct = round(size / total * 100, 1) if total > 0 else 0.0
        pct = float(min(100.0, max(0.0, pct)))

        numeric_mean = {col: float(cluster_frame[col].mean()) for col in numeric_cols}
        numeric_median = {
            col: float(cluster_frame[col].median()) for col in numeric_cols
        }
        top_categories = {
            col: _top_categories_for(cluster_frame[col]) for col in categorical_cols
        }

        stats[int(label)] = {
            "size": size,
            "pct_of_leads": pct,
            "numeric_mean": numeric_mean,
            "numeric_median": numeric_median,
            "top_categories": top_categories,
        }

    return stats


def _numeric_score(
    label: int,
    col: str,
    stats: dict[int, dict],
    labels_sorted: list[int],
) -> float:
    """Standardized distinctiveness score for one numeric attribute (design D2).

    Computes the z-score of this persona's mean against the across-persona
    distribution of persona means for attribute ``col``:
    ``abs(mean_p - mu) / sigma`` where ``mu`` and ``sigma`` (population std,
    ``ddof=0``) are taken over the per-persona means. Returns ``0.0`` when
    ``sigma == 0`` so a flat attribute never distinguishes anyone (Requirement 4.3).
    """
    means = np.array(
        [stats[q]["numeric_mean"][col] for q in labels_sorted], dtype=float
    )
    mu = means.mean()
    sigma = means.std(ddof=0)
    if sigma == 0:
        return 0.0
    return float(abs(stats[label]["numeric_mean"][col] - mu) / sigma)


def _categorical_score(
    label: int,
    col: str,
    stats: dict[int, dict],
    labels_sorted: list[int],
) -> float:
    """Max absolute proportion-difference score for one categorical attribute (D2).

    For each category ``c`` of ``col`` the persona's within-cluster proportion
    ``prop_p`` is compared against the pooled other-personas proportion
    ``prop_other`` (counts summed over every persona except this one, divided by the
    other personas' total size); the score is the maximum absolute difference over
    all categories (Requirement 4.3). Returns ``0.0`` when there is only one persona
    or the other personas are collectively empty, since no contrast is possible.

    Category counts come from each persona's ``top_categories``, which may be
    truncated to the top 3 — but a category that distinguishes a persona is, by
    construction, one of its most frequent categories, and the pooled comparison
    uses whatever counts are recorded consistently for both sides, so the max-diff
    ranking stays a deterministic function of the profiles.
    """
    size_p = stats[label]["size"]
    if size_p == 0:
        return 0.0

    others = [q for q in labels_sorted if q != label]
    other_total = sum(stats[q]["size"] for q in others)
    if not others or other_total == 0:
        return 0.0

    def _counts(persona_label: int) -> dict[str, int]:
        return {cat: int(count) for cat, count in stats[persona_label]["top_categories"][col]}

    counts_p = _counts(label)

    other_counts: dict[str, int] = {}
    for q in others:
        for cat, count in _counts(q).items():
            other_counts[cat] = other_counts.get(cat, 0) + count

    categories = set(counts_p) | set(other_counts)
    best = 0.0
    for cat in categories:
        prop_p = counts_p.get(cat, 0) / size_p
        prop_other = other_counts.get(cat, 0) / other_total
        diff = abs(prop_p - prop_other)
        if diff > best:
            best = diff
    return float(best)


def distinguishing_attributes(
    stats: dict[int, dict],
    numeric_cols: list[str],
    categorical_cols: list[str],
    top_n: int = 3,
) -> dict[int, list[str]]:
    """Top-``top_n`` distinguishing attribute names per persona (design D2 / Req 4.3).

    For every persona, scores each selected attribute by its standardized
    distinctiveness — numeric attributes via :func:`_numeric_score` (z-score of the
    persona mean against the persona-mean distribution) and categorical attributes
    via :func:`_categorical_score` (max absolute proportion difference against the
    pooled other personas) — then keeps the ``top_n`` highest-scoring attributes.
    Ties are broken by **ascending attribute name**, so the selection is a pure
    deterministic function of the profiles (Requirement 4.3). When fewer than
    ``top_n`` attributes were clustered on, every attribute is reported.

    All scores derive from standardized / proportion-difference quantities, never
    from raw attribute values, keeping attributes on different scales comparable.

    Args:
        stats: The per-persona stats from :func:`profile_stats`.
        numeric_cols: The numeric attribute names.
        categorical_cols: The categorical attribute names.
        top_n: How many distinguishing attributes to keep per persona.

    Returns:
        A ``{cluster_label: [attribute, ...]}`` mapping, each list of length
        ``min(top_n, number_of_attributes)``.
    """
    labels_sorted = sorted(stats)
    all_cols = list(numeric_cols) + list(categorical_cols)
    numeric_set = set(numeric_cols)

    result: dict[int, list[str]] = {}
    for label in labels_sorted:
        scored: list[tuple[float, str]] = []
        for col in all_cols:
            if col in numeric_set:
                score = _numeric_score(label, col, stats, labels_sorted)
            else:
                score = _categorical_score(label, col, stats, labels_sorted)
            scored.append((score, col))

        # Largest score first; ties broken by ascending attribute name so the
        # ranking is deterministic (Requirement 4.3).
        scored.sort(key=lambda item: (-item[0], item[1]))
        result[label] = [col for _, col in scored[:top_n]]

    return result


def build_profiles(
    frame: pd.DataFrame,
    labels: np.ndarray,
    numeric_cols: list[str],
    categorical_cols: list[str],
) -> list[PersonaProfile]:
    """Build one :class:`PersonaProfile` per non-empty cluster (Requirement 4).

    The public entry point for the profiling stage. It:

    1. Groups the clustered leads by their cluster ``labels`` and computes each
       non-empty cluster's raw-scale stats (``size``, ``pct_of_leads``, numeric
       mean/median, top categories) — dropping zero-size clusters so they are never
       profiled (Requirements 4.1, 4.2, 4.7).
    2. Computes the top-3 distinguishing attributes across the whole set from
       standardized scores, with ties broken by ascending attribute name (design
       D2 / Requirement 4.3).

    The ``frame`` must carry the **raw (pre-scaling) joined attribute values** so
    the reported means/medians/categories are interpretable; the scaled clustering
    matrix is only used upstream to produce ``labels``.

    Profiles are returned ordered by ascending cluster label, giving the later
    naming stage a stable, deterministic ordering.

    Args:
        frame: The raw joined attribute values, one row per clustered lead, aligned
            to ``labels`` and carrying every column in ``numeric_cols`` and
            ``categorical_cols``.
        labels: A 1-D cluster label per row (as produced by
            :func:`part5_personas.cluster.cluster`).
        numeric_cols: The numeric attribute names to profile.
        categorical_cols: The categorical attribute names to profile.

    Returns:
        A list of :class:`PersonaProfile`, one per non-empty cluster, ordered by
        ascending cluster label. Empty when there are no clustered leads.
    """
    labels_arr = np.asarray(labels)
    if len(labels_arr) != len(frame):
        raise ValueError(
            f"labels length {len(labels_arr)} does not match frame row count "
            f"{len(frame)}"
        )

    stats = profile_stats(frame, labels_arr, numeric_cols, categorical_cols)
    if not stats:
        return []

    distinguishing = distinguishing_attributes(stats, numeric_cols, categorical_cols)

    profiles: list[PersonaProfile] = []
    for label in sorted(stats):
        s = stats[label]
        profiles.append(
            PersonaProfile(
                cluster_label=int(label),
                size=s["size"],
                pct_of_leads=s["pct_of_leads"],
                numeric_mean=s["numeric_mean"],
                numeric_median=s["numeric_median"],
                top_categories=s["top_categories"],
                distinguishing=distinguishing[label],
            )
        )

    return profiles
