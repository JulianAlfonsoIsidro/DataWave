"""Shared plain-language attribute labels for the Persona_Pipeline.

The single, canonical raw-column -> business-label map for Joined_Attribute_Set
columns. It lives in the pure pipeline so **both** the Streamlit
``Persona_Page`` (``app/persona_page.py``) and the pure naming stage
(``part5_personas.naming``) read the same labels without the pipeline importing
anything under ``app/`` (the layering rule: ``app/`` may import the pipeline, the
pipeline may never import ``app/``).

This module carries only the label *text* (the raw-column -> plain-label
mapping, the ``owns_*`` rule, and a title-cased fallback). The
Attribute_Group / theme bucketing stays in ``app/persona_page.py`` (a
presentation concern); only :func:`attribute_label` is shared here.

The labels mirror the business phrasing a CRM manager expects (Requirement 3.1):
``owns_deposit`` -> "deposit account", ``total_out`` -> "total outflows",
``digital_app_user`` -> "app users", etc. :func:`attribute_label` is a pure,
deterministic function of its input (Requirement 4.6).
"""

from __future__ import annotations

# The ``owns_<product_type>`` prefix produced by the join pivot (Requirement 1.2).
_OWNERSHIP_PREFIX = "owns_"

# Canonical raw-column -> plain business label for the known Joined_Attribute_Set
# columns (customer_dna + features_part2). Labels are lower-cased noun phrases so
# they compose naturally both inside a persona name ("High total outflows") and in
# the Attribute_Picker (title-cased by the caller). ``owns_*`` flags and unmapped
# columns are handled by :func:`attribute_label` directly.
_ATTRIBUTE_LABELS: dict[str, str] = {
    # --- Demographics (customer_dna profile fields) ---
    "segment": "customer segment",
    "age_band": "age band",
    "tenure_years": "years with the bank",
    "region": "region",
    "sec_class": "socio-economic class",
    "email_valid": "valid-email holders",
    "mobile_valid": "valid-mobile holders",
    # --- Lifestyle (behaviour-flavoured profile fields) ---
    "inflow_type": "main money-in type",
    "digital_app_user": "app users",
    "online_shopper": "online shoppers",
    "frugal_flag": "frugal spenders",
    "investment_propensity_decile": "investment appetite",
    # --- Spending behavior (features_part2 behavioural features) ---
    "total_out": "total outflows",
    "out_other_bank": "outflows to other banks",
    "ext_outflow_ratio": "share of outflows leaving the bank",
    "months_with_ext_transfer": "months sending money out",
    "inflow_share_payroll": "payroll income",
    "inflow_share_remittance": "remittance income",
    "inflow_share_business_receipts": "business income",
    "spend_share_bank_transfer": "bank-transfer spend",
    "spend_share_e_commerce": "e-commerce spend",
    "spend_share_education": "education spend",
    "spend_share_fuel": "fuel spend",
    "spend_share_grocery": "grocery spend",
    "spend_share_health": "health spend",
    "spend_share_insurance_premium": "insurance spend",
    "spend_share_p2p_transfer": "peer-transfer spend",
    "spend_share_restaurants": "restaurant spend",
    "spend_share_retail": "retail spend",
    "spend_share_telco": "telco spend",
    "spend_share_travel": "travel spend",
    "spend_share_utilities": "utilities spend",
}


# Known 0/1 flag columns (besides the ``owns_*`` family). Although integer-typed,
# they are boolean in meaning, so persona names read "More/Fewer <label>" for them
# rather than "High/Low".
_FLAG_COLUMNS: frozenset[str] = frozenset(
    {"digital_app_user", "online_shopper", "frugal_flag", "email_valid", "mobile_valid"}
)


def is_flag_attribute(raw_column: str) -> bool:
    """Return True for boolean/flag-style columns (``owns_*`` and known 0/1 flags).

    Pure and deterministic (Requirement 4.6).
    """
    return raw_column.startswith(_OWNERSHIP_PREFIX) or raw_column in _FLAG_COLUMNS


def attribute_label(raw_column: str) -> str:
    """Return the plain business label for a raw Joined_Attribute_Set column.

    A pure, deterministic mapping (Requirement 4.6) shared by the naming stage and
    the Attribute_Picker so both speak the same business language. Resolution
    order:

    1. an ``owns_<type>`` ownership flag -> ``"<type> account"`` (so
       ``owns_deposit`` reads "deposit account", ``owns_credit_card`` reads
       "credit card account");
    2. an explicit entry in :data:`_ATTRIBUTE_LABELS`;
    3. graceful fallback -- the raw column with underscores turned into spaces,
       lower-cased, so an unmapped column still reads cleanly.

    The returned label is a lower-cased noun phrase; callers title-case it for
    display where needed.

    Args:
        raw_column: The raw Joined_Attribute_Set column name.

    Returns:
        A plain-language label for ``raw_column``.
    """
    if raw_column.startswith(_OWNERSHIP_PREFIX):
        product = raw_column[len(_OWNERSHIP_PREFIX) :].replace("_", " ").strip()
        return f"{product} account" if product else "product account"

    if raw_column in _ATTRIBUTE_LABELS:
        return _ATTRIBUTE_LABELS[raw_column]

    return raw_column.replace("_", " ").strip().lower()


# Category wording for non-flag text categoricals (task 8.1g, Requirements 4.4, 4.6):
# column -> template with a ``{c}`` placeholder for the category. Any other text
# column reads "<Label>: <c>". Shared so names stay consistent across the pipeline.
_CATEGORY_TEMPLATES: dict[str, str] = {
    "age_band": "{c} Age Band",
    "region": "{c} Region",
    "segment": "{c} Segment",
    "sec_class": "Class {c}",
    "inflow_type": "{c} Inflows",
    "online_shopper": "{c} Online Shoppers",
}


def is_text_category(raw_column: str, categories: list[str]) -> bool:
    """Return True when ``raw_column`` is a non-flag text categorical.

    ``owns_*`` columns are always flags. Any other column is a text categorical
    unless its observed categories are all within ``{"0", "1"}`` (a yes/no flag,
    for example ``digital_app_user``). ``online_shopper`` holds text levels
    (High / Medium / Low), so it counts as text when its categories are not 0/1.
    Pure and deterministic (Requirement 4.6).
    """
    if raw_column.startswith(_OWNERSHIP_PREFIX):
        return False
    cats = {str(c) for c in categories}
    if not cats or cats <= {"0", "1"}:
        return False
    return True


def category_phrase(raw_column: str, category: str) -> str:
    """Return the plain phrase naming ``category`` of a text column (task 8.1g).

    For example ``("age_band", "25-34")`` -> "25-34 Age Band", ``("sec_class",
    "C1")`` -> "Class C1"; an unmapped column reads "<Label>: <category>". Pure
    and deterministic (Requirement 4.6).
    """
    template = _CATEGORY_TEMPLATES.get(raw_column)
    if template is not None:
        return template.format(c=category)
    return f"{attribute_label(raw_column).title()}: {category}"
