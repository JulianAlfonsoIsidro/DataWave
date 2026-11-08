"""Upload Campaign File panel for the New Promo tab (Part 7, task 8.5).

Presentation and session-state wiring only. The real work lives in
``ai.extractor``: :func:`extract_text` reads the PDF or DOCX locally and
:func:`extract_campaign` returns validated, tagged Campaign_Fields.

Flow (design section 12, Requirements 2.1, 2.3, 2.9, 2.11, 2.12, 2.13, 1.7):

- The panel runs *before* the Fill In Details widgets are created in the same
  script run, so prefilled values are written to the widget keys in session
  state first (Requirement 2.9).
- A failed upload shows a specific error (type, size, unreadable, or empty)
  and leaves every form value and earlier extraction untouched (2.3).
- Every Campaign_Field carries a Field_Tag, "Found in Document" or "Needs
  Input" (2.11), shown as a caption under the field by :func:`field_tag`.
- The document text, context, and tags are stored in session state for the
  assistant, replacing any earlier upload (2.13).
- Nothing here runs the analysis (2.12). The user presses Run Analysis.
- The Demo Mode badge appears when the extraction used the Mock (1.7).
"""

from __future__ import annotations

import streamlit as st

import theme
from ai.extractor import (
    FOUND,
    ExtractionResult,
    UploadError,
    extract_campaign,
    extract_text,
)
from webapp_core.threshold import THRESHOLD_SPECS, ThresholdType

UPLOAD_TAB_LABEL = "Upload Campaign File"
FORM_TAB_LABEL = "Fill In Details"

# Widget keys of the Fill In Details form (written by the prefill).
THRESHOLD_TYPE_KEY = "threshold_type_select"
PRODUCT_TYPE_KEY = "new_promo_product_type"
MECHANIC_KEY = "new_promo_mechanic"
REWARD_KEY = "new_promo_reward"
MIN_ADB_KEY = "new_promo_min_adb"
SEGMENTS_KEY = "new_promo_eligible_segments"
CHANNELS_KEY = "new_promo_channels"


def threshold_value_key(threshold_type: ThresholdType) -> str:
    """The slider key for a threshold type (matches ``app/main.py``)."""
    return f"threshold_value_{threshold_type.name}"


# Session keys the assistant page reads (Requirement 2.13).
DOCUMENT_TEXT_KEY = "campaign_document_text"
CONTEXT_KEY = "campaign_context"
TAGS_KEY = "campaign_field_tags"
EXTRACTION_MODE_KEY = "campaign_extraction_mode"

_UPLOAD_SIGNATURE_KEY = "upload_signature"
_UPLOAD_ERROR_KEY = "upload_error"
_UPLOAD_SUMMARY_KEY = "upload_summary"

UPLOAD_ERROR_MESSAGES = {
    "type": "This file type is not supported. Upload a PDF or DOCX file.",
    "size": "This file is larger than 10 MB. Upload a smaller PDF or DOCX file.",
    "unreadable": (
        "This file could not be read. It may be corrupt or password protected. "
        "Upload a different PDF or DOCX file."
    ),
    "empty": (
        "This file has no readable text. Upload a PDF or DOCX file that "
        "contains text."
    ),
}


def _snap(threshold_type: ThresholdType, value: float):
    """Clamp and snap a value to the slider's range and step grid."""
    spec = THRESHOLD_SPECS[threshold_type]
    clamped = min(max(float(value), spec.minimum), spec.maximum)
    steps = round((clamped - spec.minimum) / spec.step)
    snapped = min(spec.minimum + steps * spec.step, spec.maximum)
    return type(spec.minimum)(snapped)


def ensure_form_defaults(
    segment_options: list[str],
    product_options: list[str],
    mechanic_options: list[str],
    channel_options: list[str],
) -> None:
    """Seed the form's widget keys once so widgets need no default argument."""
    state = st.session_state
    state.setdefault(PRODUCT_TYPE_KEY, product_options[0])
    state.setdefault(MECHANIC_KEY, mechanic_options[0])
    state.setdefault(REWARD_KEY, "Bonus interest")
    state.setdefault(MIN_ADB_KEY, 0.0)
    state.setdefault(SEGMENTS_KEY, list(segment_options))
    state.setdefault(CHANNELS_KEY, list(channel_options))


