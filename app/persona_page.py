"""CRM-friendly Persona_Page composition and session wiring (Requirements 3, 4.5, 4.10, 5, 6, 8.8-8.10).

The Streamlit ``Persona_Page`` for the Promo Audience Navigator. It is the
presentation-and-session-state layer only: it wires widgets, owns the
``st.cache_data`` caches, and delegates **all** clustering/profiling to
:mod:`webapp_core.personas` (Persona_Core) / :mod:`part5_personas`
(Persona_Pipeline). It holds no modelling and -- per the project's layering rule
-- keeps business logic out of ``app/`` by calling the pure backend for anything
beyond presentation (Requirement 6.9).

This module is written for a CRM manager or campaign planner, not a data
scientist (requirements Introduction): controls carry plain business labels,
attributes are grouped and renamed into business terms, and validation /
"too small to cluster" messages read as actionable instructions.

Scope note (task 14.1): this builds the **page composition + session-state
wiring** only -- the Clustering_Level / k / Run controls, the grouped
Attribute_Picker, the optional two-step control, the campaign-pool selector,
validation, the per-persona summary cards, and the two download controls. The
cluster bar chart, the elbow expander, and the persona-mix badges on decision
cards are task 14.2 and are intentionally **not** rendered here.

Pure helpers (importable without a running Streamlit server, unit-tested in task
14.3) live at module level:

- :func:`level_label_to_value` / :func:`level_value_to_label` -- the plain-label
  <-> internal-value mapping for the Clustering_Level selector (Requirement 3.4).
- :func:`attribute_group_and_label` -- the raw-column -> ``(Attribute_Group,
  Attribute_Display_Label)`` mapping with a graceful title-cased fallback for
  unmapped columns (Requirement 3.1), and :data:`DEFAULT_ATTRIBUTE_SET`
  (Requirement 3.13).
- :func:`group_attributes_by_theme` -- bucket a column list under the four
  Attribute_Group headings in display order.
- :func:`distinguishing_sentences` -- render a persona's distinguishing
  attributes as plain business sentences over :class:`PersonaProfile` values
  (Requirement 4.10).
- :func:`validation_error` -- the actionable validation message for an invalid
  configuration (Requirement 6.2).
- :func:`too_small_message` -- the actionable "too small to cluster" instruction
  stating the group's lead count (Requirement 6.10).
- :func:`promo_pool_label` -- the "promo_id -- name/date" label for the campaign
  pool selector, selecting by ``promo_id`` (Requirements 3.15, 5.3).
- :func:`campaign_leads_export_frame` -- the default Campaign_Leads_Export column
  projection (Requirement 8.8), delegating to
  :func:`part5_personas.export.campaign_leads_export`.

``streamlit`` is imported lazily inside the render functions so importing
``app.persona_page`` never requires a running Streamlit server (task 14.1
verification bar / task 14.3 testability).
"""

from __future__ import annotations

import html
from dataclasses import dataclass

import pandas as pd

from part5_personas.config import CAMPAIGN_PROMO_IDS
from part5_personas.export import (
    CAMPAIGN_LEADS_EXPORT_COLUMNS,
    GROUP_COLUMN,
    PERSONA_LABEL_COLUMN,
    campaign_leads_export,
)
from part5_personas.grouping import (
    LEVEL_ALL,
    LEVEL_BUSINESS_SEGMENT,
    LEVEL_CAMPAIGN,
    PersonaSet,
)
from part5_personas.profile import PersonaProfile
from webapp_core.personas import PersonaRunResult, PersonaRunSpec, run_personas

# --------------------------------------------------------------------------- #
# Clustering_Level: plain label <-> internal value mapping (Requirement 3.4)  #
# --------------------------------------------------------------------------- #
# The internal values handed to ``run_personas`` are unchanged; only the labels
# shown in the selector are the CRM-friendly plain phrasing. "All leads" is the
# default (maps to ``all``, Requirement 3.4).
LEVEL_LABELS: dict[str, str] = {
    LEVEL_ALL: "All leads",
    LEVEL_BUSINESS_SEGMENT: "By customer segment",
    LEVEL_CAMPAIGN: "By campaign",
}
# The display order of the level selector, default first.
LEVEL_LABEL_ORDER: list[str] = [
    LEVEL_LABELS[LEVEL_ALL],
    LEVEL_LABELS[LEVEL_BUSINESS_SEGMENT],
    LEVEL_LABELS[LEVEL_CAMPAIGN],
]
_LABEL_TO_LEVEL: dict[str, str] = {label: value for value, label in LEVEL_LABELS.items()}


def level_value_to_label(level: str) -> str:
    """Return the plain Clustering_Level label for an internal value (Req 3.4).

    Maps ``all`` -> "All leads", ``business-segment`` -> "By customer segment",
    ``campaign`` -> "By campaign". An unknown value falls back to its own string
    so the selector degrades gracefully rather than raising.
    """
    return LEVEL_LABELS.get(level, str(level))


def level_label_to_value(label: str) -> str:
    """Return the internal Clustering_Level value for a plain label (Req 3.4).

    The inverse of :func:`level_value_to_label`. An unrecognised label falls back
    to :data:`part5_personas.grouping.LEVEL_ALL` so a missing/renamed label still
    resolves to the default level (Requirement 3.4).
    """
    return _LABEL_TO_LEVEL.get(label, LEVEL_ALL)


# --------------------------------------------------------------------------- #
# Attribute_Picker: Attribute_Group headings + raw-column -> (group, label)   #
# mapping + Default_Attribute_Set (Requirements 3.1, 3.13)                     #
# --------------------------------------------------------------------------- #
# The four business-friendly Attribute_Group headings, in display order
# (Requirement 3.1).
GROUP_DEMOGRAPHICS = "Demographics"
GROUP_LIFESTYLE = "Lifestyle"
GROUP_PRODUCTS = "Products owned"
GROUP_SPENDING = "Spending behavior"

