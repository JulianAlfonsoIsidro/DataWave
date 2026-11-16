"""Shared Hypothesis strategies for the Part 5 Persona_Pipeline property tests.

This module centralizes the reusable generators the persona-segmentation
property tests (Properties 1-12, tasks 5.x-13.x) draw from, following the
``tests/strategies_part5.py`` / ``tests/strategies.py`` convention of one
``@st.composite`` per coherent shape with a clear docstring citing the
requirement it supports. Existing persona property tests keep their own
focused inline generators; these shared composites give new (and refactored)
tests a single, general input space to build on.

Three shapes are produced here, matching the three data models the persona
pipeline threads through its stages:

- :func:`joined_attribute_sets` -- a :class:`~part5_personas.join` style
  Joined_Attribute_Set: one row per unique ``client_id`` with a configurable mix
  of numeric, categorical, and ``owns_*`` ownership-flag columns, shaped exactly
  like the frame ``build_joined_attributes`` returns and
  :func:`part5_personas.grouping.build_persona_sets` clusters on
  (Requirements 2.1, 4.1).
- :func:`run_specs` / :func:`run_spec_kwargs` -- a valid
  :class:`~webapp_core.personas.PersonaRunSpec` (or its kwargs) that is coherent
  with a given joined frame: a level from the valid set, a non-empty subset of the
  frame's columns as ``clustering_attributes``, a ``k`` in ``[k_min, k_max]``, and
  optional ``grouping_attributes`` (Requirement 2.1).
- :func:`persona_labels` / :func:`lead_pools` -- the per-lead label frame
  (``client_id``, ``persona_label``, and optional ``promo_id`` + ``segment_slug``
  cell keys) the mix/export tests consume, and a Part 4 leads pool
  (``client_id``, ``best_channel``, ``p_join``, ``control``), both with one row
  per lead and no duplicate ``client_id`` (Requirement 8.1). The campaign
  empty-persona-label case is reachable.

Import from a test module with an absolute import mirroring the ``src`` package
style, relying on ``tests/conftest.py`` for ``src`` on ``sys.path`` (never
hardcode it)::

    from tests.strategies_part5_personas import joined_attribute_sets, run_specs

    @given(joined_attribute_sets())
    def test_something(joined):
        ...

Design notes:
- These generators are kept general and composable (small helper strategies +
  composites), not a copy of any one test's inline generator.
- Numeric values are finite and bounded well inside the float range so the
  downstream standardize (``preprocess.scale_numeric``) and k-prototypes fit stay
  numerically stable; categorical domains are small so both the in- and
  out-of-category paths stay reachable; ownership flags are integer ``{0, 1}``
  exactly as :func:`part5_personas.join.pivot_product_ownership` produces.
- ``client_id`` values are zero-padded strings (``C0001``) so their natural sort
  matches a stable, obvious order, mirroring the other strategy modules.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import strategies as st

from part5_personas.config import CAMPAIGN_PROMO_IDS, Config
from part5_personas.export import PART4_LEAD_COLUMNS
from part5_personas.grouping import (
    LEVEL_ALL,
    LEVEL_BUSINESS_SEGMENT,
    LEVEL_CAMPAIGN,
)
from webapp_core.personas import PersonaRunSpec

# --------------------------------------------------------------------------- #
# Shared vocabularies and bounds                                              #
# --------------------------------------------------------------------------- #

# The three clustering levels (Requirement 3.4), reused as the run-spec level pool.
LEVELS: list[str] = [LEVEL_ALL, LEVEL_BUSINESS_SEGMENT, LEVEL_CAMPAIGN]

# The Customer_DNA ``segment`` domain, usable as a Business_Segment_Field value.
# A small pool keeps every business-segment group reachable with few rows.
DNA_SEGMENTS: list[str] = [
    "Affluent-Preferred",
    "Mass-Affluent",
    "Mass-Market",
    "Emerging",
]

# A small generic categorical domain for the non-segment categorical columns.
CATEGORY_VALUES: list[str] = ["A", "B", "C", "D"]

# The four Part 3 Segment_Labels, slugged to match the per-cell leads cell keys
# (see ``webapp_core.personas.segment_slug``).
SEGMENT_SLUGS: list[str] = [
    "ready_toppers",
    "willing_but_stretched",
    "untapped_wealth",
    "not_now",
]

# The Part 4 best_channel domain (exact labels; a mismatch makes a lead
# unreachable per the product rules).
CHANNELS: list[str] = ["In-app", "Email", "SMS"]

# A persona-name vocabulary for synthetic label frames.
PERSONA_NAMES: list[str] = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]

# Numeric bounds: finite and well inside the float range so standardize + the
# k-prototypes fit stay stable and sums keep good precision.
_MIN_NUMERIC = -1_000_000.0
_MAX_NUMERIC = 1_000_000.0

# The persona-label value used for an out-of-pool / unassigned campaign lead.
EMPTY_PERSONA_LABEL = ""


def _client_ids(n: int) -> list[str]:
    """Return ``n`` unique, stably sorted, zero-padded ``client_id`` strings."""
    return [f"C{i:04d}" for i in range(1, n + 1)]


def _numeric() -> st.SearchStrategy[float]:
    """Finite numeric values bounded to keep scaling / clustering stable."""
    return st.floats(
        min_value=_MIN_NUMERIC,
        max_value=_MAX_NUMERIC,
        allow_nan=False,
        allow_infinity=False,
    )


def _p_join() -> st.SearchStrategy[float]:
    """Join probabilities in the closed unit interval ``[0, 1]``."""
    return st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    )


# --------------------------------------------------------------------------- #
# 1. Joined_Attribute_Set generator (Requirements 2.1, 4.1)                   #
# --------------------------------------------------------------------------- #
@st.composite
def joined_attribute_sets(
    draw: st.DrawFn,
    *,
    min_rows: int = 1,
    max_rows: int = 60,
    n_numeric: int | None = None,
    n_categorical: int | None = None,
    n_ownership: int | None = None,
    min_numeric: int = 1,
    max_numeric: int = 3,
    min_categorical: int = 0,
    max_categorical: int = 2,
    min_ownership: int = 1,
    max_ownership: int = 3,
    with_segment: bool = True,
) -> pd.DataFrame:
    """Composite strategy producing a Joined_Attribute_Set frame (Req 2.1, 4.1).

    The frame mirrors what :func:`part5_personas.join.build_joined_attributes`
    yields -- one row per unique ``client_id`` with a configurable mix of
    columns that :func:`part5_personas.grouping.build_persona_sets` can cluster
    on:

    - ``client_id`` -- unique, stably sorted, zero-padded strings (no duplicate
      ids; exactly one row per id).
    - ``segment`` -- a Customer_DNA segment value drawn from
      :data:`DNA_SEGMENTS` (present when ``with_segment``), usable as a
      Business_Segment_Field.
    - ``num{i}`` -- ``n_numeric`` finite numeric columns (floats bounded to keep
      standardize / k-prototypes stable).
    - ``cat{i}`` -- ``n_categorical`` categorical columns over the small
      :data:`CATEGORY_VALUES` domain.
    - ``owns_{i}`` -- ``n_ownership`` integer ``{0, 1}`` ownership-flag columns,
      exactly as :func:`part5_personas.join.pivot_product_ownership` produces and
      treated downstream as categorical (Requirement 1.3).

    Args:
        min_rows / max_rows: bounds on the lead (row) count; at least one row.
        n_numeric / n_categorical / n_ownership: exact column counts when given,
            otherwise each is drawn from its ``min_*``/``max_*`` range.
        min_numeric / max_numeric: numeric-column-count range when ``n_numeric``
            is ``None`` (at least one numeric column by default so a run always has
            a scalable feature).
        min_categorical / max_categorical: categorical-column-count range when
            ``n_categorical`` is ``None``.
        min_ownership / max_ownership: ownership-flag-count range when
            ``n_ownership`` is ``None``.
        with_segment: include the ``segment`` Business_Segment_Field column.

    Returns:
        A pandas ``DataFrame`` with the columns described above, one row per
        unique ``client_id``, values finite and within sane ranges.
    """
    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    client_ids = _client_ids(n)

    num_count = (
        n_numeric
        if n_numeric is not None
        else draw(st.integers(min_value=min_numeric, max_value=max_numeric))
    )
    cat_count = (
        n_categorical
        if n_categorical is not None
        else draw(st.integers(min_value=min_categorical, max_value=max_categorical))
    )
    own_count = (
        n_ownership
        if n_ownership is not None
        else draw(st.integers(min_value=min_ownership, max_value=max_ownership))
    )

    data: dict[str, list] = {"client_id": client_ids}

    if with_segment:
        data["segment"] = [draw(st.sampled_from(DNA_SEGMENTS)) for _ in range(n)]

    for i in range(num_count):
        data[f"num{i}"] = [draw(_numeric()) for _ in range(n)]

    for i in range(cat_count):
        data[f"cat{i}"] = [draw(st.sampled_from(CATEGORY_VALUES)) for _ in range(n)]

    for i in range(own_count):
        data[f"owns_{i}"] = [draw(st.sampled_from([0, 1])) for _ in range(n)]

    frame = pd.DataFrame(data)

    # dtype coercion matching the join stage's output: string ids/categoricals as
    # object, numeric floats as float64, ownership flags as integer {0, 1}.
    frame["client_id"] = frame["client_id"].astype("object")
    if with_segment:
        frame["segment"] = frame["segment"].astype("object")
    for i in range(num_count):
        frame[f"num{i}"] = pd.to_numeric(frame[f"num{i}"], errors="raise")
    for i in range(cat_count):
        frame[f"cat{i}"] = frame[f"cat{i}"].astype("object")
    for i in range(own_count):
        frame[f"owns_{i}"] = frame[f"owns_{i}"].astype(int)

    return frame.reset_index(drop=True)


def clustering_attribute_columns(frame: pd.DataFrame) -> list[str]:
    """Return the frame columns usable as clustering/grouping attributes.

    Every column except ``client_id`` is a candidate clustering attribute for a
    persona run; this helper keeps the run-spec generator and callers in agreement
    on that set.
    """
    return [col for col in frame.columns if col != "client_id"]


# --------------------------------------------------------------------------- #
# 2. Run-spec generator (Requirement 2.1)                                     #
# --------------------------------------------------------------------------- #
@st.composite
def run_spec_kwargs(
    draw: st.DrawFn,
    frame: pd.DataFrame,
    *,
    levels: list[str] | None = None,
    allow_grouping: bool = True,
    cfg: Config | None = None,
) -> dict:
    """Draw coherent :class:`PersonaRunSpec` kwargs for a given joined ``frame``.

    The kwargs are made consistent with ``frame`` so a run built from them is
    valid: ``clustering_attributes`` is a non-empty subset of the frame's
    clustering-candidate columns (Requirements 3.2, 3.3), ``k`` is an integer in
    ``[cfg.k_min, cfg.k_max]`` (Requirements 2.9, 2.10), and the level is drawn
    from the valid set (Requirement 3.4). For ``business-segment`` level a
    ``business_segment_field`` present on the frame is chosen (preferring
    ``segment``) and excluded from ``clustering_attributes``; for ``campaign``
    level a ``campaign_pool`` (``"live"`` or a promo id from
    :data:`CAMPAIGN_PROMO_IDS`) is set. Optional ``grouping_attributes`` draw a
    (possibly empty) subset of the remaining columns when ``allow_grouping``.

    Args:
        frame: The Joined_Attribute_Set the spec must be coherent with.
        levels: The level pool to draw from; defaults to all of :data:`LEVELS`.
        allow_grouping: whether to (sometimes) draw ``grouping_attributes``.
        cfg: supplies the ``k`` bounds; defaults to ``Config()``.

    Returns:
        A ``dict`` of keyword arguments accepted by :class:`PersonaRunSpec`.
    """
    cfg = cfg or Config()
    candidates = clustering_attribute_columns(frame)
    # A joined frame always has at least one numeric column by default, so the
    # candidate set is non-empty; guard anyway for callers that override columns.
    if not candidates:
        raise ValueError(
            "frame must carry at least one non-client_id column to draw a run spec"
        )

    level = draw(st.sampled_from(levels if levels is not None else LEVELS))

    # business_segment_field only matters at business-segment level; pick a field
    # the frame actually carries (prefer the Customer_DNA ``segment``).
    segment_fields = [c for c in ("segment",) if c in frame.columns]
    business_segment_field: str | None = None
    if level == LEVEL_BUSINESS_SEGMENT and segment_fields:
        business_segment_field = draw(st.sampled_from(segment_fields))

    # The clustering attributes: a non-empty subset, excluding the segment field
    # when it acts as the partition (the pipeline excludes it anyway).
    selectable = [c for c in candidates if c != business_segment_field]
    if not selectable:
        selectable = candidates
    clustering_attributes = draw(
        st.lists(
            st.sampled_from(selectable),
            min_size=1,
            max_size=len(selectable),
            unique=True,
        )
    )

    # Optional two-step grouping: a (possibly empty) subset of the leftover
    # columns, never overlapping the clustering attributes.
    grouping_attributes: list[str] = []
    leftover = [
        c
        for c in candidates
        if c not in clustering_attributes and c != business_segment_field
    ]
    if allow_grouping and leftover and draw(st.booleans()):
        grouping_attributes = draw(
            st.lists(
                st.sampled_from(leftover),
                min_size=1,
                max_size=len(leftover),
                unique=True,
            )
        )

    k = draw(st.integers(min_value=cfg.k_min, max_value=cfg.k_max))

    campaign_pool: str | None = None
    if level == LEVEL_CAMPAIGN:
        campaign_pool = draw(
            st.sampled_from(["live", *CAMPAIGN_PROMO_IDS])
        )

    return {
        "level": level,
        "clustering_attributes": clustering_attributes,
        "grouping_attributes": grouping_attributes,
        "k": k,
        "business_segment_field": business_segment_field,
        "campaign_pool": campaign_pool,
        "type_overrides": {},
    }


@st.composite
def run_specs(
    draw: st.DrawFn,
    frame: pd.DataFrame,
    *,
    levels: list[str] | None = None,
    allow_grouping: bool = True,
    cfg: Config | None = None,
) -> PersonaRunSpec:
    """Draw a valid :class:`PersonaRunSpec` coherent with ``frame`` (Req 2.1).

    Thin wrapper over :func:`run_spec_kwargs` that constructs the frozen
    :class:`~webapp_core.personas.PersonaRunSpec` dataclass. See
    :func:`run_spec_kwargs` for the coherence guarantees.
    """
    kwargs = draw(
        run_spec_kwargs(
            frame, levels=levels, allow_grouping=allow_grouping, cfg=cfg
        )
    )
    return PersonaRunSpec(**kwargs)


@st.composite
def joined_with_spec(
    draw: st.DrawFn,
    *,
    levels: list[str] | None = None,
    allow_grouping: bool = True,
    cfg: Config | None = None,
    **joined_kwargs,
) -> tuple[pd.DataFrame, PersonaRunSpec]:
    """Draw a ``(joined, spec)`` pair where the spec is coherent with the frame.

    Convenience composite for tests that need a Joined_Attribute_Set together with
    a valid run spec over it. ``joined_kwargs`` are forwarded to
    :func:`joined_attribute_sets`.
    """
    joined = draw(joined_attribute_sets(**joined_kwargs))
    spec = draw(
        run_specs(joined, levels=levels, allow_grouping=allow_grouping, cfg=cfg)
    )
    return joined, spec


# --------------------------------------------------------------------------- #
# 3. Lead-pool / labels generators (Requirement 8.1)                          #
# --------------------------------------------------------------------------- #
@st.composite
def lead_pools(
    draw: st.DrawFn,
    *,
    min_leads: int = 1,
    max_leads: int = 60,
    with_promo_id: bool = False,
) -> pd.DataFrame:
    """Draw a Part 4 leads pool: one row per lead, no duplicate ids (Req 8.1).

    The frame carries exactly the Part 4 lead columns
    (:data:`~part5_personas.export.PART4_LEAD_COLUMNS` -- ``client_id``,
    ``best_channel``, ``p_join``, ``control``) with unique ``client_id`` values,
    ``best_channel`` drawn from the exact :data:`CHANNELS` labels, ``p_join`` in
    ``[0, 1]``, and ``control`` a ``0``/``1`` flag. When ``with_promo_id`` is set
    an extra ``promo_id`` column is added (from :data:`CAMPAIGN_PROMO_IDS`) so the
    export's column-dropping path is exercisable.

    Returns:
        A pandas ``DataFrame`` with one row per lead and a unique ``client_id``.
    """
    n = draw(st.integers(min_value=min_leads, max_value=max_leads))
    client_ids = _client_ids(n)

    data: dict[str, list] = {
        "client_id": client_ids,
        "best_channel": [draw(st.sampled_from(CHANNELS)) for _ in range(n)],
        "p_join": [draw(_p_join()) for _ in range(n)],
        "control": [draw(st.sampled_from([0, 1])) for _ in range(n)],
    }
    if with_promo_id:
        data["promo_id"] = [draw(st.sampled_from(list(CAMPAIGN_PROMO_IDS))) for _ in range(n)]

    frame = pd.DataFrame(data, columns=[*PART4_LEAD_COLUMNS, *(["promo_id"] if with_promo_id else [])])
    frame["client_id"] = frame["client_id"].astype("object")
    frame["best_channel"] = frame["best_channel"].astype("object")
    frame["p_join"] = pd.to_numeric(frame["p_join"], errors="raise")
    frame["control"] = pd.to_numeric(frame["control"], errors="raise")
    if with_promo_id:
        frame["promo_id"] = frame["promo_id"].astype("object")

    return frame.reset_index(drop=True)


@st.composite
def persona_labels(
    draw: st.DrawFn,
    *,
    min_leads: int = 0,
    max_leads: int = 60,
    with_cells: bool = True,
    allow_empty_label: bool = True,
) -> pd.DataFrame:
    """Draw a per-lead persona-label frame (Requirement 8.1).

    Shaped like the ``labels`` frame :func:`webapp_core.personas.run_personas`
    produces and :func:`webapp_core.personas.persona_mix_by_cell` /
    :func:`part5_personas.export.build_persona_labeled_leads` consume: one row per
    lead with a unique ``client_id`` and a ``persona_label`` drawn from
    :data:`PERSONA_NAMES`. When ``with_cells`` the ``promo_id`` and
    ``segment_slug`` decision-card cell keys are attached (drawn from
    :data:`CAMPAIGN_PROMO_IDS` and :data:`SEGMENT_SLUGS`) so the per-cell mix can
    be scoped. When ``allow_empty_label`` some leads carry an empty
    ``persona_label`` (:data:`EMPTY_PERSONA_LABEL`) -- the out-of-pool campaign
    case (Requirement 8.7) -- which must not contribute to any cell's mix.

    The empty-frame case (``min_leads == 0``) is reachable so the all-empty /
    no-assignment paths are exercised.

    Returns:
        A pandas ``DataFrame`` with columns ``client_id``, ``persona_label`` and,
        when ``with_cells``, ``promo_id`` and ``segment_slug`` -- one row per lead,
        no duplicate ``client_id``.
    """
    n = draw(st.integers(min_value=min_leads, max_value=max_leads))
    client_ids = _client_ids(n)

    label_strategy: st.SearchStrategy[str] = (
        st.one_of(st.sampled_from(PERSONA_NAMES), st.just(EMPTY_PERSONA_LABEL))
        if allow_empty_label
        else st.sampled_from(PERSONA_NAMES)
    )

    data: dict[str, list] = {
        "client_id": client_ids,
        "persona_label": [draw(label_strategy) for _ in range(n)],
    }
    columns = ["client_id", "persona_label"]
    if with_cells:
        data["promo_id"] = [draw(st.sampled_from(list(CAMPAIGN_PROMO_IDS))) for _ in range(n)]
        data["segment_slug"] = [draw(st.sampled_from(SEGMENT_SLUGS)) for _ in range(n)]
        columns.extend(["promo_id", "segment_slug"])

    if n == 0:
        frame = pd.DataFrame({col: pd.Series(dtype="object") for col in columns})
    else:
        frame = pd.DataFrame(data, columns=columns)
        for col in columns:
            frame[col] = frame[col].astype("object")

    return frame.reset_index(drop=True)


@st.composite
def labels_and_cards(
    draw: st.DrawFn,
    *,
    min_leads: int = 0,
    max_leads: int = 40,
) -> tuple[pd.DataFrame, list[dict]]:
    """Draw a coherent ``(labels, cards)`` pair for the per-cell mix (Req 8.1, 7.1).

    Builds a per-lead :func:`persona_labels` frame (with cell keys) and one Part 4
    card dict per ``(promo_id, segment_slug)`` cell that the labels populate. Each
    card's ``segment`` is set to the cell's slug itself, so
    :func:`webapp_core.personas.segment_slug` (idempotent on a slug) keys the card
    to the same cell the labels carry. The empty-label (out-of-pool) and empty-cell
    cases are reachable, so both the ``available=True`` and ``available=False``
    branches of :func:`webapp_core.personas.persona_mix_by_cell` are exercised.

    Returns:
        A ``(labels, cards)`` tuple -- ``labels`` a per-lead frame, ``cards`` one
        card per distinct cell present in ``labels``.
    """
    labels = draw(
        persona_labels(
            min_leads=min_leads,
            max_leads=max_leads,
            with_cells=True,
            allow_empty_label=True,
        )
    )

    cards: list[dict] = []
    if not labels.empty:
        cells = (
            labels[["promo_id", "segment_slug"]]
            .drop_duplicates()
            .itertuples(index=False)
        )
        for promo_id, slug in cells:
            cards.append({"promo_id": str(promo_id), "segment": str(slug)})

    return labels, cards
