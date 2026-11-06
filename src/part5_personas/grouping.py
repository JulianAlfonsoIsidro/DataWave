"""Clustering levels and the two-step grouping flow for the Persona_Pipeline.

Orchestrates the persona construction for a single run: it partitions the lead
frame into groups according to the chosen clustering *level* / two-step grouping
attributes, then for each group runs the preprocess -> cluster -> profile -> name
pipeline and assembles a :class:`PersonaSet`. Pure functions over
pandas/numpy/kmodes with no Streamlit imports.

This is the module that realizes Requirements 3.4-3.11 and 5.4-5.6.

Levels (Requirement 3.4; default ``all``):

- ``all`` (:data:`LEVEL_ALL`) -- one :class:`PersonaSet` over the whole lead list,
  with ``group_key == ""`` (Requirement 3.4).
- ``business-segment`` (:data:`LEVEL_BUSINESS_SEGMENT`) -- one :class:`PersonaSet`
  per distinct non-null value of the chosen ``Business_Segment_Field`` column
  (``customer_dna.segment``, :data:`BUSINESS_SEGMENT_FIELD`, the only supported
  field; the Part 3 ``Segment_Label`` is per client and per promo and is rejected
  with :class:`InvalidSegmentFieldError`); the field name is a parameter and must
  already be present as a column on ``frame`` (Requirements 3.5, 3.6, 3.20). If the field has no usable (non-null) values, a :class:`ValueError` naming
  the field is raised and no assignments are produced (Requirement 3.7).
- ``campaign`` (:data:`LEVEL_CAMPAIGN`) -- cluster only the chosen campaign pool,
  excluding every lead outside the pool, and never use any ``Business_Segment_Field``
  as a clustering feature (Requirements 5.4, 5.5). When the pool is empty the run
  reports empty-audience *without clustering* by raising
  :class:`EmptyAudienceError` (Requirement 5.6).

Two-step flow (Requirements 3.8, 3.9): when ``grouping_attributes`` are provided,
the leads are partitioned by each distinct *combination* of grouping-attribute
values, then each resulting group is clustered on the ``clustering_attributes``
with its own k. This generalizes the business-segment partition (a single-column
grouping). Group iteration order is deterministic -- groups are visited in
ascending group-key order -- so results are reproducible.

Group-size handling (Requirements 3.10, 3.11):

- A group whose lead count is **below** ``cfg.min_group_size`` is flagged "too small
  to cluster": its :class:`PersonaSet` has ``too_small=True`` and
  ``personas == []`` and is **not** clustered (Requirement 3.10).
- A group at or above ``cfg.min_group_size`` but below the requested ``k`` has k
  **capped** to the group's lead count (``k_used = min(k, group_size)``) before
  clustering; the capped value is recorded in :attr:`PersonaSet.k_used`
  (Requirement 3.11).

Each clustered group threads a ``taken`` name set across its personas so names are
unique within the set, and personas are built in ascending cluster-label order
(Requirement 4.9). The ``namer`` is injected (defaulting to a
:class:`~part5_personas.naming.RuleBasedNamer`) so the stage depends only on the
:class:`~part5_personas.naming.PersonaNamer` Protocol (design D5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from part5_personas.cluster import cluster, validate_k
from part5_personas.config import Config
from part5_personas.naming import PersonaNamer, RuleBasedNamer
from part5_personas.preprocess import classify_types, preprocess
from part5_personas.profile import CHANNEL_FLAGS, PersonaProfile, build_profiles

# --- level identifiers (Requirement 3.4) -------------------------------------
LEVEL_ALL = "all"
LEVEL_BUSINESS_SEGMENT = "business-segment"
LEVEL_CAMPAIGN = "campaign"

# The only supported business-segment grouping field (Requirements 3.5, 3.20):
# customer_dna.segment. The Part 3 Segment_Label is per (client, promo) and is
# not a grouping field.
BUSINESS_SEGMENT_FIELD = "segment"
BUSINESS_SEGMENT_FIELD_OPTIONS = (BUSINESS_SEGMENT_FIELD,)

# The column carrying each lead's identifier across every source frame.
CLIENT_ID_COLUMN = "client_id"


@dataclass(frozen=True)
class Persona:
    """One named persona within a :class:`PersonaSet` (design Data Models).

    Pairs the human-facing naming output (``name``/``description``/``actions``)
    with the :class:`~part5_personas.profile.PersonaProfile` it was derived from.
    Names are unique within a set (Requirement 4.9) and ``actions`` always holds
    2 or 3 entries (Requirement 4.5).
    """

    name: str
    """Unique, human-facing persona name within its set (Requirement 4.9)."""
    description: str
    """One-line description derived from the profile (Requirement 4.4)."""
    actions: list[str]
    """2-3 recommended campaign actions (Requirement 4.5)."""
    profile: PersonaProfile
    """The computed profile this persona summarizes."""


@dataclass(frozen=True)
class PersonaSet:
    """The personas produced for one group of leads (design Data Models).

    A group is the whole lead list (level ``all``), one business-segment field
    value (level ``business-segment``), the campaign pool (level ``campaign``), or
    one combination of two-step ``grouping_attributes`` values. A group below
    ``cfg.min_group_size`` yields ``too_small=True`` with ``personas == []`` and is
    never clustered (Requirement 3.10); otherwise ``k_used`` is the actually used
    cluster count, possibly capped to the group's size (Requirement 3.11).
    """

    group_key: str
    """``""`` for level ``all``; the segment value / promo pool / grouping-combo
    key otherwise."""
    personas: list[Persona]
    """Personas in ascending cluster-label order; empty when ``too_small``
    (zero-size personas omitted, Requirement 4.7)."""
    k_used: int
    """The cluster count actually used, possibly capped (Requirement 3.11); ``0``
    for a too-small group."""
    elbow_costs: dict[int, float]
    """``{k: cost}`` elbow sweep over the candidate k range (Requirement 2.12);
    empty for a too-small group."""
    too_small: bool = False
    """``True`` when the group is below ``cfg.min_group_size`` (Requirement 3.10)."""


class EmptyAudienceError(ValueError):
    """Raised when a ``campaign`` run's pool contains no leads (Requirement 5.6).

    Signals the empty-audience case *before* any clustering is attempted so the
    caller (CLI / webapp_core) can surface an "empty audience" message and skip the
    k-prototypes fit entirely, rather than fitting on an empty frame. It subclasses
    :class:`ValueError` so existing broad exception handling still treats it as a
    halt, while callers that want the specific empty-audience behaviour can catch it
    by type.
    """


class InvalidSegmentFieldError(ValueError):
    """Raised when the ``business-segment`` grouping field is missing or unusable.

    The only supported Business_Segment_Field is ``customer_dna.segment``
    (:data:`BUSINESS_SEGMENT_FIELD`); the Part 3 Segment_Label is per client and
    per promo, so it cannot group customers (Requirements 3.5, 3.20).
    """


def _segment_field_message(field: str | None) -> str:
    """Actionable message for an unusable business-segment field (Req 3.5, 3.20)."""
    valid = (
        f"Valid option: {BUSINESS_SEGMENT_FIELD!r} (the customer_dna.segment "
        "field: Affluent-Gold, Affluent-Preferred, Mass, Mid-Market). "
        "The Part 3 segment label is assigned per client and per promo, "
        "so it cannot group customers."
    )
    if field:
        return (
            f"business_segment_field {field!r} is not available in the joined "
            f"data. {valid}"
        )
    return f"business-segment level needs a business_segment_field, but none was given. {valid}"


def _group_key_str(value: object) -> str:
    """Render a single grouping value as a deterministic string group key."""
    return str(value)


def _combination_key(values: tuple[object, ...]) -> str:
    """Render a tuple of grouping-attribute values as one string group key.

    A single grouping attribute renders as its lone value (so a business-segment
    group key is just the segment value); multiple attributes render as their
    values joined by " | " in grouping-attribute order, which is deterministic.
    """
    if len(values) == 1:
        return _group_key_str(values[0])
    return " | ".join(_group_key_str(v) for v in values)


def _assemble_personas(
    raw_group: pd.DataFrame,
    clustering_attributes: list[str],
    k_requested: int,
    namer: PersonaNamer,
    cfg: Config,
    type_overrides: dict[str, str] | None,
) -> tuple[list[Persona], int, dict[int, float]]:
    """Preprocess -> cluster -> profile -> name one already-sized group.

    The group is assumed to satisfy ``len(raw_group) >= cfg.min_group_size`` (the
    too-small gate runs in the caller). ``k_requested`` is the run's requested k
    *already capped* to the group size by the caller (Requirement 3.11).

    Steps:

    1. Classify the clustering attributes into numeric/categorical (honoring
       ``type_overrides``) for profiling (Requirements 2.2, 2.3).
    2. Preprocess the clustering attributes into the standardized / imputed
       k-prototypes matrix plus categorical indices (Requirement 2.4-2.7).
    3. Cluster at ``k_requested`` on that matrix, carrying the elbow sweep
       (Requirements 2.1, 2.12).
    4. Build one :class:`~part5_personas.profile.PersonaProfile` per non-empty
       cluster from the **raw** (pre-scaling) attribute values (Requirement 4.7).
    5. Name the profiles in ascending cluster-label order, threading a ``taken``
       set so names are unique within the set (Requirement 4.9), and wrap each into
       a :class:`Persona`.

    Returns:
        A ``(personas, k_used, elbow_costs)`` tuple. ``personas`` is ordered by
        ascending cluster label with zero-size clusters omitted; ``k_used`` is the
        k that was clustered with; ``elbow_costs`` is the ``{k: cost}`` sweep.
    """
    raw_group = raw_group.reset_index(drop=True)
    numeric_cols, categorical_cols = classify_types(
        raw_group, clustering_attributes, type_overrides
    )

    preprocessed, cat_indices = preprocess(
        raw_group, clustering_attributes, type_overrides
    )

    labels, elbow = cluster(
        preprocessed,
        cat_indices,
        raw_group[CLIENT_ID_COLUMN],
        k_requested,
        cfg,
    )

    # Profiles use the RAW (pre-scaling) attribute values, not the scaled matrix.
    profiles = build_profiles(
        raw_group[clustering_attributes],
        labels,
        numeric_cols,
        categorical_cols,
        # Channel flags come from the group's full joined rows so they are present
        # even when they are not clustering attributes (task 8.1e).
        reach_frame=raw_group[
            [c for _, c in CHANNEL_FLAGS if c in raw_group.columns]
        ],
    )

    # Name in ascending cluster-label order (build_profiles already orders that
    # way), threading a taken set so names are unique within the set (Req 4.9).
    personas: list[Persona] = []
    taken: set[str] = set()
    for profile in profiles:
        naming = namer.name(profile, taken)
        taken.add(naming["name"])
        personas.append(
            Persona(
                name=naming["name"],
                description=naming["description"],
                actions=list(naming["actions"]),
                profile=profile,
            )
        )

    return personas, k_requested, elbow


def _persona_set_for_group(
    group_key: str,
    raw_group: pd.DataFrame,
    clustering_attributes: list[str],
    k: int | None,
    namer: PersonaNamer,
    cfg: Config,
    type_overrides: dict[str, str] | None,
) -> PersonaSet:
    """Build the :class:`PersonaSet` for one group, applying the size rules.

    Group-size handling (Requirements 3.10, 3.11), in order:

    1. **Too-small gate (Requirement 3.10):** if ``len(raw_group) <
       cfg.min_group_size`` the group is "too small to cluster" -- return a
       :class:`PersonaSet` with ``too_small=True``, ``personas=[]``, ``k_used=0`` and
       an empty elbow sweep, *without* clustering.
    2. **k-cap (Requirement 3.11):** otherwise validate/default the requested k,
       then cap it to the group size (``k_used = min(k, group_size)``) so a group
       at/above ``min_group_size`` but below the requested k clusters with the
       capped k. The capped value is carried in ``PersonaSet.k_used``.

    The validated/defaulted k is computed with
    :func:`~part5_personas.cluster.validate_k`, so an invalid k still raises before
    any clustering (Requirement 2.10).
    """
    group_size = len(raw_group)

    # 1. Too-small gate (Requirement 3.10): flag and do not cluster.
    if group_size < cfg.min_group_size:
        return PersonaSet(
            group_key=group_key,
            personas=[],
            k_used=0,
            elbow_costs={},
            too_small=True,
        )

    # 2. Validate/default the requested k, then cap it to the group size
    #    (Requirement 3.11). validate_k raises on an invalid k (Requirement 2.10).
    validated_k = validate_k(k, cfg)
    k_used = min(validated_k, group_size)

    personas, k_used, elbow = _assemble_personas(
        raw_group,
        clustering_attributes,
        k_used,
        namer,
        cfg,
        type_overrides,
    )

    return PersonaSet(
        group_key=group_key,
        personas=personas,
        k_used=k_used,
        elbow_costs=elbow,
        too_small=False,
    )


def _partition_by_attributes(
    frame: pd.DataFrame,
    grouping_attributes: list[str],
) -> list[tuple[str, pd.DataFrame]]:
    """Partition ``frame`` by each distinct combination of grouping values.

    Implements the two-step partition (Requirements 3.8, 3.9): rows are grouped by
    the tuple of ``grouping_attributes`` values, dropping rows with a null in any
    grouping attribute (a null combination is not a usable group). Groups are
    returned in ascending group-key order so iteration is deterministic.

    Returns:
        A list of ``(group_key, group_frame)`` pairs ordered by ascending key.
    """
    present = frame.dropna(subset=grouping_attributes)
    groups: list[tuple[str, pd.DataFrame]] = []
    # groupby with sort=True yields groups in ascending key order (deterministic).
    grouped = present.groupby(grouping_attributes, sort=True, dropna=True)
    for key, group_frame in grouped:
        values = key if isinstance(key, tuple) else (key,)
        groups.append((_combination_key(values), group_frame.reset_index(drop=True)))
    return groups


def _select_campaign_pool(
    frame: pd.DataFrame,
    campaign_pool_ids: Iterable[str] | None,
) -> pd.DataFrame:
    """Restrict ``frame`` to the campaign pool, excluding out-of-pool leads.

    ``campaign_pool_ids`` is the set of ``client_id`` values that make up the pool
    (the live session leads or a past promo's leads, resolved by the caller). Only
    rows whose ``client_id`` is in that set are kept; every other lead is excluded
    (Requirements 5.4). When ``campaign_pool_ids`` is ``None`` the whole frame is
    treated as the pool (the caller has already scoped it).
    """
    if campaign_pool_ids is None:
        return frame.reset_index(drop=True)
    pool = set(campaign_pool_ids)
    kept = frame[frame[CLIENT_ID_COLUMN].isin(pool)]
    return kept.reset_index(drop=True)


def build_persona_sets(
    frame: pd.DataFrame,
    *,
    level: str = LEVEL_ALL,
    clustering_attributes: list[str],
    grouping_attributes: list[str] | None = None,
    k: int | None = None,
    business_segment_field: str | None = None,
    campaign_pool_ids: Iterable[str] | None = None,
    namer: PersonaNamer | None = None,
    cfg: Config | None = None,
    type_overrides: dict[str, str] | None = None,
) -> list[PersonaSet]:
    """Build the :class:`PersonaSet` list for one persona run (Requirements 3, 5).

    This is the module's pure, deterministic public entry point, convenient for
    both ``export.py`` (task 10.1) and ``webapp_core/personas.py`` (task 13.1):
    give it the Joined_Attribute_Set ``frame``, the level, and the clustering /
    grouping attributes, and it returns one :class:`PersonaSet` per group in a
    deterministic (ascending group-key) order.

    Level behaviour (Requirement 3.4):

    - ``all``: one :class:`PersonaSet` over the whole frame with ``group_key == ""``.
    - ``business-segment``: partition by the distinct non-null values of
      ``business_segment_field`` (which must be a column on ``frame``) and produce
      one :class:`PersonaSet` per value, ``group_key`` set to that value
      (Requirement 3.6). If the field has no non-null values, a :class:`ValueError`
      naming the field is raised (Requirement 3.7). The field itself is excluded
      from the clustering attributes if present.
    - ``campaign``: restrict to ``campaign_pool_ids`` (excluding out-of-pool leads),
      never use any ``business_segment_field`` as a clustering feature
      (Requirements 5.4, 5.5), and raise :class:`EmptyAudienceError` without
      clustering when the pool is empty (Requirement 5.6).

    Two-step flow (Requirements 3.8, 3.9): when ``grouping_attributes`` are
    provided they take precedence over the level's implicit partition -- the frame
    is partitioned by each distinct combination of grouping-attribute values and
    each group is clustered on ``clustering_attributes``. (At ``business-segment``
    level the field acts as the single grouping attribute.)

    Per group the size rules apply (Requirements 3.10, 3.11): a group below
    ``cfg.min_group_size`` is flagged ``too_small=True`` with no personas and is not
    clustered; otherwise k is capped to the group size and the group is clustered.

    Args:
        frame: The Joined_Attribute_Set -- one row per lead, carrying ``client_id``,
            the ``clustering_attributes``, and (for business-segment) the
            ``business_segment_field`` column.
        level: One of :data:`LEVEL_ALL`, :data:`LEVEL_BUSINESS_SEGMENT`,
            :data:`LEVEL_CAMPAIGN` (Requirement 3.4).
        clustering_attributes: The >=1 columns to cluster each group on
            (Requirements 3.2, 3.3). Keyword-only.
        grouping_attributes: Optional two-step grouping columns; ``None``/empty means
            no explicit two-step partition (Requirement 3.8).
        k: The requested cluster count (``None`` -> ``cfg.default_k``); capped per
            group (Requirements 2.8, 3.11).
        business_segment_field: The column name used to partition at
            ``business-segment`` level (Requirement 3.5); required at that level.
        campaign_pool_ids: The ``client_id`` values making up the campaign pool at
            ``campaign`` level (Requirements 5.1, 5.4).
        namer: The :class:`~part5_personas.naming.PersonaNamer` to name personas;
            defaults to a fresh :class:`~part5_personas.naming.RuleBasedNamer`.
        cfg: The Persona_Pipeline :class:`~part5_personas.config.Config`; defaults to
            ``Config()``.
        type_overrides: Optional per-attribute type override passed through to
            preprocessing/profiling (Requirement 2.3).

    Returns:
        A list of :class:`PersonaSet`, one per group, in ascending group-key order
        (a single set with ``group_key == ""`` at level ``all``).

    Raises:
        ValueError: If ``clustering_attributes`` is empty, if ``level`` is unknown,
            if ``business-segment`` level is missing its field or the field has no
            non-null values (Requirement 3.7).
        EmptyAudienceError: If ``campaign`` level has an empty pool (Requirement 5.6).
    """
    cfg = cfg or Config()
    namer = namer or RuleBasedNamer()
    grouping_attributes = list(grouping_attributes or [])
    type_overrides = type_overrides or {}

    if not clustering_attributes:
        raise ValueError(
            "clustering_attributes must contain at least one column "
            "(Requirement 3.3)"
        )

    clustering_attributes = list(clustering_attributes)

    if level == LEVEL_ALL:
        return _build_level_all(
            frame,
            clustering_attributes,
            grouping_attributes,
            k,
            namer,
            cfg,
            type_overrides,
        )

    if level == LEVEL_BUSINESS_SEGMENT:
        return _build_level_business_segment(
            frame,
            clustering_attributes,
            business_segment_field,
            k,
            namer,
            cfg,
            type_overrides,
        )

    if level == LEVEL_CAMPAIGN:
        return _build_level_campaign(
            frame,
            clustering_attributes,
            grouping_attributes,
            business_segment_field,
            campaign_pool_ids,
            k,
            namer,
            cfg,
            type_overrides,
        )

    raise ValueError(
        f"unknown clustering level {level!r}; expected one of "
        f"{LEVEL_ALL!r}, {LEVEL_BUSINESS_SEGMENT!r}, {LEVEL_CAMPAIGN!r} "
        f"(Requirement 3.4)"
    )


def _build_level_all(
    frame: pd.DataFrame,
    clustering_attributes: list[str],
    grouping_attributes: list[str],
    k: int | None,
    namer: PersonaNamer,
    cfg: Config,
    type_overrides: dict[str, str] | None,
) -> list[PersonaSet]:
    """Level ``all``: one set over the whole frame, or the two-step partition.

    With no ``grouping_attributes`` this produces a single :class:`PersonaSet` with
    ``group_key == ""`` over the whole lead list (Requirement 3.4). With
    ``grouping_attributes`` it partitions by their distinct combinations first, then
    clusters each group (Requirements 3.8, 3.9), one set per combination keyed by the
    combination's values.
    """
    if grouping_attributes:
        return _build_two_step(
            frame,
            clustering_attributes,
            grouping_attributes,
            k,
            namer,
            cfg,
            type_overrides,
        )

    whole = frame.reset_index(drop=True)
    return [
        _persona_set_for_group(
            "",
            whole,
            clustering_attributes,
            k,
            namer,
            cfg,
            type_overrides,
        )
    ]


def _build_level_business_segment(
    frame: pd.DataFrame,
    clustering_attributes: list[str],
    business_segment_field: str | None,
    k: int | None,
    namer: PersonaNamer,
    cfg: Config,
    type_overrides: dict[str, str] | None,
) -> list[PersonaSet]:
    """Level ``business-segment``: one set per distinct non-null field value.

    The ``business_segment_field`` must be a column on ``frame`` (Requirement 3.5).
    If it has no non-null values across the audience, a :class:`ValueError` naming
    the field is raised and nothing is clustered (Requirement 3.7). Otherwise the
    frame is partitioned by the field (acting as the single grouping attribute) and
    one :class:`PersonaSet` per distinct value is produced, ``group_key`` set to the
    value (Requirement 3.6). The field is excluded from the clustering attributes so
    it is never also a clustering feature within its own partition.
    """
    if not business_segment_field:
        raise InvalidSegmentFieldError(_segment_field_message(None))
    if business_segment_field not in frame.columns:
        raise InvalidSegmentFieldError(_segment_field_message(business_segment_field))

    # Reject a field with no usable (non-null) values (Requirement 3.7).
    if frame[business_segment_field].notna().sum() == 0:
        raise ValueError(
            f"business_segment_field {business_segment_field!r} has no non-null "
            f"values; cannot segment the audience by it (Requirement 3.7)"
        )

    # The field partitions the audience but must not be a clustering feature too.
    clustering = [c for c in clustering_attributes if c != business_segment_field]
    if not clustering:
        raise ValueError(
            "clustering_attributes must contain at least one column other than "
            f"the business_segment_field {business_segment_field!r} "
            "(Requirement 3.3)"
        )

    return _build_two_step(
        frame,
        clustering,
        [business_segment_field],
        k,
        namer,
        cfg,
        type_overrides,
    )


def _build_level_campaign(
    frame: pd.DataFrame,
    clustering_attributes: list[str],
    grouping_attributes: list[str],
    business_segment_field: str | None,
    campaign_pool_ids: Iterable[str] | None,
    k: int | None,
    namer: PersonaNamer,
    cfg: Config,
    type_overrides: dict[str, str] | None,
) -> list[PersonaSet]:
    """Level ``campaign``: cluster only the pool, never on the segment field.

    Restricts ``frame`` to the campaign pool, excluding every out-of-pool lead
    (Requirement 5.4). If the pool is empty, :class:`EmptyAudienceError` is raised
    *without* clustering so the caller surfaces an empty-audience message
    (Requirement 5.6). No ``business_segment_field`` is ever used as a clustering
    feature at this level (Requirement 5.5): it is dropped from both the clustering
    and the two-step grouping attributes. With remaining ``grouping_attributes`` the
    pool is clustered via the two-step partition; otherwise it is one set keyed by
    the pool identifier (``""`` when unnamed).
    """
    pool = _select_campaign_pool(frame, campaign_pool_ids)

    # Empty pool -> empty audience, reported WITHOUT clustering (Requirement 5.6).
    if len(pool) == 0:
        raise EmptyAudienceError(
            "campaign pool is empty; no leads to cluster (Requirement 5.6)"
        )

    # No Business_Segment_Field is used as a clustering input (Requirement 5.5).
    clustering = [c for c in clustering_attributes if c != business_segment_field]
    grouping = [g for g in grouping_attributes if g != business_segment_field]
    if not clustering:
        raise ValueError(
            "clustering_attributes must contain at least one column that is not "
            "the business_segment_field at campaign level (Requirements 3.3, 5.5)"
        )

    if grouping:
        return _build_two_step(
            pool,
            clustering,
            grouping,
            k,
            namer,
            cfg,
            type_overrides,
        )

    return [
        _persona_set_for_group(
            "",
            pool,
            clustering,
            k,
            namer,
            cfg,
            type_overrides,
        )
    ]


def _build_two_step(
    frame: pd.DataFrame,
    clustering_attributes: list[str],
    grouping_attributes: list[str],
    k: int | None,
    namer: PersonaNamer,
    cfg: Config,
    type_overrides: dict[str, str] | None,
) -> list[PersonaSet]:
    """Partition by ``grouping_attributes`` then cluster each group (Req 3.8, 3.9).

    Partitions deterministically by each distinct combination of grouping-attribute
    values (ascending group-key order) and builds one :class:`PersonaSet` per group,
    applying the per-group size rules (Requirements 3.10, 3.11) via
    :func:`_persona_set_for_group`.
    """
    sets: list[PersonaSet] = []
    for group_key, group_frame in _partition_by_attributes(frame, grouping_attributes):
        sets.append(
            _persona_set_for_group(
                group_key,
                group_frame,
                clustering_attributes,
                k,
                namer,
                cfg,
                type_overrides,
            )
        )
    return sets