ATTRIBUTE_GROUP_ORDER: list[str] = [
    GROUP_DEMOGRAPHICS,
    GROUP_LIFESTYLE,
    GROUP_PRODUCTS,
    GROUP_SPENDING,
]

# The group an unmapped column falls back under (Requirement 3.1 graceful
# fallback: a title-cased label under a default group).
_FALLBACK_GROUP = GROUP_DEMOGRAPHICS

# The ``owns_<product_type>`` prefix produced by the join pivot (Requirement 1.2);
# every such flag is a "Products owned" attribute regardless of the exact type.
_OWNERSHIP_PREFIX = "owns_"

# Explicit raw-column -> (Attribute_Group, Attribute_Display_Label) mapping for
# the known Joined_Attribute_Set columns (customer_dna + features_part2). Columns
# not listed here -- including every ``owns_*`` flag -- are handled by the rules
# in :func:`attribute_group_and_label`. These labels are presentation only; the
# raw column name is always the value passed to the pipeline (Requirement 3.1).
_ATTRIBUTE_MAP: dict[str, tuple[str, str]] = {
    # --- Demographics (customer_dna profile fields) ---
    "segment": (GROUP_DEMOGRAPHICS, "Customer segment"),
    "age_band": (GROUP_DEMOGRAPHICS, "Age band"),
    "tenure_years": (GROUP_DEMOGRAPHICS, "Years with the bank"),
    "region": (GROUP_DEMOGRAPHICS, "Region"),
    "sec_class": (GROUP_DEMOGRAPHICS, "Socio-economic class"),
    "email_valid": (GROUP_DEMOGRAPHICS, "Has a valid email"),
    "mobile_valid": (GROUP_DEMOGRAPHICS, "Has a valid mobile number"),
    # --- Lifestyle (behaviour-flavoured profile fields) ---
    "inflow_type": (GROUP_LIFESTYLE, "Main money-in type"),
    "digital_app_user": (GROUP_LIFESTYLE, "Uses the mobile app"),
    "online_shopper": (GROUP_LIFESTYLE, "Shops online"),
    "frugal_flag": (GROUP_LIFESTYLE, "Frugal spender"),
    "investment_propensity_decile": (GROUP_LIFESTYLE, "Investment appetite (1-10)"),
    # --- Spending behavior (features_part2 behavioural features) ---
    "total_out": (GROUP_SPENDING, "Total outflows"),
    "out_other_bank": (GROUP_SPENDING, "Outflows to other banks"),
    "ext_outflow_ratio": (GROUP_SPENDING, "Share of outflows leaving the bank"),
    "months_with_ext_transfer": (GROUP_SPENDING, "Months sending money out"),
    "inflow_share_payroll": (GROUP_SPENDING, "Income from payroll"),
    "inflow_share_remittance": (GROUP_SPENDING, "Income from remittances"),
    "inflow_share_business_receipts": (GROUP_SPENDING, "Income from business"),
    "spend_share_bank_transfer": (GROUP_SPENDING, "Spend on bank transfers"),
    "spend_share_e_commerce": (GROUP_SPENDING, "Spend on e-commerce"),
    "spend_share_education": (GROUP_SPENDING, "Spend on education"),
    "spend_share_fuel": (GROUP_SPENDING, "Spend on fuel"),
    "spend_share_grocery": (GROUP_SPENDING, "Spend on groceries"),
    "spend_share_health": (GROUP_SPENDING, "Spend on health"),
    "spend_share_insurance_premium": (GROUP_SPENDING, "Spend on insurance"),
    "spend_share_p2p_transfer": (GROUP_SPENDING, "Spend on peer transfers"),
    "spend_share_restaurants": (GROUP_SPENDING, "Spend on restaurants"),
    "spend_share_retail": (GROUP_SPENDING, "Spend on retail"),
    "spend_share_telco": (GROUP_SPENDING, "Spend on telco"),
    "spend_share_travel": (GROUP_SPENDING, "Spend on travel"),
    "spend_share_utilities": (GROUP_SPENDING, "Spend on utilities"),
}

# The sensible Default_Attribute_Set preselected on first load so Run works
# immediately without the user choosing anything (Requirement 3.13). A compact,
# interpretable mix of one lifestyle, one demographic, and two behavioural
# attributes -- all raw column names so they pass straight to the pipeline.
DEFAULT_ATTRIBUTE_SET: list[str] = [
    "age_band",
    "digital_app_user",
    "total_out",
    "inflow_share_payroll",
]


def _humanize(column: str) -> str:
    """Title-case a raw column name for the graceful unmapped-column fallback.

    Turns ``snake_case`` into "Title Case Words" ("some_new_col" -> "Some New
    Col"), used only when a column has no explicit mapping (Requirement 3.1).
    """
    return column.replace("_", " ").strip().title()


def attribute_group_and_label(column: str) -> tuple[str, str]:
    """Return the ``(Attribute_Group, Attribute_Display_Label)`` for a raw column.

    Presentation mapping only (Requirement 3.1): the raw ``column`` name stays the
    value passed to the Persona_Pipeline; this just decides how the Attribute_Picker
    *shows* it. Resolution order:

    1. an ``owns_<type>`` ownership flag -> ``("Products owned", "Owns <type>
       account")`` (so ``owns_deposit`` reads "Owns deposit account");
    2. an explicit entry in :data:`_ATTRIBUTE_MAP`;
    3. graceful fallback -- a title-cased label under the default group
       (Requirement 3.1), so an unmapped column still appears cleanly.

    Returns:
        A ``(group_heading, display_label)`` tuple.
    """
    if column.startswith(_OWNERSHIP_PREFIX):
        product = column[len(_OWNERSHIP_PREFIX) :].replace("_", " ").strip()
        label = f"Owns {product} account" if product else "Owns account"
        return GROUP_PRODUCTS, label

    if column in _ATTRIBUTE_MAP:
        return _ATTRIBUTE_MAP[column]

    return _FALLBACK_GROUP, _humanize(column)


