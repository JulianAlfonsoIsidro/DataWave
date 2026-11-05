"""Entry point for the Persona_Pipeline CLI (Requirement 9).

Runs a single default persona generation over the full Joined_Attribute_Set and
writes the labeled-leads export, mirroring the Part 4 ``main.py`` conventions:
an argparse layer that maps ``--flag`` path overrides onto a frozen
:class:`~part5_personas.config.Config` (Requirement 9.1), a loader/gate that is
the only stage allowed to halt before output, strict output-last write ordering
so a mid-run failure leaves ``outputs/`` untouched (Requirement 9.8), and a
``main(argv) -> int`` returning ``0`` on success / a non-zero code naming the
failing step otherwise (Requirements 9.6, 9.7). The module ends with the standard
``if __name__ == "__main__": raise SystemExit(main())`` guard so the package runs
as ``python -m part5_personas.main`` with ``PYTHONPATH=src``.

Pipeline order (Requirement 9.1): join -> preprocess -> cluster -> profile ->
name -> group -> export. Concretely:

1. :func:`part5_personas.join.build_joined_attributes` assembles the
   Joined_Attribute_Set and is the only gate -- it raises on a forbidden
   answer-key input (Requirement 1.10) or a too-low Match_Rate (Requirement 1.8).
2. The Default_Attribute_Set is derived deterministically from the joined frame's
   columns (see :func:`default_clustering_attributes`) because the CLI exposes no
   Attribute_Picker (Requirement 9.1); the richer picker lives in the Persona_Page.
3. :func:`part5_personas.cluster.cluster` produces the per-lead cluster labels and
   :func:`part5_personas.grouping.build_persona_sets` produces the named
   :class:`~part5_personas.grouping.PersonaSet` list. Both run the same seeded
   (seed 42) preprocess -> cluster path, so the per-lead labels align with the
   profiles' ``cluster_label`` values (Requirement 2.11).
4. :func:`part5_personas.export.load_part4_leads_universe` reads the Part 4 leads
   and :func:`part5_personas.export.build_exports` builds the export frames.
5. Only after every computation above succeeds is ``cfg.labeled_leads_out_path``
   written (output-last, Requirement 9.8).

Missing-artifact gate (Requirement 9.5): before any clustering or write, the
required upstream ``outputs/`` artifacts the default run consumes
(``features_part2.csv`` and the per-cell ``leads/`` directory) are checked for
existence; a missing one halts with a non-zero return and a stderr message naming
the missing artifact, before anything is written.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from part5_personas.cluster import cluster
from part5_personas.config import Config
from part5_personas.export import (
    GROUP_COLUMN,
    PERSONA_LABEL_COLUMN,
    build_exports,
    labels_from_persona_sets,
    load_part4_leads_universe,
)
from part5_personas.grouping import (
    CLIENT_ID_COLUMN,
    LEVEL_ALL,
    build_persona_sets,
)
from part5_personas.join import build_joined_attributes
from part5_personas.preprocess import preprocess

# Columns that are never offered as clustering attributes by the default CLI run.
# ``client_id`` is the identifier key; ``persona_label``/``group`` are export-only
# label columns that must never leak back in as clustering inputs. The CLI has no
# Attribute_Picker, so the Default_Attribute_Set is "every other joined column"
# (Requirement 9.1); the richer, grouped Attribute_Picker lives on the Persona_Page.
_NON_CLUSTERING_COLUMNS = frozenset(
    {CLIENT_ID_COLUMN, PERSONA_LABEL_COLUMN, GROUP_COLUMN}
)


def default_clustering_attributes(joined: pd.DataFrame) -> list[str]:
    """Derive the CLI's Default_Attribute_Set from the joined frame's columns.

    The CLI exposes no Attribute_Picker, so it clusters on a deterministic default
    set of columns rather than a user selection (Requirement 9.1). The default is
    every column of the Joined_Attribute_Set except the identifier/label columns in
    :data:`_NON_CLUSTERING_COLUMNS` (``client_id`` and the export-only
    ``persona_label``/``group`` columns). Column order is preserved exactly as it
    appears in ``joined`` -- which is itself a deterministic function of the input
    sources (see :func:`part5_personas.join.build_joined_attributes`) -- so the
    selection is reproducible across runs.

    Args:
        joined: The Joined_Attribute_Set (one row per ``client_id``).

    Returns:
        The ordered list of clustering attribute names (the frame's columns minus
        the identifier/label columns).

    Raises:
        ValueError: If no clustering attribute remains after excluding the
            identifier/label columns (the joined frame carried only ``client_id``).
    """
    attributes = [c for c in joined.columns if c not in _NON_CLUSTERING_COLUMNS]
    if not attributes:
        raise ValueError(
            "the Joined_Attribute_Set has no clustering attributes after excluding "
            f"the identifier/label columns {sorted(_NON_CLUSTERING_COLUMNS)}; "
            "cannot build personas (Requirement 9.1)"
        )
    return attributes


def _parse_config(argv: list[str] | None) -> Config:
    """Parse the pipeline's path-override arguments into a :class:`Config`.

    The eight optional overrides map onto the :class:`Config` path fields and
    default to its canonical paths, matching the part4_cards convention
    (Requirement 9.1). ``argv`` of ``None`` leaves argparse to read
    ``sys.argv[1:]``. Every override is parsed as a :class:`~pathlib.Path`.
    """
    defaults = Config()
    parser = argparse.ArgumentParser(
        prog="part5_personas",
        description=(
            "Run the Part 5 persona pipeline over the full lead list and write "
            "the persona-labeled leads export."
        ),
    )
    parser.add_argument(
        "--customer-dna",
        default=defaults.customer_dna_path,
        type=Path,
        help="Path to the customer-DNA CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--product-ownership",
        default=defaults.product_ownership_path,
        type=Path,
        help="Path to the long-format product-ownership CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--features-part2",
        default=defaults.features_part2_path,
        type=Path,
        help="Path to the Part 2 features CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--segments",
        default=defaults.segments_path,
        type=Path,
        help="Path to the Part 3 segments CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--cards",
        default=defaults.cards_path,
        type=Path,
        help="Path to the Part 4 cards JSON (default: %(default)s).",
    )
    parser.add_argument(
        "--leads-dir",
        default=defaults.leads_dir,
        type=Path,
        help="Directory of the Part 4 per-cell leads CSVs (default: %(default)s).",
    )
    parser.add_argument(
        "--promo-leads",
        default=defaults.promo_leads_path,
        type=Path,
        help="Path to the past-promo leads CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--labeled-leads-out",
        default=defaults.labeled_leads_out_path,
        type=Path,
        help="Path for the persona-labeled leads CSV output (default: %(default)s).",
    )
    args = parser.parse_args(argv)
    return Config(
        customer_dna_path=args.customer_dna,
        product_ownership_path=args.product_ownership,
        features_part2_path=args.features_part2,
        segments_path=args.segments,
        cards_path=args.cards,
        leads_dir=args.leads_dir,
        promo_leads_path=args.promo_leads,
        labeled_leads_out_path=args.labeled_leads_out,
    )


def _assert_required_artifacts(cfg: Config) -> None:
    """Halt before any write when a required upstream artifact is missing (Req 9.5).

    The default run consumes two upstream ``outputs/`` artifacts: the Part 2
    features CSV (a source of the Joined_Attribute_Set) and the Part 4 per-cell
    ``leads/`` directory (the export's lead universe). Either being absent means the
    run cannot proceed, so this raises a :class:`FileNotFoundError` naming the first
    missing artifact *before* any clustering or output write (Requirement 9.5). The
    ``customer_dna``/``product_ownership`` data inputs are validated by the join
    stage itself (which also enforces the answer-key and Match_Rate gates), so they
    are not re-checked here.

    Note the answer-key marker in ``features_part2_path`` is left for the join
    stage's guard (Requirement 1.10) -- this function only checks existence.
    """
    required = [
        ("features_part2", cfg.features_part2_path),
        ("leads", cfg.leads_dir),
    ]
    for name, path in required:
        if not Path(path).exists():
            raise FileNotFoundError(
                f"required upstream artifact {name!r} is missing at {str(path)!r}; "
                "run the Part 1-4 pipeline first (Requirement 9.5)"
            )


def _labels_for_run(
    joined: pd.DataFrame,
    clustering_attributes: list[str],
    cfg: Config,
) -> pd.DataFrame:
    """Compute the per-lead persona/group assignment for the default ``all`` run.

    ``build_persona_sets`` returns the named :class:`PersonaSet` list but not the
    per-lead cluster labels the export needs, so this reproduces the group's seeded
    (seed 42) preprocess -> cluster path to recover the per-lead labels and then
    bridges them to persona names with
    :func:`part5_personas.export.labels_from_persona_sets`.

    Because every stochastic step is seeded on ``cfg.random_seed`` (Requirement
    2.11), running :func:`part5_personas.cluster.cluster` here yields the identical
    labels that ``build_persona_sets`` used internally, so each lead's cluster label
    maps to the same :class:`~part5_personas.grouping.Persona` -- the assignment is
    consistent with the profiles. At level ``all`` there is a single group whose key
    is ``""`` (Requirement 3.4), so every clustered client maps to ``group == ""``.

    Args:
        joined: The Joined_Attribute_Set (one row per ``client_id``).
        clustering_attributes: The Default_Attribute_Set to cluster on.
        cfg: The pipeline :class:`Config`.

    Returns:
        A per-lead assignment frame (``client_id``, ``group``, ``persona_label``),
        as returned by :func:`part5_personas.export.labels_from_persona_sets`.
    """
    # Build the named persona sets (preprocess -> cluster -> profile -> name) for
    # the whole lead list; level ``all`` yields a single set keyed "" (Req 3.4).
    persona_sets = build_persona_sets(
        joined,
        level=LEVEL_ALL,
        clustering_attributes=clustering_attributes,
        cfg=cfg,
    )

    # Recover the per-lead cluster labels via the same seeded path build_persona_sets
    # ran internally, so labels align with the profiles' cluster_label (Req 2.11).
    preprocessed, cat_indices = preprocess(joined, clustering_attributes)
    client_ids = joined[CLIENT_ID_COLUMN].reset_index(drop=True)
    labels, _elbow = cluster(preprocessed, cat_indices, client_ids, None, cfg)

    cluster_labels = {
        client_id: int(label)
        for client_id, label in zip(client_ids.tolist(), labels.tolist())
    }
    # Level ``all`` is one group keyed "" -- every clustered client is in it.
    group_of_client = {client_id: "" for client_id in client_ids.tolist()}

    return labels_from_persona_sets(persona_sets, cluster_labels, group_of_client)


def _write_labeled_leads(full_labeled_leads: pd.DataFrame, out_path: Path) -> None:
    """Write the full Persona_Labeled_Leads CSV, output-last (Requirements 8.5, 9.8).

    Creates the output directory first if absent (mirroring Part 4's Reporter), then
    writes the frame as a header-carrying CSV without the pandas index. This is the
    only write the CLI performs and it runs only after every clustering/profiling
    stage has succeeded, so a mid-run failure leaves ``outputs/`` untouched
    (Requirement 9.8).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    full_labeled_leads.to_csv(out_path, index=False)


def main(argv: list[str] | None = None) -> int:
    """Run the end-to-end persona pipeline and return a process exit code.

    Parses ``argv`` (``None`` reads ``sys.argv[1:]``) into a :class:`Config`, then
    runs the pipeline in order (Requirement 9.1): join -> preprocess -> cluster ->
    profile -> name -> group -> export, writing the Persona_Labeled_Leads only after
    every computation succeeds (output-last, Requirement 9.8).

    Halting rules:

    - The missing-artifact gate runs first: if a required ``outputs/`` artifact is
      absent the run returns a non-zero code and prints a stderr message naming the
      missing artifact, before any write (Requirement 9.5).
    - The join stage is the only computational gate that validates inputs; its
      answer-key (Requirement 1.10) and Match_Rate (Requirement 1.8) halts surface
      as a non-zero return naming the ``join`` step.
    - Any other stage failure returns a non-zero code naming the failing step
      (Requirement 9.7); every failure message is printed to stderr.

    A successful run returns ``0`` (Requirement 9.6).
    """
    cfg = _parse_config(argv)

    # --- Missing-artifact gate, before any clustering or write (Req 9.5) ---
    try:
        _assert_required_artifacts(cfg)
    except FileNotFoundError as exc:
        print(f"persona pipeline halted [missing-artifact]: {exc}", file=sys.stderr)
        return 1

    # Each stage is wrapped so a failure is reported by name (Req 9.7). All
    # computation finishes before the single output-last write (Req 9.8).
    try:
        joined, _report = build_joined_attributes(cfg)
    except Exception as exc:  # noqa: BLE001 - name the failing step per Req 9.7
        print(f"persona pipeline failed [join]: {exc}", file=sys.stderr)
        return 1

    try:
        clustering_attributes = default_clustering_attributes(joined)
    except Exception as exc:  # noqa: BLE001
        print(f"persona pipeline failed [attribute-selection]: {exc}", file=sys.stderr)
        return 1

    try:
        assignment = _labels_for_run(joined, clustering_attributes, cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"persona pipeline failed [cluster]: {exc}", file=sys.stderr)
        return 1

    try:
        leads = load_part4_leads_universe(cfg.leads_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"persona pipeline failed [load-leads]: {exc}", file=sys.stderr)
        return 1

    try:
        _campaign_export, full_labeled_leads = build_exports(
            leads, assignment, cfg, richer_attributes=joined
        )
    except Exception as exc:  # noqa: BLE001
        print(f"persona pipeline failed [export]: {exc}", file=sys.stderr)
        return 1

    # --- Output-last: the single write, only after every stage above succeeded ---
    try:
        _write_labeled_leads(full_labeled_leads, cfg.labeled_leads_out_path)
    except Exception as exc:  # noqa: BLE001
        print(f"persona pipeline failed [write]: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
