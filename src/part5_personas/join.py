"""Joined_Attribute_Set builder for the Persona_Pipeline.

Assembles the per-client clustering input by pivoting the long-format
``product_ownership.csv`` into one-hot ownership flags and left-joining those
flags plus the existing ``outputs/features_part2.csv`` behavioral features onto
``customer_dna.csv`` on ``client_id`` (Requirements 1.1-1.5). It also computes
the per-source Match_Rate (Requirement 1.6), guards against forbidden
Answer_Key_File inputs (Requirement 1.10), and halts before any output when a
source's Match_Rate is zero or below the configured floor (Requirement 1.8).

This module is a pure data assembler. It never recomputes Part 2 features
(Requirement 1.5) and never performs scaling or imputation -- missing values
left by the feature left-join are handed off to ``preprocess.py``
(Requirement 2), so the frame returned here may carry NaN in the behavioral
feature columns. Every halt is raised as an exception before any output is
constructed; the CLI in ``main.py`` maps exceptions to exit codes.

Style mirrors ``part3_segments/segments.py`` and ``part4_cards/classify.py``:
pure functions over pandas frames, absolute imports, and docstrings citing the
governing requirement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from part5_personas.config import ANSWER_KEY_MARKER, Config

# The three Match_Rate source names, in a fixed report order (Requirement 1.6).
CUSTOMER_DNA_SOURCE = "customer_dna"
PRODUCT_OWNERSHIP_SOURCE = "product_ownership"
FEATURES_PART2_SOURCE = "features_part2"


def assert_no_answer_key(paths: Iterable[Path | str]) -> None:
    """Reject any input path carrying the Answer_Key_File marker.

    Turns the answer-key prohibition (Requirement 1.10) into a runtime
    invariant, mirroring ``part1_optin``'s ``assert_not_answer_key`` guard: each
    path is coerced to :class:`~pathlib.Path` and compared on its string form so
    the :data:`~part5_personas.config.ANSWER_KEY_MARKER` (``"_answer_key"``) is
    caught anywhere in the path, not only the final name component. The first
    offending path raises :class:`ValueError` naming the rejected file; the
    guard runs before any source is read, so a rejection leaves ``outputs/``
    untouched.
    """
    for path in paths:
        path = Path(path)
        if ANSWER_KEY_MARKER in str(path):
            raise ValueError(
                f"refusing to open forbidden answer-key path {path!r}: "
                f"paths containing {ANSWER_KEY_MARKER!r} are prohibited "
                f"(Requirement 1.10)"
            )


def pivot_product_ownership(product_ownership: pd.DataFrame) -> pd.DataFrame:
    """Pivot the long ownership frame into one-hot ``owns_<type>`` flags.

    Collapses the long-format ``product_ownership.csv`` (one row per client x
    owned product) into one row per ``client_id`` with one
    ``owns_<product_type>`` column per distinct ``product_type`` present. A
    client's flag is ``1`` when the client has at least one row of that
    ``product_type`` and ``0`` otherwise; every flag is an integer over
    ``{0, 1}`` treated downstream as a categorical feature
    (Requirements 1.2, 1.3).

    The flag columns are sorted alphabetically by ``product_type`` so the
    column order is a deterministic function of the input, independent of row
    order (matching the repo's stable-ordering convention). An empty input
    yields an empty frame carrying only the ``client_id`` column.
    """
    if product_ownership.empty:
        return pd.DataFrame({"client_id": pd.Series(dtype=object)})

    # Distinct product types, alphabetically sorted for a stable column order.
    product_types = sorted(product_ownership["product_type"].unique())

    # One boolean cross-tab of client_id x product_type: True where the client
    # has >= 1 row of that type. Reindex the columns to the sorted order so the
    # output column order is deterministic.
    owns = (
        product_ownership.groupby("client_id")["product_type"]
        .apply(lambda types: set(types))
        .reset_index(name="_types")
    )

    for product_type in product_types:
        owns[f"owns_{product_type}"] = owns["_types"].apply(
            lambda owned, pt=product_type: int(pt in owned)
        )

    flag_columns = [f"owns_{pt}" for pt in product_types]
    return owns[["client_id", *flag_columns]].reset_index(drop=True)


def match_rate(
    base_ids: pd.Series | pd.Index,
    source: pd.DataFrame,
    key: str = "client_id",
) -> float:
    """Fraction of base leads with a matching row in ``source``.

    The Match_Rate for a source is the share of the ``customer_dna`` base
    ``client_id`` values that appear in that source (Requirement 1.6). A base
    ``client_id`` counts as matched when it is present at least once in
    ``source[key]``; duplicate source rows do not inflate the rate because the
    base ids are de-duplicated for the membership test.

    An empty base (zero leads) is a degenerate, halt-worthy case: it returns
    ``0.0`` so the Match_Rate gate in :func:`build_joined_attributes` halts the
    run rather than dividing by zero (Requirement 1.8).
    """
    base = pd.Index(base_ids).unique()
    if len(base) == 0:
        return 0.0

    source_ids = set(source[key]) if key in source.columns else set()
    matched = sum(1 for cid in base if cid in source_ids)
    return matched / len(base)


def build_joined_attributes(cfg: Config) -> tuple[pd.DataFrame, dict[str, float]]:
    """Build the Joined_Attribute_Set and the per-source Match_Rate report.

    Runs the full assembly in a fixed, halt-before-output order:

    1. Answer-key guard over every input path (Requirement 1.10): reject with a
       :class:`ValueError` naming the file before reading anything.
    2. Read ``customer_dna.csv`` (the base, one row per ``client_id``), the long
       ``product_ownership.csv``, and ``outputs/features_part2.csv``. Behavioral
       features come only from ``features_part2.csv`` (Requirement 1.5).
    3. Pivot product ownership into ``owns_<type>`` flags (Requirements 1.2,
       1.3) and left-join those flags plus the features onto the base on
       ``client_id``, producing exactly one row per ``customer_dna`` client
       (Requirement 1.1). Clients absent from product ownership get every flag
       filled with ``0`` (Requirement 1.4).
    4. Compute the Match_Rate for each of the three sources (Requirement 1.6).
    5. Halt with a :class:`ValueError` naming the source and its rate if any
       rate is ``0`` or below ``cfg.min_match_rate`` (Requirement 1.8).

    The returned frame is pre-imputation: the feature left-join may leave NaN
    where a client had no features row, which ``preprocess.py`` resolves
    (Requirement 1.7 is satisfied downstream). Row order follows the
    ``customer_dna`` order; the ownership flag columns follow the deterministic
    alphabetical order from :func:`pivot_product_ownership`.

    Returns:
        A ``(joined, report)`` tuple where ``joined`` is the Joined_Attribute_Set
        frame (one row per ``customer_dna`` ``client_id``) and ``report`` maps
        each source name (``"customer_dna"``, ``"product_ownership"``,
        ``"features_part2"``) to its Match_Rate.

    Raises:
        ValueError: if an input path carries the answer-key marker
            (Requirement 1.10), or if any source's Match_Rate is zero or below
            ``cfg.min_match_rate`` (Requirement 1.8).
    """
    # --- 1. Answer-key guard over every input path, before any read ---
    input_paths = [
        cfg.customer_dna_path,
        cfg.product_ownership_path,
        cfg.features_part2_path,
    ]
    assert_no_answer_key(input_paths)

    # --- 2. Read the three sources ---
    customer_dna = pd.read_csv(cfg.customer_dna_path)
    product_ownership = pd.read_csv(cfg.product_ownership_path)
    features_part2 = pd.read_csv(cfg.features_part2_path)

    report = _compute_match_report(customer_dna, product_ownership, features_part2)

    # --- 5. Match_Rate halt, before constructing any joined output ---
    _assert_match_rates(report, cfg.min_match_rate)

    # --- 3. Pivot + left-join onto the customer_dna base ---
    joined = _assemble(customer_dna, product_ownership, features_part2)

    return joined, report


def _compute_match_report(
    customer_dna: pd.DataFrame,
    product_ownership: pd.DataFrame,
    features_part2: pd.DataFrame,
) -> dict[str, float]:
    """Per-source Match_Rate report against the ``customer_dna`` base.

    The base ids are ``customer_dna``'s ``client_id`` values. ``customer_dna``
    is its own source, so its rate is the fraction of base ids present in
    ``customer_dna`` itself (``1.0`` unless the base is empty). The product and
    feature rates are measured against the long/raw frames -- the long
    ``product_ownership`` is keyed on ``client_id`` just like its pivoted form,
    so the pivot does not change membership (Requirement 1.6).
    """
    base_ids = customer_dna["client_id"]
    return {
        CUSTOMER_DNA_SOURCE: match_rate(base_ids, customer_dna),
        PRODUCT_OWNERSHIP_SOURCE: match_rate(base_ids, product_ownership),
        FEATURES_PART2_SOURCE: match_rate(base_ids, features_part2),
    }


def _assert_match_rates(report: dict[str, float], min_match_rate: float) -> None:
    """Halt if any source's Match_Rate is zero or below the floor.

    Checks the sources in the fixed report order so the first offending source
    is the one reported, raising :class:`ValueError` naming the source and its
    rate (Requirement 1.8). A rate of exactly ``0`` always halts even when the
    floor is ``0``, because a source matching no lead cannot anchor a persona
    run.
    """
    for source in (
        CUSTOMER_DNA_SOURCE,
        PRODUCT_OWNERSHIP_SOURCE,
        FEATURES_PART2_SOURCE,
    ):
        rate = report[source]
        if rate == 0 or rate < min_match_rate:
            raise ValueError(
                f"match rate too low for source {source!r}: {rate:.4f} "
                f"is zero or below the minimum {min_match_rate} "
                f"(Requirement 1.8)"
            )


def _assemble(
    customer_dna: pd.DataFrame,
    product_ownership: pd.DataFrame,
    features_part2: pd.DataFrame,
) -> pd.DataFrame:
    """Left-join pivoted ownership flags and features onto the base.

    Starts from ``customer_dna`` (one row per ``client_id``), left-joins the
    pivoted ownership flags filling absent-ownership clients with ``0``
    (Requirements 1.1, 1.4), then left-joins the behavioral features
    (Requirement 1.5). The feature join may leave NaN for clients with no
    features row -- that is intentional and resolved by ``preprocess.py``
    (Requirement 1.7). Row order is preserved as the ``customer_dna`` order.
    """
    flags = pivot_product_ownership(product_ownership)
    flag_columns = [col for col in flags.columns if col != "client_id"]

    joined = customer_dna.merge(flags, on="client_id", how="left")

    # Absent-ownership clients: every flag -> 0, kept as integer {0, 1}
    # (Requirements 1.3, 1.4).
    for col in flag_columns:
        joined[col] = joined[col].fillna(0).astype(int)

    # Behavioral features left-joined; unmatched clients keep NaN for later
    # imputation (Requirement 1.5, 1.7).
    joined = joined.merge(features_part2, on="client_id", how="left")

    return joined.reset_index(drop=True)