def attribute_display_label(column: str) -> str:
    """The Attribute_Display_Label for a raw column (Requirement 3.1)."""
    return attribute_group_and_label(column)[1]


def group_attributes_by_theme(columns: list[str]) -> dict[str, list[str]]:
    """Bucket raw columns under their Attribute_Group heading, in display order.

    Groups the ``columns`` of the Joined_Attribute_Set under the four headings
    (Requirement 3.1), skipping ``client_id`` (never an attribute to cluster on).
    Within a group columns keep their input order; the returned dict is ordered by
    :data:`ATTRIBUTE_GROUP_ORDER` and omits empty groups.

    Returns:
        ``{group_heading: [raw_column, ...]}`` for every non-empty group, in
        display order.
    """
    buckets: dict[str, list[str]] = {group: [] for group in ATTRIBUTE_GROUP_ORDER}
    for column in columns:
        if column == "client_id":
            continue
        group, _label = attribute_group_and_label(column)
        buckets.setdefault(group, []).append(column)
    return {group: cols for group, cols in buckets.items() if cols}


# --------------------------------------------------------------------------- #
# Distinguishing attributes -> plain business sentences (Requirement 4.10)    #
# --------------------------------------------------------------------------- #
def _standardized_direction(
    column: str,
    profile: PersonaProfile,
    all_profiles: list[PersonaProfile],
) -> str | None:
    """Return "higher"/"lower"/"more"/"fewer"/None for a persona's attribute.

    A pure display transform over already-computed profile values
    (Requirement 4.10): it compares this persona's value for ``column`` against the
    across-persona average, exactly mirroring the design D2 standardization
    direction (sign of ``value - mean``), and returns a direction word. It never
    recomputes any clustering or ranking.

    For a numeric attribute it compares the persona's ``numeric_mean[column]`` to
    the across-persona mean of those means and returns "higher"/"lower". For a
    categorical/ownership attribute it compares the persona's share of its top
    category to the other personas' and returns "more"/"fewer". Returns ``None``
    when the direction is flat (no contrast) so the caller can omit the phrase.
    """
    numeric_means = [
        p.numeric_mean[column] for p in all_profiles if column in p.numeric_mean
    ]
    if column in profile.numeric_mean and numeric_means:
        avg = sum(numeric_means) / len(numeric_means)
        value = profile.numeric_mean[column]
        if value > avg:
            return "higher"
        if value < avg:
            return "lower"
        return None

    # Categorical: compare this persona's dominant-category share vs the pooled
    # others. top_categories holds (category, count) pairs; the persona's size is
    # the sum of its own counts for the attribute.
    if column in profile.top_categories:
        own_cats = profile.top_categories[column]
        if not own_cats:
            return None
        top_cat = own_cats[0][0]
        own_total = sum(c for _cat, c in own_cats) or 1
        own_share = own_cats[0][1] / own_total

        other_share_values: list[float] = []
        for other in all_profiles:
            if other is profile:
                continue
            cats = other.top_categories.get(column, [])
            total = sum(c for _cat, c in cats)
            if total == 0:
                continue
            match = next((c for cat, c in cats if cat == top_cat), 0)
            other_share_values.append(match / total)
        if not other_share_values:
            return None
        other_avg = sum(other_share_values) / len(other_share_values)
        if own_share > other_avg:
            return "more"
        if own_share < other_avg:
            return "fewer"
        return None

    return None


def _phrase_for(direction: str, label: str) -> str:
    """Compose one plain-language fragment for a distinguishing sentence.

    Numeric directions ("higher"/"lower") read naturally before a lower-cased
    label ("higher total outflows"). Categorical directions ("more"/"fewer") are
    rephrased into "more/fewer likely to <be/have ...>" so they stay readable:
    an "Owns ... account" label becomes "more likely to own ... account", a
    "Has ..." label becomes "more likely to have ...", and any other categorical
    label is prefixed with "more likely to be ...". Kept simple and deterministic
    (Requirement 4.10).
    """
    low = label.lower()
    if direction in ("higher", "lower"):
        return f"{direction} {low}"

    # Categorical "more"/"fewer" -> a readable "<more/fewer> likely to ..." phrase.
    if low.startswith("owns "):
        subject = low[len("owns ") :]
        return f"{direction} likely to own {subject}"
    if low.startswith("has "):
        subject = low[len("has ") :]
        return f"{direction} likely to have {subject}"
    return f"{direction} likely to be {low}"


def distinguishing_sentences(
    profile: PersonaProfile,
    all_profiles: list[PersonaProfile],
) -> str:
    """Render a persona's distinguishing attributes as one plain sentence (Req 4.10).

    A presentation transform over :attr:`PersonaProfile.distinguishing` (whose
    ranking is still the design-D2 computation): for each distinguishing attribute
    it emits a "higher/lower/more/fewer <attribute> than other personas" phrase by
    comparing the persona's value to the across-persona average, then joins the
    phrases into a single business sentence. It reads only already-computed profile
    values and adds no modelling (Requirement 4.10).

    Example output: "Higher total outflows and fewer products than other
    personas." When no attribute shows a clear direction (e.g. a single persona),
    it returns a neutral "Broadly average across the selected attributes." phrase.

    Args:
        profile: The persona whose distinguishing attributes to describe.
        all_profiles: Every persona in the same set (the across-persona baseline).

    Returns:
        A single capitalized sentence, safe to render as plain text.
    """
    fragments: list[str] = []
    for column in profile.distinguishing:
        direction = _standardized_direction(column, profile, all_profiles)
        if direction is None:
            continue
        label = attribute_display_label(column)
        fragments.append(_phrase_for(direction, label))

    if not fragments:
        return "Broadly average across the selected attributes."

    if len(fragments) == 1:
        body = fragments[0]
    else:
        body = ", ".join(fragments[:-1]) + f" and {fragments[-1]}"

    sentence = f"{body} than other personas"
    return sentence[0].upper() + sentence[1:] + "."


