"""Ask Assistant tab (Part 7, task 9.3).

Presentation only. Answers come from ``ai.assistant.answer``; this module
builds the grounding from the New Promo session state and renders the chat.

Requirements: 3.8 (chat UI with suggested questions), 3.9 (Demo Mode badge
beside Demo answers), 3.11 (non-blocking notice when the log is not saved),
3.12 (ask the user to fill in or upload a campaign first, no assistant call),
3.6 (invalid question shows a warning, no call), 1.7 (Demo Mode badge).

Empty-campaign rule (documented choice). The form widgets are seeded with
defaults, so their mere presence does not mean the user supplied a campaign.
The campaign counts as empty only when ALL of these hold:

- no uploaded document text,
- no extraction exists (no Field_Tags, so no upload was processed),
- no analysis run exists, and
- the form still equals its untouched defaults for the free-entry fields
  (Reward is blank or still the seeded "Bonus interest", Min ADB is 0).

Selectors (product, mechanic, segments, channels) start fully populated, so
they cannot signal intent on their own and are ignored by the rule.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

import theme
import upload_panel
from ai.assistant import (
    SUGGESTED_QUESTIONS,
    AssistantAnswer,
    CampaignGrounding,
    answer,
    validate_question,
)
from webapp_core.threshold import ThresholdType

RUN_RESULT_KEY = "run_result"  # same key as app/main.py
HISTORY_KEY = "assistant_history"
_SEEDED_REWARD = "Bonus interest"

EMPTY_CAMPAIGN_MESSAGE = (
    "Fill in the campaign details or upload a campaign file first, "
    "then ask your question."
)
LOG_NOTICE = "This answer could not be saved to the assistant log."


def build_grounding(state: Any = None) -> CampaignGrounding:
    """Build the assistant grounding from form widgets, tags, context, text."""
    state = st.session_state if state is None else state
    ttype = state.get(upload_panel.THRESHOLD_TYPE_KEY)
    form: dict[str, Any] = {
        "product_type": state.get(upload_panel.PRODUCT_TYPE_KEY),
        "mechanic": state.get(upload_panel.MECHANIC_KEY),
        "reward": state.get(upload_panel.REWARD_KEY),
        "min_adb": state.get(upload_panel.MIN_ADB_KEY),
        "eligible_segments": list(state.get(upload_panel.SEGMENTS_KEY) or []),
        "channels": list(state.get(upload_panel.CHANNELS_KEY) or []),
    }
    if isinstance(ttype, ThresholdType):
        form["threshold_type"] = ttype.value
        form["threshold_value"] = state.get(upload_panel.threshold_value_key(ttype))
    return CampaignGrounding(
        form=form,
        tags=dict(state.get(upload_panel.TAGS_KEY) or {}),
        context=dict(state.get(upload_panel.CONTEXT_KEY) or {}),
        document_text=str(state.get(upload_panel.DOCUMENT_TEXT_KEY) or ""),
    )


def campaign_is_empty(grounding: CampaignGrounding, state: Any = None) -> bool:
    """True when no campaign was supplied (see the module docstring rule)."""
    state = st.session_state if state is None else state
    if grounding.document_text.strip() or grounding.tags:
        return False
    if state.get(RUN_RESULT_KEY) is not None:
        return False
    reward = str(grounding.form.get("reward") or "").strip()
    if reward and reward != _SEEDED_REWARD:
        return False
    if float(grounding.form.get("min_adb") or 0) > 0:
        return False
    return True


def _render_message(message: dict) -> None:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and message.get("mode") == "Demo":
            theme.st_markdown(theme.badge_html("Demo Mode", "warning"))
        st.write(message["text"])


def _handle_question(question: str, history: list[dict]) -> None:
    """Validate, answer, and append to the history (no call when invalid)."""
    error = validate_question(question)
    if error is not None:
        st.warning(error)
        return
    grounding = build_grounding()
    if campaign_is_empty(grounding):
        st.info(EMPTY_CAMPAIGN_MESSAGE)
        return
    history.append({"role": "user", "text": question})
    with st.spinner("Thinking..."):
        reply: AssistantAnswer = answer(question, grounding)
    history.append({"role": "assistant", "text": reply.text, "mode": reply.mode})
    if not reply.log_saved:
        history[-1]["log_notice"] = True
    st.rerun()


def render_assistant_page() -> None:
    """Render the Ask Assistant tab."""
    st.subheader("Ask Assistant")
    st.caption(
        "Ask about the current campaign proposal: offer, eligibility, channels, "
        "timeline, and messaging."
    )
    history: list[dict] = st.session_state.setdefault(HISTORY_KEY, [])

    pending: str | None = None
    columns = st.columns(len(SUGGESTED_QUESTIONS))
    for index, (column, label) in enumerate(zip(columns, SUGGESTED_QUESTIONS)):
        with column:
            if st.button(label, key=f"assistant_suggested_{index}", width="stretch"):
                pending = label

    for message in history:
        _render_message(message)
    if history and history[-1].get("log_notice"):
        st.caption(LOG_NOTICE)

    typed = st.chat_input("Ask About This Campaign")
    question = pending if pending is not None else typed
    if question is not None:
        _handle_question(question, history)
