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

Scope note: task 14.1 built the **page composition + session-state wiring** --
the Clustering_Level / k / Run controls, the grouped Attribute_Picker, the
optional two-step control, the campaign-pool selector, validation, the
per-persona summary cards, and the two download controls. Task 14.2 adds, after
a successful run, Streamlit **built-in** renders (no new chart dependency,
Requirement 9.9): the "How the Personas Differ" comparison table
(``st.dataframe`` of plain-language trait tags, Requirement 6.4), and the existing Part 4 cards rendered read-only
with an adjacent Persona_Mix badge and the unavailable fallback (Requirements
7.1, 7.2, 7.5). The Elbow_Plot is intentionally not shown on the page (revised
Requirement 6.5); the backend still computes it (Requirement 2.12).

Comparison-table pure helpers (importable without Streamlit, unit-tested in task
14.3) also live at module level:

- :func:`persona_trait_tags` / :func:`persona_comparison_frame` -- the plain-language
  trait tags and the one-row-per-persona comparison table frame (Requirement 6.4).

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
  (Requirement 4.10). A non-flag categorical names the persona's dominant
  category via :func:`categorical_phrase` ("more likely to be in the 35-44 age
  band", task 14.10); binary flags and numeric attributes keep their wording.
- :func:`validation_error` -- the actionable validation message for an invalid
  configuration (Requirement 6.2).
- :func:`too_small_message` -- the actionable "too small to cluster" instruction
  stating the group's lead count (Requirement 6.10).
- :func:`promo_pool_label` -- the "promo_id -- name/date" label for the campaign
  pool selector, selecting by ``promo_id`` (Requirements 3.15, 5.3).
- :func:`campaign_leads_export_frame` -- the default Campaign_Leads_Export column
  projection (Requirement 8.8), delegating to
  :func:`part5_personas.export.campaign_leads_export`.

Group-selector pure helpers (Requirements 3.16-3.19; task 14.7). The selector
appears when a run yields more than one persona set (the two-step flow, and also
the "By customer segment" level, which likewise produces one set per segment):

- :data:`ALL_GROUPS_LABEL`, :func:`group_options`, :func:`default_group` -- the
  selector options (too-small groups included, "All groups" last) and default.
- :func:`scope_result_to_group` / :func:`scope_export_frame` -- filter an already
  computed run / download frame to one group; never mutate input, never change a
  lead's persona label, never refit.
- :func:`group_download_filename` / :func:`group_download_caption` -- the group
  named in the download filename and a caption stating what the file contains.

Single-type pure helpers (Requirements 6.11, 6.12; task 14.9):

- :func:`selection_kind` -- numeric / categorical / mixed / none for a selection,
  given the pipeline's own column kinds (unknown columns ignored).
- :func:`effective_clustering_attributes` -- the selection minus the
  business-segment field at the business-segment / campaign levels.
- :func:`single_type_warning` / :func:`clustering_kind_caption` -- the
  non-blocking warning text and the post-run caption.

``streamlit`` is imported lazily inside the render functions so importing
``app.persona_page`` never requires a running Streamlit server (task 14.1
verification bar / task 14.3 testability).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, replace

import pandas as pd

from part5_personas.config import CAMPAIGN_PROMO_IDS
from part5_personas.export import (
    CAMPAIGN_LEADS_EXPORT_COLUMNS,
    GROUP_COLUMN,
    PERSONA_LABEL_COLUMN,
    campaign_leads_export,
)
from part5_personas.grouping import (
    BUSINESS_SEGMENT_FIELD,
    BUSINESS_SEGMENT_FIELD_OPTIONS,
    LEVEL_ALL,
    LEVEL_BUSINESS_SEGMENT,
    LEVEL_CAMPAIGN,
    InvalidSegmentFieldError,
    PersonaSet,
)
from part5_personas.labels import attribute_label as _pipeline_attribute_label
from part5_personas.labels import is_flag_attribute as _is_flag_attribute
from part5_personas.profile import PersonaProfile
from webapp_core.personas import (
    PersonaMix,
    PersonaRunResult,
    PersonaRunSpec,
    persona_mix_by_cell,
    run_personas,
)

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
    """Title-case the shared plain label for an unmapped column (Requirement 3.1).

    Delegates to the pipeline's canonical raw-column -> plain-label map
    (:func:`part5_personas.labels.attribute_label`) and title-cases the result, so
    a column with no explicit picker entry in :data:`_ATTRIBUTE_MAP` still reads in
    the same business language the persona names use. Columns the shared map does
    not know fall through to its own title-cased "words" fallback ("some_new_col"
    -> "Some New Col"). Keeping one label source avoids drift between the picker
    and the generated persona names.
    """
    return _pipeline_attribute_label(column).title()


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

    A pure display transform with a single source of truth (Requirement 4.10): it
    reads :attr:`PersonaProfile.distinguishing_directions` -- computed once by the
    profiling stage, which compares a binary flag on its share of "yes" -- and
    maps ``high`` -> "higher", ``low`` -> "lower", ``more`` -> "more", ``fewer`` ->
    "fewer". ``flat``, a missing entry, or a profile with no recorded directions
    returns ``None`` so the caller omits the phrase. It never re-derives a
    direction and never recomputes any clustering or ranking.

    ``all_profiles`` is kept for call-site compatibility and is not used.
    """
    direction = profile.distinguishing_directions.get(column)
    return {
        "high": "higher",
        "low": "lower",
        "more": "more",
        "fewer": "fewer",
    }.get(direction or "")


def _likelihood_word(direction: str) -> str:
    """Word before "likely": "fewer" -> "less", anything else -> "more" (task 14.11)."""
    return "less" if direction == "fewer" else direction


def _phrase_for(direction: str, label: str) -> str:
    """Compose one plain-language fragment for a distinguishing sentence.

    Numeric directions ("higher"/"lower") read naturally before a lower-cased
    label ("higher total outflows"). Categorical directions ("more"/"fewer") are
    rephrased into "more/less likely to <be/have ...>" ("fewer" reads "less
    likely"; task 14.11) so they stay readable:
    an "Owns ... account" label becomes "more likely to own ... account", a
    "Has ..." label becomes "more likely to have ...", a "Uses ..." / "Shops ..."
    label becomes "less likely to use the mobile app" / "... shop online", and
    any other categorical label is prefixed with "more likely to be ...". Kept
    simple and deterministic (Requirement 4.10).

    This label-based wording is used for numeric attributes, binary flags, and as
    the fallback for a non-binary categorical with no recorded top category; a
    non-binary categorical with a dominant category uses
    :func:`categorical_phrase` instead (task 14.10).
    """
    low = label.lower()
    if direction in ("higher", "lower"):
        return f"{direction} {low}"

    # Categorical "more"/"fewer" -> a readable "<more/less> likely to ..." phrase.
    word = _likelihood_word(direction)
    if low.startswith("owns "):
        subject = low[len("owns ") :]
        return f"{word} likely to own {subject}"
    if low.startswith("has "):
        subject = low[len("has ") :]
        return f"{word} likely to have {subject}"
    if low.startswith("uses "):
        return f"{word} likely to use {low[len('uses ') :]}"
    if low.startswith("shops "):
        return f"{word} likely to shop {low[len('shops ') :]}"
    return f"{word} likely to be {low}"


def categorical_phrase(column: str, category: str, direction: str) -> str:
    """Phrase naming a persona's dominant category for a non-flag categorical.

    Returns the text that follows the direction word, so the sentence reads
    ``"<more|less> likely <phrase>"`` (tasks 14.10/14.11, Requirement 4.10), e.g.
    ``categorical_phrase("age_band", "35-44", "more")`` ->
    ``"more likely to be in the 35-44 age band"``. ``direction`` is "more" or
    "fewer" (rendered "less likely"). Known columns have natural wording; ``online_shopper`` is an ordinal
    text level (not a yes/no flag); any other categorical reads
    "to have <label> of <category>". Pure and deterministic.
    """
    cat = str(category)
    if column == "age_band":
        tail = f"to be in the {cat} age band"
    elif column == "region":
        tail = f"to be in the {cat} region"
    elif column == "segment":
        tail = f"to be in the {cat} customer segment"
    elif column == "sec_class":
        tail = f"to be in socio-economic class {cat}"
    elif column == "inflow_type":
        tail = f"to have {cat} as their main money-in type"
    elif column == "online_shopper":
        tail = f"to be a {cat.lower()} online shopper"
    else:
        label = re.sub(r"\s*\([^)]*\)\s*$", "", attribute_display_label(column))
        tail = f"to have {label.lower()} of {cat}"
    return f"{_likelihood_word(direction)} likely {tail}"


def _dominant_category(profile: PersonaProfile, column: str) -> str | None:
    """Dominant category of a NON-binary categorical column, else ``None``.

    ``None`` for a binary 0/1 flag, a numeric attribute, or a categorical with no
    recorded top category (callers then keep the label-based wording).
    """
    top = profile.top_categories.get(column) or []
    if not top:
        return None
    if {str(cat) for cat, _count in top} <= {"0", "1"}:
        return None
    return str(top[0][0])


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
        dominant = (
            _dominant_category(profile, column)
            if direction in ("more", "fewer")
            else None
        )
        if dominant is not None:
            fragments.append(categorical_phrase(column, dominant, direction))
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
# Persona comparison table pure helpers (Requirement 6.4) -- no Streamlit      #
# --------------------------------------------------------------------------- #
_NO_CONTRAST_TAG = "Broadly average"
_MAX_TRAIT_TAGS = 3
COMPARISON_COLUMNS: list[str] = ["Persona", "Size", "Share", "What makes them stand out"]


def persona_trait_tags(profile: PersonaProfile) -> list[str]:
    """Plain-language trait tags for one persona (Requirement 6.4).

    Reads :attr:`PersonaProfile.distinguishing_directions` (the same source the
    persona names use) for up to three of the persona's top distinguishing
    attributes: numeric ``high``/``low`` -> "Higher/Lower <label>"; flag or
    categorical ``more``/``fewer`` -> "More/Fewer <label>"; ``flat`` (no contrast)
    is skipped. Labels are the plain lower-case
    :func:`part5_personas.labels.attribute_label`. No numbers are shown. When no
    tag results the single tag "Broadly average" is returned.
    """
    directions = profile.distinguishing_directions
    tags: list[str] = []
    for column in profile.distinguishing[:_MAX_TRAIT_TAGS]:
        direction = directions.get(column)
        label = _pipeline_attribute_label(column)
        if _is_flag_attribute(column):
            # 0/1 flags may be profiled as numeric; read them as More/Fewer.
            direction = {"high": "more", "low": "fewer"}.get(direction, direction)
        if direction == "high":
            tags.append(f"Higher {label}")
        elif direction == "low":
            tags.append(f"Lower {label}")
        elif direction == "more":
            tags.append(f"More {label}")
        elif direction == "fewer":
            tags.append(f"Fewer {label}")
        # "flat" / unknown: no contrast, skip.
    return tags or [_NO_CONTRAST_TAG]


def persona_comparison_frame(persona_set: PersonaSet) -> pd.DataFrame:
    """Side-by-side "How the Personas Differ" table for one set (Requirement 6.4).

    One row per persona with columns ``Persona`` (name), ``Size`` (integer leads),
    ``Share`` (one-decimal percentage text) and ``What makes them stand out``
    (trait tags joined with " \u00b7 "). Shows no z-scores, standardized values or
    clustering costs. A ``too_small`` or empty set yields an empty frame (with the
    standard columns) so the caller can skip it.
    """
    rows: list[dict[str, object]] = []
    if not persona_set.too_small:
        for persona in persona_set.personas:
            profile = persona.profile
            rows.append(
                {
                    "Persona": persona.name,
                    "Size": int(profile.size),
                    "Share": f"{profile.pct_of_leads:.1f}%",
                    "What makes them stand out": " \u00b7 ".join(
                        persona_trait_tags(profile)
                    ),
                }
            )
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)


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


# --------------------------------------------------------------------------- #
# Single-type warning and clustering-kind caption (Requirements 6.11, 6.12)   #
# --------------------------------------------------------------------------- #
SELECTION_NUMERIC = "numeric"
SELECTION_CATEGORICAL = "categorical"
SELECTION_MIXED = "mixed"
SELECTION_NONE = "none"

_NUMERIC_ONLY_WARNING = (
    "Only numeric attributes selected. Personas will be based on those alone. "
    "Adding a categorical attribute (such as marital status or a product owned) "
    "gives richer personas."
)
_CATEGORICAL_ONLY_WARNING = (
    "Only categorical attributes selected. Personas will be based on those alone. "
    "Adding a numeric attribute (such as years with the bank or spend) gives richer personas."
)


def selection_kind(selected: list[str], kinds: dict[str, str]) -> str:
    """Classify a selection as numeric / categorical / mixed / none (Req 6.11).

    ``kinds`` maps raw column -> ``"numeric"`` / ``"categorical"`` (the pipeline's
    own ``classify_types`` result). Selected columns missing from ``kinds`` are
    IGNORED for the decision; if no known column remains the result is ``none``.
    """
    known = [kinds[c] for c in selected if kinds.get(c) in ("numeric", "categorical")]
    if not known:
        return SELECTION_NONE
    if all(k == "numeric" for k in known):
        return SELECTION_NUMERIC
    if all(k == "categorical" for k in known):
        return SELECTION_CATEGORICAL
    return SELECTION_MIXED


def business_segment_field_options() -> list[str]:
    """Grouping fields offered at the business-segment level (Requirement 3.5).

    Only ``customer_dna.segment``. The Part 3 label is per client and per promo,
    so it is not offered.
    """
    return list(BUSINESS_SEGMENT_FIELD_OPTIONS)


def business_segment_field_for_level(level: str | None) -> str | None:
    """The grouping field a level uses: ``segment`` for business-segment, else None."""
    return BUSINESS_SEGMENT_FIELD if level == LEVEL_BUSINESS_SEGMENT else None


def effective_clustering_attributes(
    level: str | None,
    attributes: list[str],
    business_segment_field: str | None,
) -> list[str]:
    """Attributes the pipeline actually clusters on (mirrors the backend).

    At the ``business-segment`` and ``campaign`` levels the business-segment field
    is not a clustering feature, so it is dropped; level ``all`` is unchanged.
    """
    if level in (LEVEL_BUSINESS_SEGMENT, LEVEL_CAMPAIGN) and business_segment_field:
        return [c for c in attributes if c != business_segment_field]
    return list(attributes)


def single_type_warning(kind: str) -> str | None:
    """Non-blocking warning text for a single-type selection (Req 6.11)."""
    if kind == SELECTION_NUMERIC:
        return _NUMERIC_ONLY_WARNING
    if kind == SELECTION_CATEGORICAL:
        return _CATEGORICAL_ONLY_WARNING
    return None


def clustering_kind_caption(kind: str | None) -> str | None:
    """Caption shown with results of a single-type run (Req 6.12)."""
    if kind == SELECTION_NUMERIC:
        return "Clustered on numeric attributes only"
    if kind == SELECTION_CATEGORICAL:
        return "Clustered on categorical attributes only"
    return None


def group_lead_counts(joined: pd.DataFrame, group_columns: list[str]) -> dict[str, int]:
    """Count leads per group key using the pipeline's key convention.

    Mirrors ``part5_personas.grouping._combination_key``: one column -> ``str(value)``;
    several -> ``" | ".join(str(v) ...)`` in ``group_columns`` order. Rows with a
    null in any group column are dropped. Returns ``{}`` when there are no group
    columns, no data, or a column is missing. Pure (Requirement 6.10).
    """
    if joined is None or joined.empty or not group_columns:
        return {}
    if any(c not in joined.columns for c in group_columns):
        return {}
    sub = joined[list(group_columns)].dropna()
    counts: dict[str, int] = {}
    for values in sub.itertuples(index=False, name=None):
        key = " | ".join(str(v) for v in values)
        counts[key] = counts.get(key, 0) + 1
    return counts


def too_small_message(group_key: str, lead_count: int | None) -> str:
    """Return the actionable "too small to cluster" instruction (Requirement 6.10).

    States the group's lead count and tells the user how to proceed, rather than a
    bare status flag -- e.g. "This segment has only 12 leads. Pick a larger segment
    or combine segments." When ``lead_count`` is ``None`` the sentence carries no
    number. When ``group_key`` is empty (level ``all``) the message refers to
    "this audience" instead of a named segment.
    """
    where = f'"{group_key}"' if group_key else "this audience"
    if lead_count is None:
        return (
            f"{where} has too few leads to build personas. "
            "Pick a larger segment or combine segments, or lower the number of "
            "personas."
        )
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
# Group selector pure helpers (Requirements 3.16-3.19) -- no Streamlit         #
# --------------------------------------------------------------------------- #
ALL_GROUPS_LABEL = "All groups"
GROUP_SELECT_KEY = "persona_group_select"


def group_options(result: PersonaRunResult) -> list[str]:
    """Options for the group selector (Requirements 3.16, 3.18).

    The group keys of ``result.persona_sets`` in their existing order -- too-small
    groups included -- followed by :data:`ALL_GROUPS_LABEL`. Returns ``[]`` when the
    run has zero or one persona set (the selector is then not shown).
    """
    sets = list(result.persona_sets)
    if len(sets) <= 1:
        return []
    return [ps.group_key for ps in sets] + [ALL_GROUPS_LABEL]


def default_group(options: list[str]) -> str:
    """The default selection: the first group (Requirement 3.16)."""
    return options[0]


def _is_all_groups(selected: str | None) -> bool:
    return selected is None or selected == ALL_GROUPS_LABEL


def scope_result_to_group(result: PersonaRunResult, selected: str | None) -> PersonaRunResult:
    """Scope a run result to one group without altering any assignment (Req 3.17, 3.19).

    ``None`` / "All groups" returns ``result`` itself. Otherwise returns a NEW
    result holding only the persona set(s) whose ``group_key == selected`` and the
    ``labels`` rows of that group (index reset); ``joined_attributes`` is unchanged.
    The input is never mutated and no lead's persona label is changed.
    """
    if _is_all_groups(selected):
        return result
    sets = [ps for ps in result.persona_sets if ps.group_key == selected]
    labels = result.labels
    if labels is not None and GROUP_COLUMN in labels.columns:
        labels = labels[labels[GROUP_COLUMN] == selected].reset_index(drop=True)
    return replace(result, persona_sets=sets, labels=labels)


def scope_export_frame(frame: pd.DataFrame, selected: str | None) -> pd.DataFrame:
    """Rows of a download frame belonging to the selected group (Req 3.17).

    The frame is returned unchanged for "All groups" (or when it has no group
    column); otherwise only rows whose group equals ``selected`` are kept.
    """
    if _is_all_groups(selected) or GROUP_COLUMN not in frame.columns:
        return frame
    return frame[frame[GROUP_COLUMN] == selected].reset_index(drop=True)


def group_download_filename(base: str, selected: str | None) -> str:
    """CSV filename naming the group, e.g. ``campaign_leads_mid-market.csv`` (Req 3.17)."""
    if _is_all_groups(selected):
        return f"{base}.csv"
    slug = re.sub(r"[^a-z0-9]+", "-", str(selected).lower()).strip("-") or "group"
    return f"{base}_{slug}.csv"


def group_download_caption(selected: str | None, n_rows: int, kind: str = "leads") -> str:
    """Plain sentence stating what the download contains (Req 3.17, 3.18)."""
    if _is_all_groups(selected):
        return f"This file contains the {kind} from all groups ({n_rows:,} {kind})."
    if n_rows == 0:
        return (
            f'There are no personas to export for the "{selected}" group because it '
            "is too small to cluster."
        )
    return f'This file contains only the {n_rows:,} {kind} in the "{selected}" group.'


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
# {group_key: lead_count} for the last non-campaign run, used by the too-small
# message (Requirement 6.10). Empty for the campaign level.
PERSONA_GROUP_COUNTS_KEY = "persona_group_counts"
# The selection kind (numeric/categorical/mixed/none) of the run that produced the
# displayed results, used for the clustering-kind caption (Requirement 6.12).
PERSONA_KIND_KEY = "persona_clustering_kind"


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


_ATTRIBUTE_KINDS_FN = None


def _joined_attribute_kinds() -> dict[str, str]:
    """``{column: "numeric"|"categorical"}`` from the pipeline's ``classify_types``.

    Cached once (module singleton). Returns ``{}`` on any failure so the page shows
    no warning rather than a wrong one.
    """
    global _ATTRIBUTE_KINDS_FN
    if _ATTRIBUTE_KINDS_FN is None:
        import streamlit as st

        @st.cache_data(show_spinner=False)
        def _kinds() -> dict[str, str]:
            try:
                from part5_personas.config import Config
                from part5_personas.join import build_joined_attributes
                from part5_personas.preprocess import classify_types

                joined, _report = build_joined_attributes(Config())
                cols = [c for c in joined.columns if c != "client_id"]
                numeric, categorical = classify_types(joined, cols)
                out = {c: "numeric" for c in numeric}
                out.update({c: "categorical" for c in categorical})
                return out
            except Exception:  # noqa: BLE001 - no warning beats a wrong warning
                return {}

        _ATTRIBUTE_KINDS_FN = _kinds
    return _ATTRIBUTE_KINDS_FN()


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


def _load_part4_cards() -> list[dict]:
    """Read the Part 4 decision cards from ``outputs/cards.json`` (Requirement 7).

    Follows the path-resolution pattern of :func:`_available_promo_meta` (resolve
    ``outputs/cards.json`` relative to the app root) so the persona-mix layer can
    render **alongside** the existing Part 4 cards without touching any Part 4 code
    or ``app/main.py``. The returned card dicts are read only -- neither this page
    nor :func:`webapp_core.personas.persona_mix_by_cell` mutates them, keeping every
    Part 4 field byte-for-byte unchanged (Requirements 7.3, 7.4).

    Returns:
        The list of card dicts, or an empty list when the file is absent or
        unreadable (the caller then renders nothing rather than failing).
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    cards_path = root / "outputs" / "cards.json"
    try:
        with open(cards_path, encoding="utf-8") as fh:
            cards = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return cards if isinstance(cards, list) else []


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


def _group_lead_count(result: PersonaRunResult, group_key: str) -> int | None:
    """Best-effort lead count for a group, for the too-small message (Req 6.10).

    A too-small :class:`PersonaSet` carries no personas and no size. The count is
    read first from the per-group counts stored at run time
    (:data:`PERSONA_GROUP_COUNTS_KEY`, built by :func:`group_lead_counts`), then
    from the run's ``labels`` frame. Returns ``None`` when it cannot be determined
    (never a misleading 0). This is a display helper only.
    """
    try:
        import streamlit as st

        stored = st.session_state.get(PERSONA_GROUP_COUNTS_KEY) or {}
        if group_key in stored:
            return int(stored[group_key])
    except Exception:  # noqa: BLE001 - display helper must never crash
        pass

    labels = result.labels
    if (
        labels is not None
        and not labels.empty
        and GROUP_COLUMN in labels.columns
    ):
        count = int((labels[GROUP_COLUMN] == group_key).sum())
        if count:
            return count

    return None


# --------------------------------------------------------------------------- #
# How the Personas Differ comparison table (Requirement 6.4)                   #
# --------------------------------------------------------------------------- #
def _render_persona_comparison(result: PersonaRunResult) -> None:
    """Render the "How the Personas Differ" table, one per clustered set (Req 6.4).

    Uses only Streamlit built-ins (``st.dataframe``), so no new dependency is added
    (Requirement 9.9). ``too_small`` and empty sets are skipped.
    """
    import streamlit as st

    rendered_any = False
    for persona_set in result.persona_sets:
        frame = persona_comparison_frame(persona_set)
        if frame.empty:
            continue
        if not rendered_any:
            st.subheader("How the Personas Differ")
            st.caption(
                "Each row is one persona. The tags show what sets it apart from "
                "the others."
            )
            rendered_any = True
        if persona_set.group_key:
            st.markdown(f"**Segment: {persona_set.group_key}**")
        st.dataframe(frame, hide_index=True, use_container_width=True)


# --------------------------------------------------------------------------- #
# Persona mix on decision cards (Requirements 7.1, 7.2, 7.5) -- read-only      #
# --------------------------------------------------------------------------- #
def _persona_mix_badge_html(mix) -> str:
    """Build the (escaped) persona-mix badge HTML shown beside a card (Req 7.1, 7.2).

    Renders the :class:`webapp_core.personas.PersonaMix` for one cell as a visually
    distinct block of persona-name -> one-decimal-percentage chips, adjacent to the
    card's existing guidance and never overwriting, hiding, or reordering any card
    field (Requirement 7.2). Shares are shown to one decimal place and listed in
    descending share so the dominant persona reads first.

    When the mix is unavailable (``available == False``, Requirement 7.5) a muted
    "Persona context unavailable" chip is returned instead so the card still renders
    with its guidance intact. Reuses the ``pan-chip`` style (no new CSS classes).
    """
    label = (
        '<span style="color:var(--pan-gray);font-size:0.78rem;'
        'letter-spacing:0.2px;">Persona Mix</span><br/>'
    )
    if not getattr(mix, "available", False) or not getattr(mix, "shares", None):
        return (
            f'<div style="margin-top:4px;">{label}'
            '<span class="pan-chip">Persona context unavailable</span></div>'
        )

    ordered = sorted(mix.shares.items(), key=lambda kv: (-kv[1], kv[0]))
    chips = "".join(
        f'<span class="pan-chip">{html.escape(str(name))} {share:.1f}%</span>'
        for name, share in ordered
    )
    return f'<div style="margin-top:4px;">{label}{chips}</div>'


def _render_cards_with_mix(result: PersonaRunResult) -> None:
    """Render each Part 4 card read-only with its Persona_Mix adjacent (Req 7).

    Reads the Part 4 decision cards from ``outputs/cards.json`` (via
    :func:`_load_part4_cards`), computes the per-cell Persona_Mix with the already
    implemented :func:`webapp_core.personas.persona_mix_by_cell` from the run's
    ``labels`` and those cards, and renders each card **alongside** a persona-mix
    badge. Every Part 4 field is shown read-only exactly as laid out by Part 4's
    ``_decision_card_html`` field order (Action, Dominant Channel, Message Angle,
    Top Drivers, Exclusions By Reason) -- nothing is overwritten, hidden, or
    reordered (Requirements 7.2, 7.3, 7.4); this page renders a local read-only copy
    of those fields and never mutates a card.

    The unavailable-mix fallback (Requirement 7.5) is handled per card by
    :func:`_persona_mix_badge_html`, so a cell with no assignment still renders its
    guidance plus a "persona context unavailable" indication while the remaining
    cards render normally. No chart/plot dependency is involved here (Req 9.9).

    Does nothing when no cards are on disk, so a workspace without ``cards.json``
    simply omits this section rather than failing the page.
    """
    import streamlit as st
    import theme

    cards = _load_part4_cards()
    if not cards:
        return

    labels = result.labels
    try:
        mixes = persona_mix_by_cell(labels, cards)
    except Exception:  # noqa: BLE001 - never fail the page on a mix error (Req 7.5)
        mixes = {}

    st.subheader("Decision Cards With Persona Mix")
    st.caption(
        "Each card keeps its Part 4 guidance unchanged, with the persona mix of "
        "its leads shown alongside."
    )

    for i in range(0, len(cards), 2):
        pair = cards[i : i + 2]
        cols = st.columns(2)
        for col, card in zip(cols, pair):
            with col:
                promo_id = str(card.get("promo_id", "--"))
                segment = str(card.get("segment", "--"))
                mix = mixes.get((promo_id, segment))
                if mix is None:
                    # No mix entry for this card -> treat as unavailable (Req 7.5).
                    mix = PersonaMix(
                        promo_id=promo_id,
                        segment=segment,
                        shares={},
                        available=False,
                    )
                body = _part4_card_readonly_html(card) + _persona_mix_badge_html(mix)
                theme.card(f"{promo_id} -- {segment}", body)


def _part4_card_readonly_html(card: dict) -> str:
    """Build the read-only body HTML for one Part 4 card (Requirements 7.2-7.4).

    A local, read-only render of the Part 4 card fields in the **same field order**
    as ``app/main.py``'s ``_decision_card_html`` (Action, Dominant Channel, Message
    Angle, Top Drivers, Exclusions By Reason, plus the Joiners / 90% / Value stat
    chips). It only *reads* ``card`` values -- it never edits, hides, or reorders a
    field -- so every Part 4 value stays byte-for-byte unchanged (Requirements 7.2,
    7.3, 7.4). This is intentionally separate from ``main.py`` so no Part 4 code and
    no existing tab is touched; we render alongside, not in place.
    """
    action = html.escape(str(card.get("action", "--")))
    channel = html.escape(str(card.get("dominant_channel", "--")))
    angle = html.escape(str(card.get("message_angle", "--")))

    joiners = float(card.get("expected_joiners", 0.0) or 0.0)
    low = float(card.get("joiners_90_low", 0.0) or 0.0)
    high = float(card.get("joiners_90_high", 0.0) or 0.0)
    exp_value = float(card.get("expected_value", 0.0) or 0.0)

    drivers = card.get("top_drivers") or []
    drivers_html = ", ".join(html.escape(str(d)) for d in drivers) or "--"

    excluded = card.get("excluded_by_reason") or {}
    if excluded:
        exclusions_html = ", ".join(
            f"{html.escape(str(reason))}: {int(count):,}"
            for reason, count in excluded.items()
        )
    else:
        exclusions_html = "none"

    chips = (
        f'<span class="pan-chip">Joiners {joiners:,.1f}</span>'
        f'<span class="pan-chip">90% {low:,.1f}-{high:,.1f}</span>'
        f'<span class="pan-chip">Value {exp_value:,.0f}</span>'
    )

    rows = [
        ("Action", action),
        ("Dominant Channel", channel),
        ("Message Angle", angle),
        ("Top Drivers", drivers_html),
        ("Exclusions By Reason", exclusions_html),
    ]
    items = "".join(
        f'<div style="margin-bottom:8px;">'
        f'<span style="color:var(--pan-gray);font-size:0.78rem;'
        f'letter-spacing:0.2px;">{label}</span><br/>'
        f'<span style="font-weight:600;color:var(--pan-charcoal);">{value}</span>'
        "</div>"
        for label, value in rows
    )
    return f'<div style="margin-bottom:12px;">{chips}</div>{items}'


def _render_downloads(selected_group: str | None = None) -> None:
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

    # Scope both files to the selected group (Requirement 3.17); All groups = full.
    campaign_frame = scope_export_frame(exports.campaign_leads, selected_group)
    labeled_frame = scope_export_frame(exports.labeled_leads, selected_group)
    campaign_bytes = campaign_frame.to_csv(index=False).encode("utf-8")
    full_bytes = labeled_frame.to_csv(index=False).encode("utf-8")
    with dl_cols[0]:
        st.download_button(
            f"Download Campaign Leads ({len(campaign_frame):,})",
            data=campaign_bytes,
            file_name=group_download_filename("campaign_leads", selected_group),
            mime="text/csv",
            disabled=campaign_frame.empty,
            key="persona_dl_campaign",
            help=(
                "The CRM-ready list: client id, persona, group, best channel, "
                "join probability, and control flag."
            ),
        )
    with dl_cols[1]:
        st.download_button(
            f"Download Full Labeled Leads ({len(labeled_frame):,}, optional)",
            data=full_bytes,
            file_name=group_download_filename("persona_labeled_leads", selected_group),
            mime="text/csv",
            disabled=labeled_frame.empty,
            key="persona_dl_full",
            help="The full list with every joined attribute, for deeper analysis.",
        )
    st.caption(group_download_caption(selected_group, len(campaign_frame), "leads"))


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
       **Number of personas** k selector (2-6, default 3), and -- at the campaign
       level -- the **campaign pool** selector; the "By customer segment" level
       groups by ``customer_dna.segment`` directly with no field picker
       (Requirements 3.4, 3.5, 5.1-5.3, 6.1);
    2. the grouped **Attribute_Picker** with readable labels and a preselected
       Default_Attribute_Set (Requirements 3.1, 3.13);
    3. the optional **two-step** control "Split by ... first ..." (Requirement 3.8);
    4. a **Run** control that validates the config (Requirement 6.2), runs the
       cached backend, and stashes the result + exports in session state;
    5. one **summary card** per persona (Requirement 6.3) with the too-small
       instruction for flagged groups (Requirement 6.10);
    6. after a successful run, the **"How the Personas Differ" table**
       (``st.dataframe`` of plain trait tags, Requirement 6.4), and the existing Part 4
       **cards with their Persona_Mix** badge, unavailable fallback included
       (Requirements 7.1, 7.2, 7.5); the Elbow_Plot is not shown on the page
       (revised Requirement 6.5); and
    7. the two **download** controls, default Campaign_Leads_Export + optional full
       Persona_Labeled_Leads, disabled until a run completes (Requirements 8.8-8.10).

    All clustering/profiling is delegated to the cached
    :func:`webapp_core.personas.run_personas`; this function only wires widgets and
    session state (Requirement 6.9). The task-14.2 comparison table and on-card persona mix
    use Streamlit built-ins only, adding no dependency (Requirement 9.9).

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
            key="persona_level_select",
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
                key="persona_k_input",
                help="Between 2 and 6. Start at 3 and adjust.",
            )
        )

    business_segment_field: str | None = None
    campaign_pool: str | None = None

    if level == LEVEL_BUSINESS_SEGMENT:
        # Group by customer_dna.segment directly; no picker (Requirements 3.5, 3.20).
        business_segment_field = business_segment_field_for_level(level)

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
        key="persona_two_step",
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

    # --- single-type warning (Requirement 6.11): non-blocking, above Run ---
    _warning = single_type_warning(
        selection_kind(
            effective_clustering_attributes(
                level, selected_attributes, business_segment_field
            ),
            _joined_attribute_kinds(),
        )
    )
    if _warning is not None:
        st.warning(_warning)

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

    # --- results: summary cards + charts + cards-with-mix + downloads ---
    # Everything below persists across reruns and is gated on a run result
    # existing in the session (task 14.2: the charts and the on-card persona mix
    # render only after a successful persona run).
    result: PersonaRunResult | None = st.session_state.get(PERSONA_RESULT_KEY)
    selected_group: str | None = None
    if result is not None:
        # Group selector (Requirements 3.16-3.19): shown only when the run yields
        # more than one group. Filters already-computed data -- never refits.
        options = group_options(result)
        if options:
            if st.session_state.get(GROUP_SELECT_KEY) not in options:
                st.session_state[GROUP_SELECT_KEY] = default_group(options)
            selected_group = st.selectbox(
                "Show group",
                options,
                index=options.index(st.session_state[GROUP_SELECT_KEY]),
                key=GROUP_SELECT_KEY,
                help="Show the personas, comparison, decision cards and download "
                "for one group, or all groups together.",
            )
        scoped = scope_result_to_group(result, selected_group)

        st.subheader("Personas")
        _caption = clustering_kind_caption(st.session_state.get(PERSONA_KIND_KEY))
        if _caption is not None:
            st.caption(_caption)
        _render_summary_cards(scoped)
        # How the Personas Differ comparison table (Requirement 6.4).
        _render_persona_comparison(scoped)
        # Existing Part 4 cards rendered read-only with the Persona_Mix badge
        # adjacent, with the unavailable fallback (Requirements 7.1, 7.2, 7.5).
        _render_cards_with_mix(scoped)

    _render_downloads(selected_group)


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
        except InvalidSegmentFieldError as exc:
            st.error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - surface any backend halt as a message
            st.error(f"Could not build personas: {exc}")
            return

    st.session_state[PERSONA_RESULT_KEY] = result
    st.session_state[PERSONA_EXPORTS_KEY] = exports
    st.session_state[PERSONA_KIND_KEY] = selection_kind(
        effective_clustering_attributes(level, attributes, business_segment_field),
        _joined_attribute_kinds(),
    )

    # Per-group lead counts for the too-small message (Req 6.10). Campaign-level
    # membership is restricted by the pool, so no count is derived there.
    group_counts: dict[str, int] = {}
    if level != LEVEL_CAMPAIGN:
        if level == LEVEL_BUSINESS_SEGMENT:
            group_columns = [business_segment_field] if business_segment_field else []
        else:
            group_columns = list(grouping_attributes or [])
        try:
            group_counts = group_lead_counts(result.joined_attributes, group_columns)
        except Exception:  # noqa: BLE001 - display helper must never block a run
            group_counts = {}
    st.session_state[PERSONA_GROUP_COUNTS_KEY] = group_counts

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
