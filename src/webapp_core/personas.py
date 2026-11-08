"""Persona_Core orchestration for the Persona_Page (Requirements 5, 6.8, 7).

A ``webapp_core``-style pure orchestration module that wires the
:mod:`part5_personas` (Persona_Pipeline) APIs into a single in-memory run for the
Streamlit Persona_Page. Like its siblings (``run_promo.py``, ``past_promos.py``)
it holds **no Streamlit imports** (Requirement 6.8) and adds **no modelling**
beyond the pipeline: it builds the Joined_Attribute_Set, runs the
level/grouping/clustering/profiling/naming stages, recovers the per-lead
persona/group assignment, and -- for the card surface -- computes a per-cell
Persona_Mix aligned onto the existing Part 4 cards without touching them.

Two public functions (design "Components and Interfaces"):

- :func:`run_personas` -- the single in-memory persona run. It is a pure,
  deterministic function of its inputs (Requirement 2.11), so the Persona_Page can
  wrap it in ``st.cache_data`` safely. For a ``campaign`` run it resolves the
  Campaign_Lead_Pool from either the current New Promo session leads passed as
  ``live_leads`` (Requirement 5.1) or a past promo's leads read from
  ``outputs/leads/`` / ``promo_leads.csv`` by ``promo_id`` (Requirement 5.3).
- :func:`persona_mix_by_cell` -- the per-cell Persona_Mix. It computes, per
  ``(promo_id, segment)`` decision-card cell, the share of that cell's leads
  assigned to each persona, normalized so the shares across the personas present
  in a non-empty cell sum to 100% (Requirement 7.1), and aligns them to the Part 4
  cards by ``(promo_id, segment)``. It **never mutates** a card (Requirements 7.3,
  7.4) and marks a cell ``available=False`` when it has no persona assignment
  (Requirement 7.5).

Reuse (design D1): Part 3 :func:`part3_segments.segments.assign_segments` and
Part 4 :func:`part4_cards.cards.build_cards` are available read-only for the live
New Promo flow (the caller passes the already-built live frames/cards in); no Part
1-4 module is modified. The mix is computed and attached entirely here.

Cell-key matching: the Part 4 cards carry the human segment label (for example
"Not Now"), while the per-cell leads files -- and so the cell keys recovered from
the leads universe -- carry the Part 4 Reporter's segment *slug* (for example
"not_now"). Both sides are reduced to the same slug via :func:`segment_slug`
(identical to ``part4_cards``/``webapp_core.past_promos`` slugging) before being
matched, so the mix lines up regardless of label spelling.

Determinism: every stochastic step runs through the seeded Persona_Pipeline
(seed ``cfg.random_seed`` = 42), and the per-lead labels are recovered by re-running
the same seeded preprocess -> cluster path the persona sets used internally, so a
lead's cluster label maps to the same :class:`~part5_personas.grouping.Persona`
(mirrors ``part5_personas.main._labels_for_run``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

import pandas as pd

from part5_personas.cluster import cluster
from part5_personas.config import Config
from part5_personas.export import (
    PERSONA_LABEL_COLUMN,
    labels_from_persona_sets,
    load_part4_leads_universe,
)
from part5_personas.grouping import (
    CLIENT_ID_COLUMN,
    LEVEL_BUSINESS_SEGMENT,
    LEVEL_CAMPAIGN,
    PersonaSet,
    build_persona_sets,
)
from part5_personas.join import build_joined_attributes
from part5_personas.naming import PersonaNamer, RuleBasedNamer
from part5_personas.preprocess import preprocess

# The cell key columns the Part 4 cards and the leads universe share.
PROMO_ID_COLUMN = "promo_id"
SEGMENT_COLUMN = "segment"
# The per-lead cell slug column attached from the leads universe.
SEGMENT_SLUG_COLUMN = "segment_slug"

# The value a mix share is normalized to sum to over a non-empty cell (Req 7.1).
MIX_TOTAL_PERCENT = 100.0


# Narration modes for run_personas: "rule" keeps the RuleBasedNamer (default);
# "ai" builds the BedrockNamer, which falls back to Mock text per persona.
NARRATION_RULE = "rule"
NARRATION_AI = "ai"
NARRATION_BEDROCK = "Bedrock"
NARRATION_DEMO = "Demo"


def segment_slug(segment: str) -> str:
    """Slugify a segment label exactly as the Part 4 Reporter does.

    Lowercases the label and collapses every run of non-alphanumeric characters
    into a single underscore ("Ready Toppers" -> "ready_toppers", "Willing but
    Stretched" -> "willing_but_stretched"), matching
    ``part4_cards.main._segment_slug`` / ``webapp_core.past_promos._segment_slug``
    so a card's human segment label and the per-cell leads filename slug reduce to
    the same key.
    """
    return re.sub(r"[^a-z0-9]+", "_", str(segment).lower())


@dataclass(frozen=True)
class PersonaRunSpec:
    """The immutable description of one persona run (design Data Models).

    Carries the Persona_Page's configuration choices. ``clustering_attributes``
    must be non-empty (Requirements 3.2, 3.3); ``k`` is an integer in ``[2, 6]``
    (Requirements 2.9, 2.10). ``grouping_attributes`` is the optional two-step
    partition ([] when unused, Requirement 3.8). ``business_segment_field`` names
    the business-segment column at ``business-segment`` level; only ``segment``
    (``customer_dna.segment``) is valid (Requirements 3.5, 3.20).
    ``campaign_pool`` is ``"live"`` (the New Promo session leads) or a ``promo_id``
    in ``{P001, P002, P003}`` at ``campaign`` level (Requirements 5.1, 5.3).
    """

    level: str = "all"
    clustering_attributes: list[str] = field(default_factory=list)
    grouping_attributes: list[str] = field(default_factory=list)
    k: int | None = None
    business_segment_field: str | None = None
    campaign_pool: str | None = None
    type_overrides: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PersonaMix:
    """The per-persona share of one decision-card cell's leads (Requirement 7).

    ``shares`` maps each persona name present in the cell to its share, and the
    shares sum to ~100.0 when the cell has at least one assigned lead
    (Requirement 7.1). ``available`` is ``False`` when the cell has no persona
    assignment at all, in which case ``shares`` is empty and the Persona_Page
    renders a "persona context unavailable" indication (Requirement 7.5).
    """

    promo_id: str
    segment: str
    shares: dict[str, float]
    available: bool


@dataclass(frozen=True)
class PersonaRunResult:
    """The in-memory result of one persona run (design Data Models).

    ``persona_sets`` is one :class:`~part5_personas.grouping.PersonaSet` per group
    (one with ``group_key == ""`` at level ``all``). ``labels`` is the per-lead
    assignment carrying ``client_id``, ``group``, ``persona_label`` and -- when a
    Part 4 leads universe was available -- the cell keys ``promo_id`` and
    ``segment_slug`` so :func:`persona_mix_by_cell` can scope shares per cell.
    ``joined_attributes`` is the Joined_Attribute_Set the run clustered on.
    """

    persona_sets: list[PersonaSet]
    labels: pd.DataFrame
    joined_attributes: pd.DataFrame
    # "Bedrock" when every persona text came from Bedrock, else "Demo" (any Mock
    # text, or a rule-based run). Defaulted so older constructors stay valid
    # (Requirement 6.11).
    narration_source: str = NARRATION_DEMO


# --------------------------------------------------------------------------- #
# run_personas                                                                #
# --------------------------------------------------------------------------- #
def _campaign_pool_ids(
    spec: PersonaRunSpec,
    cfg: Config,
    live_leads: pd.DataFrame | None,
) -> list[str]:
    """Resolve the Campaign_Lead_Pool client ids for a ``campaign`` run.

    The pool is either the current New Promo session leads (``campaign_pool ==
    "live"``, taken from ``live_leads``, Requirement 5.1) or a past promo's leads
    read from ``outputs/leads/`` by ``promo_id`` (Requirement 5.3). Returns the
    list of ``client_id`` values; an empty list is a valid (empty-audience) result
    that :func:`part5_personas.grouping.build_persona_sets` turns into an
    EmptyAudienceError (Requirement 5.6).
    """
    pool = spec.campaign_pool
    if pool is None:
        raise ValueError(
            "campaign level requires campaign_pool ('live' or a promo_id) "
            "(Requirements 5.1, 5.3)"
        )

    if pool == "live":
        if live_leads is None:
            raise ValueError(
                "campaign_pool 'live' requires the current New Promo run's leads "
                "to be passed as live_leads (Requirement 5.2)"
            )
        if CLIENT_ID_COLUMN not in live_leads.columns:
            raise ValueError(
                f"live_leads must carry a {CLIENT_ID_COLUMN!r} column "
                "(Requirement 5.1)"
            )
        return [str(cid) for cid in live_leads[CLIENT_ID_COLUMN].tolist()]

    # A past promo selected by promo_id -> its per-cell leads under outputs/leads/.
    universe = load_part4_leads_universe(cfg.leads_dir, promo_id=pool)
    return [str(cid) for cid in universe[CLIENT_ID_COLUMN].tolist()]


def _recover_labels(
    joined: pd.DataFrame,
    persona_sets: list[PersonaSet],
    spec: PersonaRunSpec,
    cfg: Config,
    campaign_pool_ids: Sequence[str] | None,
) -> pd.DataFrame:
    """Recover the per-lead ``client_id``/``group``/``persona_label`` assignment.

    ``build_persona_sets`` returns the named persona sets but not the per-lead
    cluster labels, so this reproduces the same seeded (seed ``cfg.random_seed``)
    preprocess -> cluster path per group that the sets used internally -- exactly
    as ``part5_personas.main._labels_for_run`` does for the CLI -- and bridges the
    recovered labels to persona names with
    :func:`part5_personas.export.labels_from_persona_sets`.

    Group membership mirrors ``build_persona_sets``'s own partition:

    - level ``all`` with no grouping attributes -> a single group keyed ``""``;
    - level ``business-segment`` -> one group per ``business_segment_field`` value;
    - level ``campaign`` -> the pool only, one group keyed ``""`` (the field is
      never a clustering or grouping feature here, Requirement 5.5);
    - any run with ``grouping_attributes`` -> one group per distinct combination.

    Only groups that were actually clustered (``too_small`` is ``False``) are
    re-clustered here; a too-small group contributes no labels (Requirement 3.10).
    """
    clustering = list(spec.clustering_attributes)
    grouping = list(spec.grouping_attributes)

    # Scope the frame to the campaign pool first so the per-group re-cluster sees
    # exactly the rows build_persona_sets saw (Requirement 5.4).
    frame = joined
    if spec.level == LEVEL_CAMPAIGN and campaign_pool_ids is not None:
        pool = set(campaign_pool_ids)
        frame = joined[joined[CLIENT_ID_COLUMN].isin(pool)].reset_index(drop=True)

    # Decide the grouping columns that define each PersonaSet's membership, and
    # drop the business_segment_field from the clustering columns where the
    # pipeline would have (business-segment always; campaign never clusters on it).
    if spec.level == LEVEL_BUSINESS_SEGMENT and spec.business_segment_field:
        group_cols = [spec.business_segment_field]
        clustering = [c for c in clustering if c != spec.business_segment_field]
    elif grouping:
        group_cols = list(grouping)
        if spec.level == LEVEL_CAMPAIGN and spec.business_segment_field:
            group_cols = [g for g in group_cols if g != spec.business_segment_field]
    else:
        group_cols = []

    if spec.level == LEVEL_CAMPAIGN and spec.business_segment_field:
        clustering = [c for c in clustering if c != spec.business_segment_field]

    sets_by_key = {ps.group_key: ps for ps in persona_sets}

    cluster_labels: dict[str, int] = {}
    group_of_client: dict[str, str] = {}

    def _cluster_group(group_key: str, group_frame: pd.DataFrame) -> None:
        persona_set = sets_by_key.get(group_key)
        if persona_set is None or persona_set.too_small:
            return
        group_frame = group_frame.reset_index(drop=True)
        preprocessed, cat_indices = preprocess(
            group_frame, clustering, spec.type_overrides or None
        )
        client_ids = group_frame[CLIENT_ID_COLUMN].reset_index(drop=True)
        labels, _elbow = cluster(
            preprocessed, cat_indices, client_ids, persona_set.k_used, cfg
        )
        for client_id, label in zip(client_ids.tolist(), labels.tolist()):
            cluster_labels[str(client_id)] = int(label)
            group_of_client[str(client_id)] = group_key

    if not group_cols:
        _cluster_group("", frame)
    else:
        present = frame.dropna(subset=group_cols)
        for key, group_frame in present.groupby(group_cols, sort=True, dropna=True):
            values = key if isinstance(key, tuple) else (key,)
            group_key = (
                str(values[0])
                if len(values) == 1
                else " | ".join(str(v) for v in values)
            )
            _cluster_group(group_key, group_frame)

    return labels_from_persona_sets(persona_sets, cluster_labels, group_of_client)


def _attach_cells(
    labels: pd.DataFrame,
    leads_universe: pd.DataFrame | None,
) -> pd.DataFrame:
    """Attach ``promo_id``/``segment_slug`` cell keys to the per-lead labels.

    :func:`persona_mix_by_cell` needs to know which decision-card cell each
    labeled lead belongs to. The Part 4 leads universe (from
    :func:`part5_personas.export.load_part4_leads_universe`) carries ``promo_id``
    and a ``segment_slug`` per lead; this left-joins those cell keys onto the
    labels by ``client_id`` so the mix can be scoped per cell. When no universe is
    available the labels are returned unchanged (the caller simply cannot compute a
    cell mix).

    Note the leads universe is de-duplicated to one row per ``client_id`` (first
    cell wins) by :func:`load_part4_leads_universe`, so a client that appears in
    more than one promo's cells is attributed to a single deterministic cell here.
    """
    if leads_universe is None or leads_universe.empty or labels.empty:
        return labels

    cell_cols = [CLIENT_ID_COLUMN]
    if PROMO_ID_COLUMN in leads_universe.columns:
        cell_cols.append(PROMO_ID_COLUMN)
    if SEGMENT_SLUG_COLUMN in leads_universe.columns:
        cell_cols.append(SEGMENT_SLUG_COLUMN)

    cells = leads_universe[cell_cols].drop_duplicates(subset=[CLIENT_ID_COLUMN])
    return labels.merge(cells, on=CLIENT_ID_COLUMN, how="left")


def run_personas(
    spec: PersonaRunSpec,
    namer: PersonaNamer | None = None,
    cfg: Config | None = None,
    *,
    live_leads: pd.DataFrame | None = None,
    narration: str = NARRATION_RULE,
) -> PersonaRunResult:
    """Run one in-memory persona generation and return its result (Requirements 3, 5).

    ``narration`` picks the namer when ``namer`` is not given: ``"rule"``
    (default) uses the RuleBasedNamer; ``"ai"`` builds a BedrockNamer here and
    records ``narration_source`` on the result (Requirement 6.11). Clustering is
    identical in both modes.

    Builds the Joined_Attribute_Set from ``cfg`` (Requirement 1), then runs the
    chosen level / two-step grouping / clustering / profiling / naming via
    :func:`part5_personas.grouping.build_persona_sets`, recovers the per-lead
    persona/group assignment, and attaches the Part 4 cell keys so the mix can be
    computed later. Deterministic given its inputs (Requirement 2.11), so the
    Persona_Page may cache it.

    Campaign pool resolution (Requirement 5): at ``campaign`` level the pool is the
    New Promo session leads passed as ``live_leads`` (``campaign_pool == "live"``,
    Requirement 5.1) or a past promo's leads read from ``outputs/leads/`` by
    ``promo_id`` (Requirement 5.3); an empty pool surfaces as the pipeline's
    EmptyAudienceError (Requirement 5.6).

    Args:
        spec: The run configuration.
        namer: The persona namer; defaults to a fresh
            :class:`~part5_personas.naming.RuleBasedNamer` (design D5). The
            pipeline depends only on the :class:`PersonaNamer` protocol, so a
            future Bedrock namer substitutes here with no other change.
        cfg: The Persona_Pipeline :class:`~part5_personas.config.Config`; defaults
            to ``Config()``.
        live_leads: The current New Promo run's sendable leads (session state),
            required only for a ``campaign_pool == "live"`` run (Requirement 5.1).

    Returns:
        A :class:`PersonaRunResult` carrying the persona sets, the per-lead labels
        (with cell keys when a leads universe was available), and the joined set.
    """
    cfg = cfg or Config()
    bedrock_namer = None
    if namer is None:
        if narration == NARRATION_AI:
            from ai.persona_narrator import BedrockNamer

            bedrock_namer = BedrockNamer()
            namer = bedrock_namer
        else:
            namer = RuleBasedNamer()

    if not spec.clustering_attributes:
        raise ValueError(
            "spec.clustering_attributes must contain at least one column "
            "(Requirement 3.3)"
        )

    # 1. Build the Joined_Attribute_Set (join stage; the only input gate).
    joined, _report = build_joined_attributes(cfg)

    # 2. Resolve the campaign pool (campaign level only).
    campaign_pool_ids: list[str] | None = None
    if spec.level == LEVEL_CAMPAIGN:
        campaign_pool_ids = _campaign_pool_ids(spec, cfg, live_leads)

    # 3. Build the named persona sets for the chosen level/grouping.
    persona_sets = build_persona_sets(
        joined,
        level=spec.level,
        clustering_attributes=list(spec.clustering_attributes),
        grouping_attributes=list(spec.grouping_attributes),
        k=spec.k,
        business_segment_field=spec.business_segment_field,
        campaign_pool_ids=campaign_pool_ids,
        namer=namer,
        cfg=cfg,
        type_overrides=spec.type_overrides or None,
    )

    # 4. Recover the per-lead assignment via the same seeded cluster path.
    labels = _recover_labels(joined, persona_sets, spec, cfg, campaign_pool_ids)

    # 5. Attach the Part 4 cell keys so a per-cell mix can be computed, when the
    #    leads universe is available on disk.
    leads_universe: pd.DataFrame | None = None
    try:
        leads_universe = load_part4_leads_universe(cfg.leads_dir)
    except FileNotFoundError:
        leads_universe = None
    labels = _attach_cells(labels, leads_universe)

    source = NARRATION_DEMO
    if bedrock_namer is not None:
        used = bedrock_namer.sources
        if used and all(v == NARRATION_BEDROCK for v in used.values()):
            source = NARRATION_BEDROCK

    return PersonaRunResult(
        persona_sets=persona_sets,
        labels=labels,
        joined_attributes=joined,
        narration_source=source,
    )


# --------------------------------------------------------------------------- #
# persona_mix_by_cell                                                         #
# --------------------------------------------------------------------------- #
def persona_mix_by_cell(
    labels: pd.DataFrame,
    cards: Sequence[Mapping],
) -> dict[tuple[str, str], PersonaMix]:
    """Per-cell Persona_Mix aligned onto the existing Part 4 cards (Requirement 7).

    For every Part 4 card (one per ``(promo_id, segment)`` cell) computes the share
    of that cell's leads assigned to each persona. The shares are normalized so the
    personas present in a non-empty cell **sum to 100.0** (Requirement 7.1). A cell
    with no persona assignment is marked ``available=False`` with empty ``shares``
    so the Persona_Page shows a "persona context unavailable" indication
    (Requirement 7.5).

    The function is pure and **never mutates** a card or the ``labels`` frame
    (Requirements 7.3, 7.4): it only reads each card's ``promo_id``/``segment`` to
    key the result and reads ``labels`` to count assignments. A card's human
    segment label is slugged via :func:`segment_slug` to match the per-lead
    ``segment_slug`` cell key. The returned dict is keyed by the card's
    ``(promo_id, segment)`` (the original label, not the slug) so the page can look
    up each card's mix by the values it already holds.

    Args:
        labels: The per-lead assignment from :func:`run_personas` -- must carry a
            persona label column (``persona_label`` or the design's
            ``persona_name``) and the cell keys ``promo_id`` and ``segment_slug``. A
            lead with an empty persona label (e.g. an out-of-pool campaign lead)
            does not contribute to any cell's mix.
        cards: The Part 4 cards, each a mapping carrying ``promo_id`` and
            ``segment``. Cards are read only.

    Returns:
        ``{(promo_id, segment): PersonaMix}`` -- one entry per card, keyed by the
        card's original ``promo_id`` and ``segment`` values.
    """
    label_col = _resolve_label_column(labels)
    counts_by_slug_cell = _counts_by_cell(labels, label_col)

    result: dict[tuple[str, str], PersonaMix] = {}
    for card in cards:
        promo_id = str(card["promo_id"])
        segment = str(card["segment"])
        key = (promo_id, segment)
        if key in result:
            continue

        slug_key = (promo_id, segment_slug(segment))
        counts = counts_by_slug_cell.get(slug_key, {})
        total = sum(counts.values())
        if total <= 0:
            # No persona assignment for this cell -> unavailable (Requirement 7.5).
            result[key] = PersonaMix(
                promo_id=promo_id,
                segment=segment,
                shares={},
                available=False,
            )
            continue

        # Normalize to shares summing to 100.0 over the personas present (Req 7.1).
        shares = {
            name: count / total * MIX_TOTAL_PERCENT
            for name, count in counts.items()
        }
        result[key] = PersonaMix(
            promo_id=promo_id,
            segment=segment,
            shares=shares,
            available=True,
        )

    return result


def _resolve_label_column(labels: pd.DataFrame) -> str:
    """Return the persona-label column name present on ``labels``.

    Accepts either the Requirement 8 ``persona_label`` name or the design's
    ``persona_name`` name, matching :func:`part5_personas.export` which tolerates
    both.
    """
    if PERSONA_LABEL_COLUMN in labels.columns:
        return PERSONA_LABEL_COLUMN
    if "persona_name" in labels.columns:
        return "persona_name"
    raise ValueError(
        f"labels must carry a persona label column ({PERSONA_LABEL_COLUMN!r} or "
        "'persona_name')"
    )


def _counts_by_cell(
    labels: pd.DataFrame,
    label_col: str,
) -> dict[tuple[str, str], dict[str, int]]:
    """Count assigned leads per persona within each ``(promo_id, segment_slug)`` cell.

    Leads with a missing/empty persona label or missing cell key are skipped, so an
    out-of-pool campaign lead (empty label) never contributes to a mix. The cell key
    uses the ``segment_slug`` attached from the leads universe; the caller slugs each
    card's human segment label the same way to look the counts up. Returns a
    ``{(promo_id, segment_slug): {persona_name: count}}`` mapping.
    """
    counts: dict[tuple[str, str], dict[str, int]] = {}
    if labels.empty:
        return counts
    if (
        PROMO_ID_COLUMN not in labels.columns
        or SEGMENT_SLUG_COLUMN not in labels.columns
    ):
        # No cell keys attached -> nothing can be scoped to a card cell.
        return counts

    for _idx, row in labels.iterrows():
        persona = row.get(label_col)
        promo_id = row.get(PROMO_ID_COLUMN)
        slug = row.get(SEGMENT_SLUG_COLUMN)
        if persona is None or pd.isna(persona) or str(persona) == "":
            continue
        if promo_id is None or pd.isna(promo_id):
            continue
        if slug is None or pd.isna(slug):
            continue
        key = (str(promo_id), str(slug))
        cell = counts.setdefault(key, {})
        cell[str(persona)] = cell.get(str(persona), 0) + 1

    return counts


# --------------------------------------------------------------------------- #
# expected_joiners_by_persona (task 13.4; Requirements 7.1-7.5, 7.7, 7.8)     #
# --------------------------------------------------------------------------- #
OTHER_PERSONAS_NAME = "Other personas"
UNLABELED_NAME = "Not in this persona run"
SAME_MESSAGE_ACTION = "Same message as above."
CHANNEL_FALLBACK_PREFIX = "Reachable on every channel about equally"
NO_SENDABLE_TAKEAWAY = "No sendable leads in this card."
EQUAL_TAKEAWAY = "Personas respond about equally; one message fits this card."

# A persona folds into "Other personas" below this lead share (percent) or count.
FOLD_MIN_SHARE_PCT = 5.0
FOLD_MIN_LEADS = 5
# The highest persona rate must be at least this multiple of the lowest to count
# as distinct (exactly 1.2x is distinct; a tiny tolerance absorbs float noise).
DISTINCT_RATE_RATIO = 1.2
_RATE_TOLERANCE = 1e-9

ROW_KIND_PERSONA = "persona"
ROW_KIND_OTHER = "other"
ROW_KIND_UNLABELED = "unlabeled"


@dataclass(frozen=True)
class PersonaJoinerRow:
    """One row of a card's expected-joiners-by-persona table.

    ``show_joiners`` is ``False`` only for the folded "Other personas" row, whose
    expected joiners are kept for the total but not displayed (lead count only).
    ``kind`` is ``persona``, ``other`` or ``unlabeled``.
    """

    name: str
    leads: int
    lead_share_pct: float
    expected_joiners: float
    rate_pct: float
    action: str
    kind: str = ROW_KIND_PERSONA
    show_joiners: bool = True


@dataclass(frozen=True)
class CardPersonaBreakdown:
    """The persona breakdown of one decision card's sendable leads."""

    promo_id: str
    segment: str
    rows: tuple[PersonaJoinerRow, ...]
    total_leads: int
    total_expected_joiners: float
    takeaway: str
    # Task 13.5: the persona the takeaway names (None for the equal / empty case)
    # and the action to show for it (the equal line when there is no such persona).
    takeaway_persona: str | None = None
    takeaway_action: str = ""


def _rate_pct(joiners: float, leads: int) -> float:
    return joiners / leads * 100.0 if leads > 0 else 0.0


def _first_labels_per_client(labels: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """Map ``str(client_id)`` -> ``(group, persona_label)``.

    Normally one row per client. If a client has several rows (e.g. across
    groups) the first by sorted ``(client_id, group, persona_label)`` order wins,
    so the result is deterministic. Rows with an empty label are ignored.
    """
    if labels is None or labels.empty:
        return {}
    label_col = _resolve_label_column(labels)
    group_col = "group" if "group" in labels.columns else None
    triples = []
    for _i, row in labels.iterrows():
        label = row[label_col]
        if label is None or pd.isna(label) or str(label) == "":
            continue
        group = "" if group_col is None or pd.isna(row[group_col]) else str(row[group_col])
        triples.append((str(row[CLIENT_ID_COLUMN]), group, str(label)))
    triples.sort()
    out: dict[str, tuple[str, str]] = {}
    for cid, group, label in triples:
        out.setdefault(cid, (group, label))
    return out


def _persona_action_lookup(persona_sets: Sequence) -> dict[tuple[str, str], str]:
    """``(group, persona name) -> first non-channel-fallback action`` ("" if none)."""
    lookup: dict[tuple[str, str], str] = {}
    for ps in persona_sets:
        for persona in ps.personas:
            chosen = ""
            for action in persona.actions:
                if not str(action).startswith(CHANNEL_FALLBACK_PREFIX):
                    chosen = str(action)
                    break
            lookup.setdefault((str(ps.group_key), str(persona.name)), chosen)
    return lookup


def _takeaway(shown: list[PersonaJoinerRow], total_joiners: float) -> str:
    if len(shown) < 2:
        return EQUAL_TAKEAWAY
    rates = [r.rate_pct for r in shown]
    hi, lo = max(rates), min(rates)
    distinct = hi > 0 if lo == 0 else hi >= DISTINCT_RATE_RATIO * lo - _RATE_TOLERANCE
    if not distinct:
        return EQUAL_TAKEAWAY
    top = sorted(shown, key=lambda r: (-r.rate_pct, -r.expected_joiners, r.name))[0]
    share_j = top.expected_joiners / total_joiners * 100.0 if total_joiners > 0 else 0.0
    return (
        f"{top.name} is {top.lead_share_pct:.0f}% of leads but {share_j:.0f}% "
        "of expected joiners. Lead with its hook."
    )



NO_GROUP_NAME = "Not in a clustered group"
ALL_LEADS_GROUP_NAME = "All leads"
TOO_FEW_TEMPLATE = (
    "Only {n} leads from {group} in this card; too few for a persona breakdown."
)


def _takeaway_parts(
    shown: list[PersonaJoinerRow], total_joiners: float
) -> tuple[str, PersonaJoinerRow | None]:
    """The takeaway text and the persona row it names (None for the equal case)."""
    text = _takeaway(shown, total_joiners)
    if text == EQUAL_TAKEAWAY:
        return text, None
    top = sorted(shown, key=lambda r: (-r.rate_pct, -r.expected_joiners, r.name))[0]
    return text, top


def _build_rows(
    frame: pd.DataFrame,
    label_by_client: Mapping[str, tuple[str, str]],
    lookup: Mapping[tuple[str, str], str],
    multi_group: bool,
    with_unlabeled: bool = True,
) -> tuple[list[PersonaJoinerRow], list[PersonaJoinerRow], dict[str, tuple[str, str]]]:
    """Build the persona rows for ``frame`` (shared by the 13.4 and 13.5 functions).

    Returns ``(all rows, persona rows only, display name -> (group, name))``.
    """
    n_leads = len(frame)
    counts: dict[tuple[str, str], int] = {}
    sums: dict[tuple[str, str], float] = {}
    un_n, un_sum = 0, 0.0
    for cid, p in zip(frame[CLIENT_ID_COLUMN].tolist(), frame["p_join"].tolist()):
        key = label_by_client.get(str(cid))
        p = float(p)
        if key is None:
            un_n += 1
            un_sum += p
        else:
            counts[key] = counts.get(key, 0) + 1
            sums[key] = sums.get(key, 0.0) + p

    shown: list[tuple[str, int, float, str, tuple[str, str]]] = []
    other_n, other_sum = 0, 0.0
    for key in counts:
        n, s = counts[key], sums[key]
        if n * 100 < FOLD_MIN_SHARE_PCT * n_leads or n < FOLD_MIN_LEADS:
            other_n += n
            other_sum += s
            continue
        group, name = key
        display = f"{group}: {name}" if multi_group else name
        shown.append((display, n, s, lookup.get(key, ""), key))
    shown.sort(key=lambda t: (-t[2], t[0]))

    rows: list[PersonaJoinerRow] = []
    keys: dict[str, tuple[str, str]] = {}
    used_actions: set[str] = set()
    for display, n, s, action, key in shown:
        if action and action in used_actions:
            action = SAME_MESSAGE_ACTION
        elif action:
            used_actions.add(action)
        keys[display] = key
        rows.append(
            PersonaJoinerRow(display, n, n / n_leads * 100.0, s, _rate_pct(s, n), action)
        )
    persona_rows = list(rows)
    if other_n:
        rows.append(
            PersonaJoinerRow(
                OTHER_PERSONAS_NAME, other_n, other_n / n_leads * 100.0, other_sum,
                _rate_pct(other_sum, other_n), "", ROW_KIND_OTHER, False,
            )
        )
    if un_n and with_unlabeled:
        rows.append(
            PersonaJoinerRow(
                UNLABELED_NAME, un_n, un_n / n_leads * 100.0, un_sum,
                _rate_pct(un_sum, un_n), "", ROW_KIND_UNLABELED, True,
            )
        )
    return rows, persona_rows, keys


def _n_groups(persona_sets: Sequence, label_by_client: Mapping) -> int:
    n = len({str(ps.group_key) for ps in persona_sets})
    return n or len({g for g, _ in label_by_client.values()})


def expected_joiners_by_persona(
    cards: Sequence[Mapping],
    sendable_by_segment: Mapping[str, pd.DataFrame],
    labels: pd.DataFrame,
    persona_sets: Sequence[PersonaSet],
    drop_empty: bool = False,
) -> list[CardPersonaBreakdown]:
    """Per-card expected joiners split by persona (Requirements 7.1-7.5, 7.7, 7.8).

    For each card, its sendable leads (``sendable_by_segment[card['segment']]``)
    are matched to ``labels`` by ``str(client_id)``. Rows are keyed by
    ``(group, persona_label)`` so same-named personas from different groups are
    never merged; the display name is prefixed ``"<group>: "`` only when the
    persona run has more than one group. Personas under 5% of the card's leads or
    under 5 leads fold into one "Other personas" row (lead count only in the UI);
    unlabeled leads form a final "Not in this persona run" row, present only when
    non-empty. The total over all rows equals the sum of ``p_join`` over the
    card's sendable leads. ``drop_empty=True`` omits cards with no sendable leads
    (Requirement 7.6c). Pure; inputs are never mutated.
    """
    lookup = _persona_action_lookup(persona_sets)
    label_by_client = _first_labels_per_client(labels)
    multi_group = _n_groups(persona_sets, label_by_client) > 1

    out: list[CardPersonaBreakdown] = []
    for card in cards:
        promo_id = str(card.get("promo_id", ""))
        segment = str(card["segment"])
        frame = sendable_by_segment.get(segment)
        if frame is None or len(frame) == 0:
            if not drop_empty:
                out.append(
                    CardPersonaBreakdown(
                        promo_id, segment, (), 0, 0.0, NO_SENDABLE_TAKEAWAY
                    )
                )
            continue
        rows, persona_rows, keys = _build_rows(frame, label_by_client, lookup, multi_group)
        total = float(sum(r.expected_joiners for r in rows))
        text, top = _takeaway_parts(persona_rows, total)
        if top is None:
            t_name, t_action = None, EQUAL_TAKEAWAY
        else:
            t_name, t_action = top.name, lookup.get(keys[top.name], "")
        out.append(
            CardPersonaBreakdown(
                promo_id, segment, tuple(rows), len(frame), total, text, t_name, t_action
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Group-scoped breakdown and all-groups summary (task 13.5)                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GroupCardBreakdown:
    """One card's persona breakdown restricted to a single group's leads.

    ``total_*`` cover only the group's leads; ``card_expected_joiners`` and
    ``card_leads`` carry the card's overall figures (all sendable leads) for the
    note. ``too_few`` is ``True`` when every persona row folded into "Other
    personas", so the page shows :attr:`too_few_message` instead of a table.
    Persona names carry no group prefix.
    """

    promo_id: str
    segment: str
    group: str
    rows: tuple[PersonaJoinerRow, ...]
    total_leads: int
    total_expected_joiners: float
    card_expected_joiners: float
    card_leads: int
    takeaway: str
    takeaway_persona: str | None
    takeaway_action: str
    too_few: bool

    @property
    def too_few_message(self) -> str:
        return TOO_FEW_TEMPLATE.format(n=self.total_leads, group=self.group)


def expected_joiners_for_group(
    cards: Sequence[Mapping],
    sendable_by_segment: Mapping[str, pd.DataFrame],
    labels: pd.DataFrame,
    persona_sets: Sequence[PersonaSet],
    group: str,
) -> list[GroupCardBreakdown]:
    """Per-card breakdown of the sendable leads labelled into ``group``.

    Same fold / ordering / takeaway rules as :func:`expected_joiners_by_persona`,
    using only ``group``'s personas. Cards with no sendable leads in the group are
    dropped (including cards with no sendable leads at all). There is no
    "Not in this persona run" row: every lead considered is in the group.
    """
    group = str(group)
    lookup = _persona_action_lookup(persona_sets)
    in_group = {
        cid: key for cid, key in _first_labels_per_client(labels).items()
        if key[0] == group
    }
    out: list[GroupCardBreakdown] = []
    for card in cards:
        segment = str(card["segment"])
        frame = sendable_by_segment.get(segment)
        if frame is None or len(frame) == 0:
            continue
        mask = frame[CLIENT_ID_COLUMN].astype(str).isin(in_group.keys())
        scoped = frame[mask]
        if len(scoped) == 0:
            continue
        rows, persona_rows, keys = _build_rows(scoped, in_group, lookup, False, False)
        total = float(sum(r.expected_joiners for r in rows))
        text, top = _takeaway_parts(persona_rows, total)
        if top is None:
            t_name, t_action = None, EQUAL_TAKEAWAY
        else:
            t_name, t_action = top.name, lookup.get(keys[top.name], "")
        out.append(
            GroupCardBreakdown(
                str(card.get("promo_id", "")), segment, group, tuple(rows),
                len(scoped), total, float(frame["p_join"].astype(float).sum()),
                len(frame), text, t_name, t_action, not persona_rows,
            )
        )
    return out


@dataclass(frozen=True)
class GroupSummaryRow:
    """One group's slice of a card. ``group`` is ``None`` for the no-group row."""

    name: str
    group: str | None
    leads: int
    lead_share_pct: float
    expected_joiners: float


@dataclass(frozen=True)
class CardGroupSummary:
    """The "All groups" summary of one card: one row per group."""

    promo_id: str
    segment: str
    rows: tuple[GroupSummaryRow, ...]
    total_leads: int
    total_expected_joiners: float


def group_summary_by_card(
    cards: Sequence[Mapping],
    sendable_by_segment: Mapping[str, pd.DataFrame],
    labels: pd.DataFrame,
    persona_sets: Sequence[PersonaSet],
) -> list[CardGroupSummary]:
    """Per-card leads, share and expected joiners by group (Requirement 7.6b).

    Rows are ordered by group key ascending (a ``""`` single-group key is shown
    as "All leads"). Too-small groups are never clustered, so
    ``run_personas`` emits no label rows for their leads; those leads (and any
    other unlabeled lead) form the single "Not in a clustered group" row, added
    last and only when non-empty. Cards with no sendable leads are dropped. The
    total equals the card's sum of ``p_join``.
    """
    label_by_client = _first_labels_per_client(labels)
    out: list[CardGroupSummary] = []
    for card in cards:
        segment = str(card["segment"])
        frame = sendable_by_segment.get(segment)
        if frame is None or len(frame) == 0:
            continue
        counts: dict[str, int] = {}
        sums: dict[str, float] = {}
        un_n, un_sum = 0, 0.0
        for cid, p in zip(frame[CLIENT_ID_COLUMN].tolist(), frame["p_join"].tolist()):
            key = label_by_client.get(str(cid))
            p = float(p)
            if key is None:
                un_n += 1
                un_sum += p
            else:
                counts[key[0]] = counts.get(key[0], 0) + 1
                sums[key[0]] = sums.get(key[0], 0.0) + p
        n_leads = len(frame)
        rows = [
            GroupSummaryRow(
                g or ALL_LEADS_GROUP_NAME, g, counts[g], counts[g] / n_leads * 100.0, sums[g]
            )
            for g in sorted(counts)
        ]
        if un_n:
            rows.append(
                GroupSummaryRow(NO_GROUP_NAME, None, un_n, un_n / n_leads * 100.0, un_sum)
            )
        out.append(
            CardGroupSummary(
                str(card.get("promo_id", "")), segment, tuple(rows), n_leads,
                float(sum(r.expected_joiners for r in rows)),
            )
        )
    return out
