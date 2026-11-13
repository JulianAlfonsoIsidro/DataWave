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
- The Demo Mode label appears when the extraction used the Mock (1.7).

Part 9 round 3 (spec part9-layout-fixes, Requirements 32, 33, 37):

- The file is read on this computer first. Phone numbers, email addresses
  and long digit strings are masked, and the page says how many.
- Nothing is sent to Bedrock until the user presses "Fill Form with Bedrock"
  (with the Bedrock icon). "Fill Form with Built-in Rules" never sends.
- The Bedrock notice, the wait line, an "AI-generated" tag on fields read by
  Bedrock, and the token line follow the shared AI drawers (``ai_ui``).
"""

from __future__ import annotations


import streamlit as st

import ai_ui
import theme
from ai.extractor import (
    FOUND,
    ExtractionResult,
    UploadError,
    estimated_input_tokens,
    extract_campaign,
    extract_text,
)
from ai.privacy import mask_pii, masked_note
from webapp_core import ai_usage
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
# Round 3: the file's masked text waits here until the user chooses how to read it.
_PENDING_KEY = "upload_pending"
_UPLOAD_USAGE_KEY = "upload_usage"

DOES_LINE = (
    "Here the AI reads your file and fills in the form for you to check. It never "
    "produces or changes a number in the results: scoring is the prediction model, "
    "and built-in rules read the file when the AI is not used."
)
PRIVACY_NOTE = (
    "The file was read on this computer. Only the masked text is sent, and only "
    "when you choose Fill Form with Bedrock."
)
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
    if found and st.session_state.get(EXTRACTION_MODE_KEY) == "Bedrock":
        # Round 3 (Requirement 32.4): a field read by Bedrock is tagged.
        theme.st_markdown(
            f'<div class="pan-ai-meta"><span class="pan-token-line">{FOUND}</span>'
            f"{theme.ai_tag_html()}</div>"
        )
        return
    st.caption(FOUND if found else "Needs Input")


def _read_locally(data: bytes, filename: str) -> None:
    """Read the file on this computer and mask it; send nothing yet.

    A failure records the specific error and changes nothing (2.3).
    """
    st.session_state[_UPLOAD_ERROR_KEY] = None
    st.session_state.pop(_UPLOAD_SUMMARY_KEY, None)
    try:
        text = extract_text(data, filename)
    except UploadError as exc:
        st.session_state[_UPLOAD_ERROR_KEY] = UPLOAD_ERROR_MESSAGES.get(
            exc.cause, UPLOAD_ERROR_MESSAGES["unreadable"]
        )
        st.session_state.pop(_PENDING_KEY, None)
        return
    masked = mask_pii(text)
    st.session_state[_PENDING_KEY] = {
        "text": masked.text, "filename": filename, "note": masked_note(masked),
    }


def _fill(use_bedrock: bool, slot, **options) -> None:
    """Read the masked text with Bedrock or the built-in rules, then prefill."""
    pending = st.session_state.get(_PENDING_KEY) or {}
    text = pending.get("text", "")
    allowed, off_reason = ai_ui.can_call()
    use_ai = use_bedrock and allowed
    if use_ai:
        slot.markdown(ai_ui.wait_html(estimated_input_tokens(text)), unsafe_allow_html=True)
    result = extract_campaign(
        text, use_ai=use_ai, off_reason=off_reason if use_bedrock else "builtin_choice",
    )
    slot.empty()
    rec = ai_ui.record(ai_usage.record_from(
        ai_usage.FEATURE_UPLOAD, result.mode, result.usage, result.seconds, result.reason,
    ))
    st.session_state[_UPLOAD_USAGE_KEY] = rec.as_dict()
    apply_prefill(result, **options)
    found = sum(1 for tag in result.tags.values() if tag == FOUND)
    st.session_state[_UPLOAD_SUMMARY_KEY] = (
        f"Found {found} of {len(result.tags)} fields in {pending.get('filename', 'the file')}. "
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
    ai_ui.notice("bedrock", DOES_LINE, chips=True)
    uploaded = st.file_uploader(
        "Campaign File",
        type=["pdf", "docx"],
        accept_multiple_files=False,
        key="campaign_file_upload",
    )

    options = dict(
        segment_options=segment_options,
        product_options=product_options,
        mechanic_options=mechanic_options,
        channel_options=channel_options,
    )
    if uploaded is not None:
        signature = (uploaded.name, uploaded.size)
        if st.session_state.get(_UPLOAD_SIGNATURE_KEY) != signature:
            st.session_state[_UPLOAD_SIGNATURE_KEY] = signature
            _read_locally(uploaded.getvalue(), uploaded.name)
    else:
        st.session_state.pop(_UPLOAD_SIGNATURE_KEY, None)
        st.session_state.pop(_UPLOAD_ERROR_KEY, None)
        st.session_state.pop(_PENDING_KEY, None)

    error = st.session_state.get(_UPLOAD_ERROR_KEY)
    if error:
        st.error(error)

    pending = st.session_state.get(_PENDING_KEY) if uploaded is not None else None
    if pending:
        # Round 3 (Requirement 37.1, 37.2): masked first; the user decides.
        st.caption(f"{pending['note']} {PRIVACY_NOTE}")
        allowed, off_reason = ai_ui.can_call()
        with st.container(key="pan_upload_choice", horizontal=True):
            use_bedrock = st.button(
                "Fill Form with Bedrock",
                key="bedrock_btn_upload_fill",
                disabled=not allowed,
                help="Sends the masked text to Amazon Bedrock to read the fields. "
                     + ai_usage.TOKEN_HINTS["upload"],
            )
            use_builtin = st.button(
                "Fill Form with Built-in Rules",
                key="upload_fill_builtin",
                help="Reads the fields on this computer. Nothing is sent.",
            )
        if not allowed:
            st.caption(f"Bedrock is not available: {ai_usage.reason_text(off_reason)}.")
        slot = st.empty()
        if use_bedrock or use_builtin:
            _fill(bool(use_bedrock), slot, **options)

    if uploaded is not None and st.session_state.get(_UPLOAD_SUMMARY_KEY):
        st.success(st.session_state[_UPLOAD_SUMMARY_KEY])
        rec = st.session_state.get(_UPLOAD_USAGE_KEY)
        if rec:
            theme.st_markdown(ai_ui.meta_html(ai_usage.UsageRecord(**rec)))