# --------------------------------------------------------------------------- #
# Actionable messages (Requirements 6.2, 6.10)                                #
# --------------------------------------------------------------------------- #
def validation_error(
    n_attributes: int,
    k: int,
    level: str | None,
    *,
    k_min: int = 2,
    k_max: int = 6,
) -> str | None:
    """Return the actionable validation message, or ``None`` when the config is valid.

    Checks the Run-time validity rules (Requirement 6.2): at least one attribute
    selected, ``k`` an integer in ``[k_min, k_max]``, and a Clustering_Level
    chosen. The message names the invalid input and tells the user how to fix it
    (e.g. "Pick at least one attribute to build personas"), so the Persona_Page can
    reject the run while retaining the current configuration and displayed results.

    The first failing check (attributes, then k, then level) wins so the user is
    guided one fix at a time. Returns ``None`` when every check passes.
    """
    if n_attributes < 1:
        return "Pick at least one attribute to build personas."
    if not isinstance(k, int) or k < k_min or k > k_max:
        return (
            f"Set the number of personas to a whole number from {k_min} to "
            f"{k_max}."
        )
    if not level:
        return "Choose how to group leads: all leads, by customer segment, or by campaign."
    return None


def too_small_message(group_key: str, lead_count: int) -> str:
    """Return the actionable "too small to cluster" instruction (Requirement 6.10).

    States the group's lead count and tells the user how to proceed, rather than a
    bare status flag -- e.g. "This segment has only 12 leads. Pick a larger segment
    or combine segments." When ``group_key`` is empty (level ``all``) the message
    refers to "this audience" instead of a named segment.
    """
    where = f'"{group_key}"' if group_key else "this audience"
    return (
        f"{where} has only {lead_count:,} leads, too few to build personas. "
        "Pick a larger segment or combine segments, or lower the number of "
        "personas."
    )


# --------------------------------------------------------------------------- #
# Campaign pool labelling (Requirements 3.15, 5.3)                            #
# --------------------------------------------------------------------------- #
def promo_pool_label(promo_id: str, meta: dict[str, str] | None = None) -> str:
    """Return the campaign-pool display label for a ``promo_id`` (Req 3.15, 5.3).

    Shows the promo's name or date alongside its ``promo_id`` when such a label is
    available in ``meta`` (a ``{promo_id: label}`` lookup), while selection still
    keys on the bare ``promo_id``. Absent a label, the bare ``promo_id`` is shown
    (Requirement 3.15). The returned string is for display only; callers must map
    it back to ``promo_id`` via the option list they built.
    """
    if meta:
        label = meta.get(promo_id)
        if label:
            return f"{promo_id} -- {label}"
    return promo_id


# --------------------------------------------------------------------------- #
# Campaign_Leads_Export projection (Requirement 8.8)                          #
# --------------------------------------------------------------------------- #
def campaign_leads_export_frame(full_labeled_leads: pd.DataFrame) -> pd.DataFrame:
    """Project the full Persona_Labeled_Leads to the default Campaign_Leads_Export.

    A thin presentation-layer wrapper over
    :func:`part5_personas.export.campaign_leads_export` (Requirement 8.8): it keeps
    exactly ``client_id``, the persona-label column, the group column,
    ``best_channel``, ``p_join``, ``control`` -- one row per Part 4 lead, agreeing
    row-for-row with the full frame. Delegating keeps the column contract in the
    pipeline layer (no business logic in ``app/``).
    """
    return campaign_leads_export(full_labeled_leads)


# --------------------------------------------------------------------------- #
# Session-state keys                                                          #
# --------------------------------------------------------------------------- #
# The persona run result stashed after a successful Run, consumed by the summary
# cards, the downloads, and (task 14.2) the charts/mix. Namespaced so it never
# collides with main.py's RUN_RESULT_KEY.
PERSONA_RESULT_KEY = "persona_run_result"
# The full Persona_Labeled_Leads + the projected Campaign_Leads_Export, held so
# the download buttons stay enabled across reruns after a run completes.
PERSONA_EXPORTS_KEY = "persona_exports"
# Flash messages (level, text) surviving the post-Run rerun.
PERSONA_FLASH_KEY = "persona_flash_messages"


@dataclass(frozen=True)
class _PersonaExports:
    """The two download frames held in session state after a completed run."""

    campaign_leads: pd.DataFrame
    labeled_leads: pd.DataFrame


# --------------------------------------------------------------------------- #
# Cached backend wrappers (st.cache_data owned HERE, Requirement 6.8/6.9)     #
# --------------------------------------------------------------------------- #
def _spec_fingerprint(spec: PersonaRunSpec, seed: int) -> tuple:
    """A hashable fingerprint of a run spec for ``st.cache_data`` keying (design D3).

    Caches the run by sorted selected attributes, k, level, pool, grouping, the
    business-segment field, and the seed so a What-If tweak or a re-render that does
    not change these does not refit (design D3). Returned as a tuple of immutables
    so Streamlit can hash it.
    """
    return (
        spec.level,
        tuple(sorted(spec.clustering_attributes)),
        tuple(sorted(spec.grouping_attributes)),
        spec.k,
        spec.business_segment_field,
        spec.campaign_pool,
        tuple(sorted(spec.type_overrides.items())),
        seed,
    )


def _live_leads_fingerprint(live_leads: pd.DataFrame | None) -> tuple:
    """A hashable fingerprint of the live campaign pool (its client ids).

    The live New Promo pool (Requirement 5.1) is a DataFrame, so it cannot go into
    the ``st.cache_data`` key directly. This reduces it to the sorted tuple of its
    ``client_id`` values -- exactly what makes two live runs differ -- so a
    different live audience is a genuine cache miss. ``None`` (no live pool) and a
    clientless frame both fingerprint to ``()``.
    """
    if live_leads is None or "client_id" not in getattr(live_leads, "columns", []):
        return ()
    return tuple(sorted(str(cid) for cid in live_leads["client_id"].tolist()))