def apply_prefill(
    result: ExtractionResult,
    *,
    segment_options: list[str],
    product_options: list[str],
    mechanic_options: list[str],
    channel_options: list[str],
) -> None:
    """Write found fields to the widget keys (call before widgets exist)."""
    fields = result.fields
    state = st.session_state

    if fields.get("product_type") in product_options:
        state[PRODUCT_TYPE_KEY] = fields["product_type"]
    if fields.get("mechanic") in mechanic_options:
        state[MECHANIC_KEY] = fields["mechanic"]
    if "reward" in fields:
        state[REWARD_KEY] = str(fields["reward"])
    if "min_adb" in fields:
        state[MIN_ADB_KEY] = float(fields["min_adb"])
    if "eligible_segments" in fields:
        chosen = [s for s in fields["eligible_segments"] if s in segment_options]
        if chosen:
            state[SEGMENTS_KEY] = chosen
    if "channels" in fields:
        chosen = [c for c in fields["channels"] if c in channel_options]
        if chosen:
            state[CHANNELS_KEY] = chosen

    if "threshold_type" in fields:
        ttype = ThresholdType(fields["threshold_type"])
        state[THRESHOLD_TYPE_KEY] = ttype
        if "threshold_value" in fields:
            state[threshold_value_key(ttype)] = _snap(ttype, fields["threshold_value"])

    # Replace any earlier upload for the assistant (Requirement 2.13).
    state[DOCUMENT_TEXT_KEY] = result.document_text
    state[CONTEXT_KEY] = dict(result.context)
    state[TAGS_KEY] = dict(result.tags)
    state[EXTRACTION_MODE_KEY] = result.mode


def field_tag(*names: str) -> None:
    """Caption the Field_Tag under a field; nothing before an upload.

    With several names (the threshold type and value) the field counts as
    found only when every name was found.
    """
    tags = st.session_state.get(TAGS_KEY)
    if not tags:
        return
    found = all(tags.get(name) == FOUND for name in names)
    st.caption(FOUND if found else "Needs Input")


def _process(data: bytes, filename: str, **options) -> None:
    """Extract and prefill, or record the specific error and change nothing."""
    st.session_state[_UPLOAD_ERROR_KEY] = None
    try:
        text = extract_text(data, filename)
    except UploadError as exc:
        st.session_state[_UPLOAD_ERROR_KEY] = UPLOAD_ERROR_MESSAGES.get(
            exc.cause, UPLOAD_ERROR_MESSAGES["unreadable"]
        )
        return
    with st.spinner("Reading the campaign file..."):
        result = extract_campaign(text)
    apply_prefill(result, **options)
    found = sum(1 for tag in result.tags.values() if tag == FOUND)
    st.session_state[_UPLOAD_SUMMARY_KEY] = (
        f"Found {found} of {len(result.tags)} fields in {filename}. "
        f"Open the {FORM_TAB_LABEL} tab to review them, then press Run Analysis."
    )


def render_upload_panel(
    *,
    segment_options: list[str],
    product_options: list[str],
    mechanic_options: list[str],
    channel_options: list[str],
) -> None:
    """Render the Upload Campaign File tab body."""
    st.subheader("Upload A Campaign Proposal")
    st.caption(
        "Upload a PDF or DOCX file up to 10 MB. Details found in the file "
        f"prefill the {FORM_TAB_LABEL} tab. Nothing runs until you press Run Analysis."
    )
    uploaded = st.file_uploader(
        "Campaign File",
        type=["pdf", "docx"],
        accept_multiple_files=False,
        key="campaign_file_upload",
    )

    if uploaded is not None:
        signature = (uploaded.name, uploaded.size)
        if st.session_state.get(_UPLOAD_SIGNATURE_KEY) != signature:
            st.session_state[_UPLOAD_SIGNATURE_KEY] = signature
            _process(
                uploaded.getvalue(),
                uploaded.name,
                segment_options=segment_options,
                product_options=product_options,
                mechanic_options=mechanic_options,
                channel_options=channel_options,
            )
    else:
        st.session_state.pop(_UPLOAD_SIGNATURE_KEY, None)
        st.session_state.pop(_UPLOAD_ERROR_KEY, None)

    error = st.session_state.get(_UPLOAD_ERROR_KEY)
    if error:
        st.error(error)
    elif uploaded is not None and st.session_state.get(_UPLOAD_SUMMARY_KEY):
        st.success(st.session_state[_UPLOAD_SUMMARY_KEY])

    if st.session_state.get(EXTRACTION_MODE_KEY) == "Demo":
        theme.st_markdown(theme.badge_html("Demo Mode", "warning"))
        st.caption(
            "Details were read with built-in rules because the AI service "
            "was not available."
        )
