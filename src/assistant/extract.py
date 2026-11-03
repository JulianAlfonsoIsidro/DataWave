"""Upload field-extraction pipeline: channel mapping, validation, and extract_form."""

from __future__ import annotations

import math
from typing import Any

from assistant.models import FieldDraft, FormDraft, Mode

# Promo form option lists -- kept identical to app/main.py so a value the form
# cannot offer is never marked "found" (Requirement 7.4).
PRODUCT_TYPE_OPTIONS: list[str] = ["Savings", "Time Deposit", "Investment", "Credit Card"]
MECHANIC_OPTIONS: list[str] = ["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE", "OTHER"]

# The three exact labels Part 4 understands. Any other spelling makes leads
# unreachable, so channel candidates are mapped onto exactly these (Req 7.6).
ALLOWED_CHANNEL_LABELS: list[str] = ["In-app", "Email", "SMS"]

# Normalized channel synonym -> Allowed_Channel_Label. Keys are lowercase and
# stripped; map_channel normalizes the input the same way before lookup.
CHANNEL_MAP: dict[str, str] = {
    "in-app": "In-app",
    "inapp": "In-app",
    "app": "In-app",
    "push": "In-app",
    "notification": "In-app",
    "email": "Email",
    "e-mail": "Email",
    "sms": "SMS",
    "text": "SMS",
    "message": "SMS",
}


def map_channel(name: Any) -> str | None:
    """Map a raw channel name to exactly one Allowed_Channel_Label.

    Normalizes case and surrounding whitespace, then resolves common synonyms:
    `in-app / inapp / app / push / notification -> "In-app"`,
    `email / e-mail -> "Email"`, `sms / text / message -> "SMS"`.
    Returns None for anything unmappable so the caller can drop it (Req 7.6).
    """
    if not isinstance(name, str):
        return None
    key = name.strip().lower()
    return CHANNEL_MAP.get(key)


def _coerce_number(value: Any) -> float | None:
    """Return a finite number >= 0 for int/float or numeric strings, else None.

    Booleans are rejected (a bool is an int subclass but never a valid amount).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _draft_product_type(value: Any) -> FieldDraft:
    if isinstance(value, str) and value in PRODUCT_TYPE_OPTIONS:
        return FieldDraft(value=value, status="found")
    return FieldDraft(value=PRODUCT_TYPE_OPTIONS[0], status="needs_input")


def _draft_mechanic(value: Any) -> FieldDraft:
    if isinstance(value, str) and value in MECHANIC_OPTIONS:
        return FieldDraft(value=value, status="found")
    return FieldDraft(value=MECHANIC_OPTIONS[0], status="needs_input")


def _draft_number(value: Any) -> FieldDraft:
    number = _coerce_number(value)
    if number is None:
        return FieldDraft(value=0.0, status="needs_input")
    return FieldDraft(value=number, status="found")


def _draft_reward(value: Any) -> FieldDraft:
    if isinstance(value, str) and value.strip():
        return FieldDraft(value=value, status="found")
    return FieldDraft(value="", status="needs_input")


def _draft_segments(value: Any, segment_options: list[str]) -> FieldDraft:
    if isinstance(value, (list, tuple)):
        # Keep only recognized segments, in option order, without duplicates.
        kept = [seg for seg in segment_options if seg in value]
        if kept:
            return FieldDraft(value=kept, status="found")
    return FieldDraft(value=[], status="needs_input")


def _draft_channels(value: Any) -> FieldDraft:
    if isinstance(value, (list, tuple)):
        kept: list[str] = []
        for raw in value:
            label = map_channel(raw)
            if label is not None and label not in kept:
                kept.append(label)
        if kept:
            return FieldDraft(value=kept, status="found")
    return FieldDraft(value=[], status="needs_input")


def validate_fields(
    candidates: dict[str, Any],
    segment_options: list[str],
    mode: Mode = "mock",
) -> FormDraft:
    """Build the seven FieldDrafts from raw candidate values, dropping anything
    invalid to `needs_input` with a safe default (Requirements 7.4, 7.6, 7.7).

    A value survives as `found` only when it is in its allowed set:
    `product_type`/`mechanic` in their option lists, `threshold_php`/`min_adb`
    finite numbers >= 0, `reward` a non-empty string, `eligible_segments` a
    non-empty subset of `segment_options`, and `channels` a non-empty mapped
    subset of the three Allowed_Channel_Labels. No invalid value is ever
    marked `found`. The same validator runs for both the Bedrock and Mock
    paths so a driver can never inject a bad value.
    """
    get = candidates.get
    return FormDraft(
        product_type=_draft_product_type(get("product_type")),
        mechanic=_draft_mechanic(get("mechanic")),
        threshold_php=_draft_number(get("threshold_php")),
        reward=_draft_reward(get("reward")),
        eligible_segments=_draft_segments(get("eligible_segments"), segment_options),
        min_adb=_draft_number(get("min_adb")),
        channels=_draft_channels(get("channels")),
        mode=mode,
    )


def extract_form(
    file_bytes: bytes,
    filename: str,
    segment_options: list[str],
) -> FormDraft:
    """Run one campaign-file upload end to end and return a :class:`FormDraft`.

    Extracts Campaign_Text locally, then asks Bedrock for strict JSON when
    credentials are usable (falling back to the Mock rule extractor on any
    Bedrock error) or uses the Mock rules directly when credentials are absent,
    validates every candidate field, and returns a :class:`FormDraft` tagged
    with the ``mode`` actually used. It never starts a run — only a
    :class:`FormDraft` is produced (Requirements 7.3, 7.4, 7.5, 7.6, 7.7, 7.8).

    Args:
        file_bytes: The raw bytes of the uploaded PDF or DOCX.
        filename: The uploaded file's name (its extension selects the reader).
        segment_options: The distinct Customer_DNA segment names the form offers;
            extracted segments are validated against this list.

    Returns:
        FormDraft: The seven validated ``FieldDraft`` fields plus the ``mode``.

    Raises:
        assistant.doc_text.UnsupportedFile: If ``filename`` is not .pdf/.docx
            (the UI restricts types, so this is a direct-call backstop).
    """
    # Local imports keep boto3 off the import path and avoid an import cycle
    # between this module and the drivers.
    from assistant import bedrock_driver, doc_text, mock_driver
    from assistant.config import load_model_config

    campaign_text = doc_text.extract_text(file_bytes, filename)
    cfg = load_model_config()

    mode: Mode = "mock"
    candidates: dict[str, Any]
    if cfg.is_usable:
        try:
            candidates = bedrock_driver.extract_fields_json(campaign_text, cfg)
            mode = "bedrock"
        except Exception:
            # Any Bedrock/parse error degrades to the offline Mock rules (Req 7.5).
            candidates = mock_driver.extract_fields_rules(campaign_text)
            mode = "mock"
    else:
        candidates = mock_driver.extract_fields_rules(campaign_text)
        mode = "mock"

    return validate_fields(candidates, segment_options, mode)