def _run_personas_impl(
    fingerprint: tuple,
    live_fingerprint: tuple,
    _spec: PersonaRunSpec,
    _live_leads: pd.DataFrame | None,
) -> PersonaRunResult:
    """The persona run body behind the ``st.cache_data`` boundary (design D3).

    Defined **once at module scope** -- never nested inside the caller -- so that,
    when wrapped by ``st.cache_data``, Streamlit memoizes it against its *hashed
    arguments* rather than against free variables captured from an enclosing frame.
    (The previous nested/closure version returned a stale result because the cache
    could not see the captured ``spec``, so changing the selected attributes left
    the output unchanged.)

    Cache key: the two leading positional arguments ``_fingerprint`` (the full
    :func:`_spec_fingerprint`) and ``_live_fingerprint`` (the live pool's
    :func:`_live_leads_fingerprint`) are the complete key -- change any attribute,
    k, level, pool, grouping field, seed, or the live audience and the key changes,
    so a reconfigured run genuinely refits. ``_spec`` and ``_live_leads`` have a
    leading underscore so Streamlit's input hasher ignores them (the fingerprints
    already capture everything they can affect); they carry the unhashable
    ``PersonaRunSpec`` / DataFrame through to the actual run without breaking the
    key. The keyed args (`fingerprint`/`live_fingerprint`) deliberately have NO
    leading underscore so Streamlit DOES hash them -- a leading underscore on a
    parameter tells Streamlit to skip it, so if every parameter were underscored
    the key would be constant and every run would collide (the earlier failure).
    """
    from part5_personas.config import Config

    return run_personas(_spec, cfg=Config(), live_leads=_live_leads)


# Lazily-built ``st.cache_data`` wrapper around :func:`_run_personas_impl`. Built
# on first use so importing this module never requires Streamlit (task 14.1 bar);
# cached as a module singleton so the wrapper -- and thus its memo -- is created
# once rather than redefined per call (the bug that defeated caching before).
_CACHED_RUNNER = None


def _get_cached_runner():
    """Return the memoized ``st.cache_data`` wrapper around :func:`_run_personas_impl`.

    Imports Streamlit lazily (Requirement 6.8 keeps the cache in ``app/`` while the
    module stays importable without a server) and wraps the module-scope impl
    exactly once, storing it in :data:`_CACHED_RUNNER` so every call shares one
    Streamlit cache.
    """
    global _CACHED_RUNNER
    if _CACHED_RUNNER is None:
        import streamlit as st

        _CACHED_RUNNER = st.cache_data(show_spinner=False)(_run_personas_impl)
    return _CACHED_RUNNER


def _run_personas_cached(
    spec: PersonaRunSpec,
    live_leads: pd.DataFrame | None,
) -> PersonaRunResult:
    """Run a persona generation, cached by the spec + live-pool fingerprints (design D3).

    Thin wrapper: it computes the two cache-key fingerprints and delegates to the
    module-scope cached :func:`_run_personas_impl` (via :func:`_get_cached_runner`).
    A re-render or What-If tweak that changes neither fingerprint is served from
    cache (design D3); any attribute/k/level/pool change refits because it changes
    :func:`_spec_fingerprint`. ``live_leads`` feeds the ``campaign`` live pool
    (Requirement 5.1) and is keyed via :func:`_live_leads_fingerprint`.
    """
    from part5_personas.config import Config

    seed = Config().random_seed
    runner = _get_cached_runner()
    return runner(
        _spec_fingerprint(spec, seed),
        _live_leads_fingerprint(live_leads),
        spec,
        live_leads,
    )


# --------------------------------------------------------------------------- #
# Rendering helpers (lazy ``streamlit`` import)                               #
# --------------------------------------------------------------------------- #
def _joined_attribute_columns() -> list[str]:
    """The Joined_Attribute_Set columns offered in the Attribute_Picker.

    Reads the columns from a cached build of the joined set so the picker reflects
    the real data (including every ``owns_*`` flag). Falls back to the known
    customer_dna + features_part2 + default ownership columns when the artifacts
    are missing, so the page still renders a sensible picker before a pipeline run.
    """
    import streamlit as st

    from part5_personas.config import Config
    from part5_personas.join import build_joined_attributes

    @st.cache_data(show_spinner=False)
    def _columns() -> list[str]:
        try:
            joined, _report = build_joined_attributes(Config())
        except Exception:  # noqa: BLE001 - a missing/unreadable source degrades gracefully
            return list(_ATTRIBUTE_MAP.keys())
        return [c for c in joined.columns if c != "client_id"]

    return _columns()


