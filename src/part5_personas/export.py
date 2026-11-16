"""Leads export for the Persona_Pipeline (Requirement 8).

Builds the two downloadable lead exports produced at the very end of a persona
run, after clustering and profiling have both succeeded (Requirement 8.5):

- :func:`build_persona_labeled_leads` -- the full **Persona_Labeled_Leads**: one
  row per lead in the Part 4 leads input (Requirement 8.1), carrying the Part 4
  ``client_id``/``best_channel``/``p_join``/``control`` columns, a ``persona_label``
  column assigning each lead to exactly one persona, a ``group`` column, and the
  richer attributes left-joined from ``customer_dna.csv``, the pivoted
  ``product_ownership.csv``, and ``outputs/features_part2.csv`` with every source
  column name preserved exactly (Requirements 8.2-8.4, 8.6, 8.9).
- :func:`campaign_leads_export` -- the default **Campaign_Leads_Export**: a pure
  column projection of the full frame carrying exactly ``client_id``,
  ``persona_label``, ``group``, ``best_channel``, ``p_join``, ``control`` and
  nothing else, one row per Part 4 lead, agreeing row-for-row with the full frame
  on ``client_id``/persona label/group (Requirement 8.8).

Both variants preserve the one-row-per-lead guarantee (Requirement 8.1).

Design note -- this module is deliberately *pure frame construction*. It does not
run clustering, re-run the namer, or write any file; the per-lead persona/group
assignment is handed in by the caller (``main.py`` / ``webapp_core/personas.py``),
which runs :func:`part5_personas.grouping.build_persona_sets` first and only then
constructs these frames (output-last, Requirement 8.5). Keeping the assignment an
input means the campaign-level empty-label rule (Requirement 8.7) is expressed as
a plain left join: leads outside the chosen pool simply have no assignment row and
so receive an empty ``persona_label``/``group``.

The assignment is supplied as a frame with columns ``client_id`` plus the persona
label and group columns (see :func:`labels_from_persona_sets`, a convenience that
turns the :class:`~part5_personas.grouping.PersonaSet` list plus the per-lead
cluster labels into that frame). ``export.py`` itself never clusters.

Style mirrors the sibling ``join.py``/``profile.py`` modules: pure functions over
pandas frames, absolute imports, docstrings citing the governing requirement, and
no Streamlit imports.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from part5_personas.config import Config
from part5_personas.grouping import CLIENT_ID_COLUMN, PersonaSet
from part5_personas.join import build_joined_attributes

# --- Part 4 leads schema (each outputs/leads/*.csv carries exactly these) ----
PART4_LEAD_COLUMNS = ["client_id", "best_channel", "p_join", "control"]

# --- the two columns the export adds on top of the Part 4 leads ---------------
PERSONA_LABEL_COLUMN = "persona_label"
GROUP_COLUMN = "group"

# --- the exact Campaign_Leads_Export projection, in order (Requirement 8.8) ---
CAMPAIGN_LEADS_EXPORT_COLUMNS = [
    "client_id",
    PERSONA_LABEL_COLUMN,
    GROUP_COLUMN,
    "best_channel",
    "p_join",
    "control",
]

# A leads filename encodes <promo_id>_<segment_slug>.csv, e.g.
# ``P001_ready_toppers.csv`` -> promo_id "P001", segment slug "ready_toppers".
_LEADS_FILENAME_RE = re.compile(r"^(?P<promo_id>[^_]+)_(?P<segment_slug>.+)\.csv$")


def parse_leads_filename(name: str) -> tuple[str, str]:
    """Split a per-cell leads filename into ``(promo_id, segment_slug)``.

    Each Part 4 per-cell leads file is named ``<promo_id>_<segment_slug>.csv``
    (for example ``P001_ready_toppers.csv``). The promo id is the text before the
    first underscore and the segment slug is the remainder before the ``.csv``
    suffix, so a multi-word slug such as ``willing_but_stretched`` is kept whole.

    Args:
        name: The bare filename (not a full path), e.g. ``"P001_ready_toppers.csv"``.

    Returns:
        A ``(promo_id, segment_slug)`` tuple.

    Raises:
        ValueError: if ``name`` does not match the ``<promo_id>_<segment>.csv``
            shape.
    """
    match = _LEADS_FILENAME_RE.match(name)
    if match is None:
        raise ValueError(
            f"leads filename {name!r} does not match the expected "
            f"'<promo_id>_<segment_slug>.csv' shape"
        )
    return match.group("promo_id"), match.group("segment_slug")


def load_part4_leads_universe(
    leads_dir: Path | str,
    *,
    promo_id: str | None = None,
) -> pd.DataFrame:
    """Assemble the Part 4 leads universe from the per-cell ``leads/*.csv`` files.

    The Part 4 leads input is a set of per-cell CSVs under ``leads_dir``, each named
    ``<promo_id>_<segment_slug>.csv`` and carrying exactly
    ``client_id,best_channel,p_join,control``. For an ``all``/``business-segment``
    run the leads universe is the *union* of every per-cell file; for a
    ``campaign`` run the universe is a single promo's cells, selected by passing
    ``promo_id`` (Requirement 8.1 defines the export rows as "one row per lead
    present in the Part 4 leads input").

    A ``client_id`` can appear in more than one cell (different promos target the
    same client), so the union is de-duplicated to **one row per ``client_id``**:
    the first occurrence in deterministic (sorted-filename, then file row) order
    wins, which keeps the one-row-per-lead guarantee of Requirement 8.1. The
    ``promo_id`` and ``segment_slug`` parsed from each filename are attached as
    extra columns so a caller can scope the campaign pool, but they are not part of
    the Part 4 lead schema and are dropped before export.

    Args:
        leads_dir: Directory holding the per-cell leads CSVs (``cfg.leads_dir``).
        promo_id: When given, restrict the universe to that promo's cells only
            (the campaign-level pool); otherwise include every cell.

    Returns:
        A frame with columns ``client_id``, ``best_channel``, ``p_join``,
        ``control``, ``promo_id``, ``segment_slug`` -- one row per distinct
        ``client_id``, in ascending ``client_id`` order.

    Raises:
        FileNotFoundError: if ``leads_dir`` does not exist.
    """
    leads_dir = Path(leads_dir)
    if not leads_dir.exists():
        raise FileNotFoundError(f"leads directory {leads_dir!r} does not exist")

    # Sorted filenames give a deterministic first-occurrence order for de-dup.
    files = sorted(p for p in leads_dir.glob("*.csv") if p.is_file())

    frames: list[pd.DataFrame] = []
    for path in files:
        parsed_promo, segment_slug = parse_leads_filename(path.name)
        if promo_id is not None and parsed_promo != promo_id:
            continue
        cell = pd.read_csv(path)
        cell = cell[PART4_LEAD_COLUMNS].copy()
        cell["promo_id"] = parsed_promo
        cell["segment_slug"] = segment_slug
        frames.append(cell)

    columns = [*PART4_LEAD_COLUMNS, "promo_id", "segment_slug"]
    if not frames:
        return pd.DataFrame({col: pd.Series(dtype=object) for col in columns})

    universe = pd.concat(frames, ignore_index=True)
    # One row per client_id: keep the first occurrence in the deterministic
    # (sorted-file, file-row) order, then sort by client_id for a stable result.
    universe = universe.drop_duplicates(subset=[CLIENT_ID_COLUMN], keep="first")
    universe = universe.sort_values(CLIENT_ID_COLUMN).reset_index(drop=True)
    return universe[columns]


def labels_from_persona_sets(
    persona_sets: list[PersonaSet],
    cluster_labels: dict[str, int],
    group_of_client: dict[str, str],
) -> pd.DataFrame:
    """Turn a run's :class:`PersonaSet` list into a per-lead assignment frame.

    A convenience bridge between the clustering stage and the export: given the
    run's :class:`~part5_personas.grouping.PersonaSet` list, a mapping from each
    clustered ``client_id`` to its raw cluster label, and a mapping from each
    clustered ``client_id`` to its group key, it produces the per-lead assignment
    frame the export consumes -- one row per clustered client with its
    ``persona_label`` (the persona's human name, Requirement 4) and ``group``
    (Requirement 8.6).

    The persona *name* for a lead is the :class:`~part5_personas.grouping.Persona`
    whose ``profile.cluster_label`` matches the lead's cluster label *within the
    lead's group's* :class:`PersonaSet` (cluster labels restart per group, so the
    lookup is scoped by group key). Leads whose cluster label has no surviving
    persona -- which cannot normally happen since zero-size clusters are the only
    omitted ones -- are dropped from the assignment and therefore left unlabeled by
    the downstream left join (Requirement 8.4-style empty handling).

    Args:
        persona_sets: The run's persona sets (one per group), as returned by
            :func:`part5_personas.grouping.build_persona_sets`.
        cluster_labels: ``{client_id: raw_cluster_label}`` for every clustered lead.
        group_of_client: ``{client_id: group_key}`` for every clustered lead.

    Returns:
        A frame with columns ``client_id``, ``group``, ``persona_label`` -- one row
        per clustered lead, in ascending ``client_id`` order.
    """
    # (group_key, cluster_label) -> persona name, scoped per set so per-group
    # cluster labels do not collide across groups.
    name_by_group_label: dict[tuple[str, int], str] = {}
    for persona_set in persona_sets:
        for persona in persona_set.personas:
            key = (persona_set.group_key, persona.profile.cluster_label)
            name_by_group_label[key] = persona.name

    rows: list[dict[str, object]] = []
    for client_id, label in cluster_labels.items():
        group_key = group_of_client.get(client_id)
        if group_key is None:
            continue
        persona_name = name_by_group_label.get((group_key, int(label)))
        if persona_name is None:
            continue
        rows.append(
            {
                CLIENT_ID_COLUMN: client_id,
                GROUP_COLUMN: group_key,
                PERSONA_LABEL_COLUMN: persona_name,
            }
        )

    if not rows:
        return pd.DataFrame(
            {
                CLIENT_ID_COLUMN: pd.Series(dtype=object),
                GROUP_COLUMN: pd.Series(dtype=object),
                PERSONA_LABEL_COLUMN: pd.Series(dtype=object),
            }
        )

    frame = pd.DataFrame(rows, columns=[CLIENT_ID_COLUMN, GROUP_COLUMN, PERSONA_LABEL_COLUMN])
    return frame.sort_values(CLIENT_ID_COLUMN).reset_index(drop=True)


def _normalize_assignment(assignment: pd.DataFrame) -> pd.DataFrame:
    """Coerce a per-lead assignment frame to ``client_id``/``group``/``persona_label``.

    The assignment may arrive with the design's ``persona_name`` column name
    (``PersonaRunResult.labels``) or the Requirement 8 ``persona_label`` name; this
    accepts either and returns a frame carrying exactly ``client_id``, ``group``,
    ``persona_label``, de-duplicated to one row per ``client_id`` (first wins) so
    the downstream left join cannot introduce duplicate lead rows (Requirement 8.3).
    """
    work = assignment.copy()
    if PERSONA_LABEL_COLUMN not in work.columns and "persona_name" in work.columns:
        work = work.rename(columns={"persona_name": PERSONA_LABEL_COLUMN})

    missing = [
        col
        for col in (CLIENT_ID_COLUMN, GROUP_COLUMN, PERSONA_LABEL_COLUMN)
        if col not in work.columns
    ]
    if missing:
        raise ValueError(
            f"assignment frame is missing required column(s) {missing}; expected "
            f"{CLIENT_ID_COLUMN!r}, {GROUP_COLUMN!r}, and a persona label column "
            f"({PERSONA_LABEL_COLUMN!r} or 'persona_name')"
        )

    work = work[[CLIENT_ID_COLUMN, GROUP_COLUMN, PERSONA_LABEL_COLUMN]]
    # Guard the no-duplicates invariant (Requirement 8.3): one assignment per lead.
    work = work.drop_duplicates(subset=[CLIENT_ID_COLUMN], keep="first")
    return work.reset_index(drop=True)


def build_persona_labeled_leads(
    leads: pd.DataFrame,
    richer_attributes: pd.DataFrame,
    assignment: pd.DataFrame,
) -> pd.DataFrame:
    """Build the full **Persona_Labeled_Leads** frame (Requirements 8.1-8.9).

    Produces exactly one row per Part 4 lead (Requirement 8.1) by starting from the
    Part 4 ``leads`` frame and left-joining, keyed on ``client_id``:

    1. the per-lead persona assignment (``persona_label`` + ``group``), so a lead
       with no assignment -- for example a ``campaign``-level lead outside the
       chosen pool -- keeps an **empty** ``persona_label`` and ``group``
       (Requirement 8.7); and
    2. the richer attributes from ``customer_dna.csv``, the pivoted
       ``product_ownership.csv``, and ``outputs/features_part2.csv`` with every
       source column name preserved exactly (Requirement 8.2); a lead with no
       matching source row keeps those attributes **empty** rather than being
       dropped (Requirement 8.4).

    Every join is a left join keyed on the Part 4 leads, so no Part 4 lead is
    dropped and no duplicate lead rows are introduced (Requirement 8.3) -- the
    assignment and richer-attribute frames are both de-duplicated to one row per
    ``client_id`` first. The resulting column order is: the four Part 4 columns,
    then ``persona_label`` and ``group``, then the richer attributes (with
    ``client_id`` never duplicated).

    Args:
        leads: The Part 4 leads universe -- one row per lead, carrying at least
            ``client_id``, ``best_channel``, ``p_join``, ``control``. Extra columns
            (such as the ``promo_id``/``segment_slug`` from
            :func:`load_part4_leads_universe`) are dropped so the export carries
            exactly the Part 4 schema plus the persona columns plus the richer
            attributes.
        richer_attributes: The Joined_Attribute_Set (one row per ``client_id``) from
            :func:`part5_personas.join.build_joined_attributes`, whose source column
            names are preserved exactly (Requirement 8.2).
        assignment: The per-lead assignment carrying ``client_id``, ``group``, and a
            persona label column (``persona_label`` or the design's ``persona_name``).

    Returns:
        The full Persona_Labeled_Leads frame, one row per Part 4 lead, in the input
        ``leads`` order.
    """
    base = leads[PART4_LEAD_COLUMNS].copy()

    # 1. Attach persona label + group via a left join; unassigned leads (e.g.
    #    out-of-pool campaign leads) keep empty values (Requirements 8.6, 8.7).
    norm_assignment = _normalize_assignment(assignment)
    labeled = base.merge(norm_assignment, on=CLIENT_ID_COLUMN, how="left")

    # 2. Left-join the richer attributes, preserving every source column name
    #    (Requirement 8.2). client_id is the only overlap, so no column collides.
    richer = richer_attributes.drop_duplicates(subset=[CLIENT_ID_COLUMN], keep="first")
    richer_cols = [c for c in richer.columns if c != CLIENT_ID_COLUMN]
    labeled = labeled.merge(
        richer[[CLIENT_ID_COLUMN, *richer_cols]],
        on=CLIENT_ID_COLUMN,
        how="left",
    )

    # Deterministic column order: Part 4 cols, persona cols, then richer attrs.
    ordered = [
        "client_id",
        "best_channel",
        "p_join",
        "control",
        PERSONA_LABEL_COLUMN,
        GROUP_COLUMN,
        *richer_cols,
    ]
    return labeled[ordered].reset_index(drop=True)


def campaign_leads_export(full_frame: pd.DataFrame) -> pd.DataFrame:
    """Project the full frame down to the default **Campaign_Leads_Export** (Req 8.8).

    Returns a pure column projection of :func:`build_persona_labeled_leads`'s output
    carrying **exactly** the columns ``client_id``, ``persona_label``, ``group``,
    ``best_channel``, ``p_join``, ``control`` and nothing else, in that order. It
    selects columns only -- it never re-derives the assignment -- so it keeps one
    row per Part 4 lead and agrees with the full frame row-for-row on ``client_id``,
    persona label, and group (Requirement 8.8). The one-row-per-lead guarantee of
    the full frame (Requirement 8.1) therefore carries over unchanged.

    Args:
        full_frame: The full Persona_Labeled_Leads frame from
            :func:`build_persona_labeled_leads`.

    Returns:
        The six-column Campaign_Leads_Export frame, one row per Part 4 lead, in the
        same row order as ``full_frame``.

    Raises:
        ValueError: if ``full_frame`` is missing any of the six projected columns.
    """
    missing = [c for c in CAMPAIGN_LEADS_EXPORT_COLUMNS if c not in full_frame.columns]
    if missing:
        raise ValueError(
            f"full frame is missing Campaign_Leads_Export column(s) {missing}; "
            f"expected all of {CAMPAIGN_LEADS_EXPORT_COLUMNS} (Requirement 8.8)"
        )
    return full_frame[CAMPAIGN_LEADS_EXPORT_COLUMNS].reset_index(drop=True)


def build_exports(
    leads: pd.DataFrame,
    assignment: pd.DataFrame,
    cfg: Config | None = None,
    *,
    richer_attributes: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build both export variants in one call, output-last (Requirement 8.5).

    Convenience wrapper for the CLI / webapp orchestration: it assembles the richer
    attributes (building the Joined_Attribute_Set from ``cfg`` when they are not
    passed in), constructs the full Persona_Labeled_Leads, and projects the default
    Campaign_Leads_Export from it. Because it only *reads* the already-computed
    ``assignment`` (produced after clustering + profiling), calling it is the
    output-last step of a run -- it performs no clustering and writes no file
    (Requirement 8.5; file writing is wired in ``main.py``).

    Args:
        leads: The Part 4 leads universe (see :func:`load_part4_leads_universe`).
        assignment: The per-lead persona/group assignment.
        cfg: The pipeline Config; used only to build the richer attributes when
            ``richer_attributes`` is not supplied. Defaults to ``Config()``.
        richer_attributes: Optional pre-built Joined_Attribute_Set; when ``None`` it
            is built via :func:`part5_personas.join.build_joined_attributes`.

    Returns:
        A ``(campaign_export, full_labeled_leads)`` tuple: the default
        Campaign_Leads_Export first (Requirement 8.8), the optional full
        Persona_Labeled_Leads second (Requirement 8.9).
    """
    cfg = cfg or Config()
    if richer_attributes is None:
        richer_attributes, _report = build_joined_attributes(cfg)

    full = build_persona_labeled_leads(leads, richer_attributes, assignment)
    campaign = campaign_leads_export(full)
    return campaign, full