def _available_promo_meta() -> dict[str, str]:
    """A ``{promo_id: label}`` lookup for the campaign pool selector (Req 3.15).

    Reads the promo name/date from ``outputs/cards.json`` when available so the
    campaign-pool selector can show a label beside each ``promo_id`` while still
    selecting by ``promo_id``. Degrades to an empty mapping (bare ids) when the
    file is absent or carries no usable label.
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    cards_path = root / "outputs" / "cards.json"
    meta: dict[str, str] = {}
    try:
        with open(cards_path, encoding="utf-8") as fh:
            cards = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return meta
    for card in cards:
        promo_id = str(card.get("promo_id", ""))
        if not promo_id or promo_id in meta:
            continue
        label = card.get("promo_name") or card.get("promo_date") or card.get("reward")
        if label:
            meta[promo_id] = str(label)
    return meta


def _show_messages(messages: list[tuple[str, str]]) -> None:
    """Display ``(level, text)`` messages as Streamlit alerts (mirrors main.py)."""
    import streamlit as st

    for level, text in messages:
        {"error": st.error, "warning": st.warning, "success": st.success}.get(
            level, st.info
        )(text)


def _persona_card_html(
    persona_name: str,
    description: str,
    size: int,
    pct: float,
    distinguishing_sentence: str,
    actions: list[str],
) -> str:
    """Build the (escaped) body HTML for one persona summary card (Req 6.3).

    Shows the name, description, the integer size and one-decimal percentage as
    stat chips, the distinguishing attributes as a plain sentence
    (Requirement 4.10), and the recommended actions as campaign guidance
    (Requirement 4.5). Reuses the ``pan-chip`` style via raw HTML so the card
    matches the rest of the app without new CSS classes.
    """
    chips = (
        f'<span class="pan-chip">{size:,} leads</span>'
        f'<span class="pan-chip">{pct:.1f}%</span>'
    )
    desc_html = html.escape(str(description))
    distinguishing_html = html.escape(distinguishing_sentence)
    actions_items = "".join(
        f"<li style=\"margin-bottom:4px;\">{html.escape(str(a))}</li>" for a in actions
    )
    return (
        f'<div style="margin-bottom:10px;">{chips}</div>'
        f'<div style="margin-bottom:10px;color:var(--pan-charcoal);">{desc_html}</div>'
        '<div style="margin-bottom:6px;">'
        '<span style="color:var(--pan-gray);font-size:0.78rem;">What sets them apart</span>'
        f'<br/><span style="font-weight:600;">{distinguishing_html}</span></div>'
        '<div style="margin-top:8px;">'
        '<span style="color:var(--pan-gray);font-size:0.78rem;">Recommended actions</span>'
        f'<ul style="margin:6px 0 0 18px;padding:0;">{actions_items}</ul></div>'
    )


def _render_summary_cards(result: PersonaRunResult) -> None:
    """Render one summary card per persona, across every persona set (Req 6.3, 6.10).

    Walks the run's :class:`PersonaSet` list. A set flagged ``too_small`` renders
    the actionable too-small instruction (Requirement 6.10) instead of cards. For a
    clustered set, each persona gets a card (name, description, integer size,
    one-decimal percentage, plain distinguishing sentence, campaign-guidance
    actions). Cards are laid out two per row to match the Results tab.
    """
    import streamlit as st
    import theme

    for persona_set in result.persona_sets:
        if persona_set.group_key:
            st.markdown(f"**Segment: {persona_set.group_key}**")

        if persona_set.too_small:
            # The too-small group reports no personas; show the actionable count.
            # The lead count is recovered from the labels frame scoped to the group.
            lead_count = _group_lead_count(result, persona_set.group_key)
            st.warning(too_small_message(persona_set.group_key, lead_count))
            continue

        profiles = [p.profile for p in persona_set.personas]
        personas = persona_set.personas
        for i in range(0, len(personas), 2):
            pair = personas[i : i + 2]
            cols = st.columns(2)
            for col, persona in zip(cols, pair):
                with col:
                    sentence = distinguishing_sentences(persona.profile, profiles)
                    theme.card(
                        persona.name,
                        _persona_card_html(
                            persona.name,
                            persona.description,
                            persona.profile.size,
                            persona.profile.pct_of_leads,
                            sentence,
                            persona.actions,
                        ),
                    )


def _group_lead_count(result: PersonaRunResult, group_key: str) -> int:
    """Best-effort lead count for a group, for the too-small message (Req 6.10).

    A too-small :class:`PersonaSet` carries no personas and no size, so the count
    is recovered from the run's ``labels`` frame when it carries the group column;
    otherwise 0 is returned (the message still reads sensibly). This is a display
    helper only.
    """
    labels = result.labels
    if labels is None or labels.empty or GROUP_COLUMN not in labels.columns:
        return 0
    return int((labels[GROUP_COLUMN] == group_key).sum())


def _render_downloads() -> None:
    """Render the two download controls, disabled until a run completes (Req 8.10).

    Defaults to the Campaign_Leads_Export and offers the full Persona_Labeled_Leads
    as a clearly labeled optional second download (Requirements 8.8-8.10). Both
    buttons are disabled until a persona run has completed in the session
    (Requirement 6.7): when no exports are held, disabled placeholder buttons are
    shown so the controls are always visible but inert.
    """
    import streamlit as st

    exports: _PersonaExports | None = st.session_state.get(PERSONA_EXPORTS_KEY)
    st.subheader("Download Personas")

    dl_cols = st.columns(2)
    if exports is None:
        with dl_cols[0]:
            st.download_button(
                "Download Campaign Leads (CSV)",
                data=b"",
                file_name="campaign_leads.csv",
                mime="text/csv",
                disabled=True,
                key="persona_dl_campaign_disabled",
                help="Run personas first to enable this download.",
            )
        with dl_cols[1]:
            st.download_button(
                "Download Full Labeled Leads (CSV, optional)",
                data=b"",
                file_name="persona_labeled_leads.csv",
                mime="text/csv",
                disabled=True,
                key="persona_dl_full_disabled",
                help="Run personas first to enable this download.",
            )
        return

    campaign_bytes = exports.campaign_leads.to_csv(index=False).encode("utf-8")
    full_bytes = exports.labeled_leads.to_csv(index=False).encode("utf-8")
    with dl_cols[0]:
        st.download_button(
            f"Download Campaign Leads ({len(exports.campaign_leads):,})",
            data=campaign_bytes,
            file_name="campaign_leads.csv",
            mime="text/csv",
            key="persona_dl_campaign",
            help=(
                "The CRM-ready list: client id, persona, group, best channel, "
                "join probability, and control flag."
            ),
        )
    with dl_cols[1]:
        st.download_button(
            f"Download Full Labeled Leads ({len(exports.labeled_leads):,}, optional)",
            data=full_bytes,
            file_name="persona_labeled_leads.csv",
            mime="text/csv",
            key="persona_dl_full",
            help="The full list with every joined attribute, for deeper analysis.",
        )


def _build_spec(
    level: str,
    attributes: list[str],
    k: int,
    business_segment_field: str | None,
    campaign_pool: str | None,
    grouping_attributes: list[str],
) -> PersonaRunSpec:
    """Assemble a :class:`PersonaRunSpec` from the page's widget values.

    The Attribute_Picker selection is the ``clustering_attributes``; the optional
    two-step control's attributes are the ``grouping_attributes``; "Number of
    personas" is the per-group ``k`` (Requirement 3.8). The spec handed to the
    pipeline is identical to configuring the two controls separately -- only the
    page collapses them into one control.
    """
    return PersonaRunSpec(
        level=level,
        clustering_attributes=list(attributes),
        grouping_attributes=list(grouping_attributes),
        k=k,
        business_segment_field=business_segment_field,
        campaign_pool=campaign_pool,
    )


def render_persona_tab(run_result_key: str = "run_result") -> None:
    """Render the Persona_Page tab body: controls, Run, summary cards, downloads.

    The single entry point wired into ``app/main.py``'s tab list (task 14.1). It
    composes, in order:

    1. the **Clustering_Level** selector (plain labels, default "All leads"), the
       **Number of personas** k selector (2-6, default 3), and -- depending on the
       level -- the **Business_Segment_Field** selector or the **campaign pool**
       selector (Requirements 3.4, 3.5, 5.1-5.3, 6.1);
    2. the grouped **Attribute_Picker** with readable labels and a preselected
       Default_Attribute_Set (Requirements 3.1, 3.13);
    3. the optional **two-step** control "Split by ... first ..." (Requirement 3.8);
    4. a **Run** control that validates the config (Requirement 6.2), runs the
       cached backend, and stashes the result + exports in session state;
    5. one **summary card** per persona (Requirement 6.3) with the too-small
       instruction for flagged groups (Requirement 6.10); and
    6. the two **download** controls, default Campaign_Leads_Export + optional full
       Persona_Labeled_Leads, disabled until a run completes (Requirements 8.8-8.10).

    All clustering/profiling is delegated to the cached
    :func:`webapp_core.personas.run_personas`; this function only wires widgets and
    session state (Requirement 6.9). The charts and the on-card persona mix are
    task 14.2 and are intentionally not rendered here.

    Args:
        run_result_key: The session-state key under which ``main.py`` stashes the
            New Promo :class:`RunResult`; used to detect a live campaign pool
            (Requirement 5.2).
    """
    import streamlit as st

    st.subheader("Build Personas")
    st.caption(
        "Group your leads into personas, see what sets each one apart, and "
        "download a CRM-ready list. Pick the attributes and press Build."
    )

    # Flash messages from the previous Run survive the post-Run rerun.
    _show_messages(st.session_state.pop(PERSONA_FLASH_KEY, []))

    columns = _joined_attribute_columns()
    grouped = group_attributes_by_theme(columns)

    # --- top controls: level, k, and the level-specific selector ---
    ctl_left, ctl_right = st.columns(2)
    with ctl_left:
        level_label = st.selectbox(
            "How to group leads",
            options=LEVEL_LABEL_ORDER,
            index=0,
            help=(
                "All leads builds one set of personas. By customer segment builds "
                "a set per segment. By campaign uses one campaign's audience."
            ),
        )
        level = level_label_to_value(level_label)
    with ctl_right:
        k = int(
            st.number_input(
                "Number of personas",
                min_value=2,
                max_value=6,
                value=3,
                step=1,
                help="Between 2 and 6. Start at 3 and adjust.",
            )
        )

    business_segment_field: str | None = None
    campaign_pool: str | None = None

    if level == LEVEL_BUSINESS_SEGMENT:
        # Choose the Business_Segment_Field (Requirement 3.5). The two supported
        # fields are the customer_dna segment and the Part 3 Segment_Label.
        field_label = st.selectbox(
            "Segment field",
            options=["Customer segment (customer_dna)", "Part 3 segment label"],
            index=0,
            help="Build one set of personas per value of this field.",
        )
        business_segment_field = (
            "segment" if field_label.startswith("Customer segment") else "segment_label"
        )

    if level == LEVEL_CAMPAIGN:
        campaign_pool = _render_campaign_pool_selector(run_result_key)

    # --- Attribute_Picker: grouped multiselect with readable labels ---
    st.markdown("**Attributes to build personas on**")
    selected_attributes: list[str] = []
    picker_cols = st.columns(2)
    for i, (group, cols) in enumerate(grouped.items()):
        with picker_cols[i % 2]:
            defaults = [c for c in cols if c in DEFAULT_ATTRIBUTE_SET]
            chosen = st.multiselect(
                group,
                options=cols,
                default=defaults,
                format_func=attribute_display_label,
                key=f"persona_attr_{group}",
            )
            selected_attributes.extend(chosen)

    # --- optional two-step control (Requirement 3.8) ---
    grouping_attributes: list[str] = []
    two_step = st.checkbox(
        "Split into groups first, then build personas within each group",
        value=False,
        help=(
            "Optional. Choose attributes to split leads into groups first; "
            "personas are then built within each group."
        ),
    )
    if two_step:
        grouping_attributes = st.multiselect(
            "Split by",
            options=[c for c in columns if c != "client_id"],
            default=[],
            format_func=attribute_display_label,
            key="persona_grouping_attrs",
            help='Reads as "Split by [these] first, then create personas within each group".',
        )

    # --- Run control + validation (Requirements 6.1, 6.2) ---
    run_clicked = st.button("Build Personas", type="primary", key="persona_run")
    if run_clicked:
        error = validation_error(len(selected_attributes), k, level)
        if error is not None:
            # Reject the run, RETAIN config + displayed results (Requirement 6.2):
            # we simply show the error and fall through to re-render whatever run
            # result is already in session state.
            st.error(error)
        else:
            _handle_run(
                level=level,
                attributes=selected_attributes,
                k=k,
                business_segment_field=business_segment_field,
                campaign_pool=campaign_pool,
                grouping_attributes=grouping_attributes,
                run_result_key=run_result_key,
            )

    # --- results: summary cards + downloads (persist across reruns) ---
    result: PersonaRunResult | None = st.session_state.get(PERSONA_RESULT_KEY)
    if result is not None:
        st.subheader("Personas")
        _render_summary_cards(result)

    _render_downloads()


def _render_campaign_pool_selector(run_result_key: str) -> str | None:
    """Render the campaign pool selector and return the chosen pool value.

    Lets the user pick the live New Promo session leads or a past promo by
    ``promo_id`` in {P001, P002, P003} (Requirements 5.1, 5.3). The live choice is
    disabled when no New Promo run exists in session state, with a message that a
    run is required first (Requirement 5.2). Past promos show the promo name/date
    beside the ``promo_id`` when available while selecting by ``promo_id``
    (Requirements 3.15, 5.3).

    Returns:
        ``"live"`` for the live pool, a ``promo_id`` string for a past promo, or
        ``None`` when the live pool is chosen but unavailable.
    """
    import streamlit as st

    has_live = st.session_state.get(run_result_key) is not None
    meta = _available_promo_meta()

    pool_kind = st.radio(
        "Campaign audience",
        options=["Current New Promo run", "A past promo"],
        index=1 if not has_live else 0,
        horizontal=True,
    )

    if pool_kind == "Current New Promo run":
        if not has_live:
            st.info(
                "Run a promo on the New Promo tab first to use its audience here."
            )
            return None
        return "live"

    # A past promo selected by promo_id, with a name/date label when available.
    options = list(CAMPAIGN_PROMO_IDS)
    chosen_label = st.selectbox(
        "Past promo",
        options=options,
        index=0,
        format_func=lambda pid: promo_pool_label(pid, meta),
    )
    return chosen_label


def _handle_run(
    *,
    level: str,
    attributes: list[str],
    k: int,
    business_segment_field: str | None,
    campaign_pool: str | None,
    grouping_attributes: list[str],
    run_result_key: str,
) -> None:
    """Execute a validated persona run and stash the result + exports in session.

    Builds the :class:`PersonaRunSpec`, resolves the live leads for a ``campaign``
    live pool from ``main.py``'s session result (Requirement 5.1), runs the cached
    backend, then builds the two export frames (Campaign_Leads_Export default +
    full Persona_Labeled_Leads) so the downloads enable (Requirements 8.8-8.10).
    Any backend error (empty audience, bad field, low match rate) is surfaced as an
    actionable message and the previous displayed result is retained
    (Requirement 6.2).
    """
    import streamlit as st

    spec = _build_spec(
        level,
        attributes,
        k,
        business_segment_field,
        campaign_pool,
        grouping_attributes,
    )

    live_leads = _live_leads_for(run_result_key) if campaign_pool == "live" else None

    with st.spinner("Building personas..."):
        try:
            result = _run_personas_cached(spec, live_leads)
            exports = _build_exports(result)
        except Exception as exc:  # noqa: BLE001 - surface any backend halt as a message
            st.error(f"Could not build personas: {exc}")
            return

    st.session_state[PERSONA_RESULT_KEY] = result
    st.session_state[PERSONA_EXPORTS_KEY] = exports
    n_personas = sum(len(ps.personas) for ps in result.persona_sets)
    st.session_state[PERSONA_FLASH_KEY] = [
        ("success", f"Built {n_personas} personas across {len(result.persona_sets)} group(s).")
    ]
    st.rerun()


def _live_leads_for(run_result_key: str) -> pd.DataFrame | None:
    """Return the New Promo run's sendable leads for the live campaign pool (Req 5.1).

    Reads ``main.py``'s :class:`RunResult` from session state and assembles a frame
    carrying ``client_id`` from the union of its per-segment sendable leads, which
    :func:`webapp_core.personas.run_personas` treats as the live pool. Returns
    ``None`` when no run exists.
    """
    import streamlit as st

    run_result = st.session_state.get(run_result_key)
    if run_result is None:
        return None

    sendable = getattr(run_result, "sendable_by_segment", None) or {}
    frames = [df for df in sendable.values() if df is not None and not df.empty]
    if not frames:
        # Fall back to the scored audience if no sendable split is available.
        scored = getattr(run_result, "scored", None)
        if scored is not None and "client_id" in getattr(scored, "columns", []):
            return scored[["client_id"]].drop_duplicates().reset_index(drop=True)
        return None

    combined = pd.concat(frames, ignore_index=True)
    if "client_id" not in combined.columns:
        return None
    return combined[["client_id"]].drop_duplicates().reset_index(drop=True)


def _build_exports(result: PersonaRunResult) -> _PersonaExports:
    """Build the two download frames from a completed run (Requirements 8.8-8.10).

    Delegates the full Persona_Labeled_Leads construction to the pipeline export
    builder and projects the default Campaign_Leads_Export from it, so the column
    contracts stay in the pipeline layer. The full frame is assembled from the
    Part 4 leads universe, the run's joined attributes, and the run's per-lead
    labels; when the leads universe is unavailable the labels themselves back a
    minimal frame so the downloads still enable.
    """
    from part5_personas.config import Config
    from part5_personas.export import (
        build_persona_labeled_leads,
        load_part4_leads_universe,
    )

    cfg = Config()
    labels = result.labels

    try:
        universe = load_part4_leads_universe(cfg.leads_dir)
        leads = universe[["client_id", "best_channel", "p_join", "control"]].copy()
    except (FileNotFoundError, KeyError):
        # No Part 4 leads on disk: back the export off the labels alone so the
        # download still works (one row per labeled lead).
        leads = pd.DataFrame({"client_id": labels.get("client_id", pd.Series(dtype=object))})
        for col in ("best_channel", "p_join", "control"):
            leads[col] = pd.NA

    full = build_persona_labeled_leads(leads, result.joined_attributes, labels)
    campaign = campaign_leads_export_frame(full)
    return _PersonaExports(campaign_leads=campaign, labeled_leads=full)
