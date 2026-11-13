"""Ask Assistant tab (Part 7, task 9.3; Part 9 round 3).

Presentation only. Answers come from ``ai.assistant.answer``; this module
builds the grounding from the New Promo session state and the current run,
and draws the conversation.

Requirements: 3.8 (chat UI with suggested questions), 3.9 (Demo Mode label
beside Demo answers), 3.11 (non-blocking notice when the log is not saved),
3.12 (ask the user to fill in or upload a campaign first, no assistant call),
3.6 (invalid question shows a warning, no call), 1.7 (Demo Mode label).

Part 9 round 3 (spec part9-layout-fixes):

- Requirement 30: the grounding carries the Run_Summary (segment totals,
  actions, expected joiners, impact, persona names), so the assistant can
  answer about the results after Run Analysis. The owner reported that it
  could not; the payload used to hold the form and document only.
- Requirement 35: a plain transcript, a dot for the user and the stone block
  for the assistant, a prompt line with a hint row, the Bedrock wait line
  while an answer is fetched, and the answer revealed in short steps.
- Requirements 32, 33, 37: the notice, the mode chips, an "AI-generated"
  tag and a token line per answer, "What The AI Used", a number check,
  "Report A Wrong Answer", "Clear Conversation And Log", a question limit
  and a live character count.

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

import html
import time
from typing import Any

import streamlit as st

import ai_ui
import theme
import upload_panel
from ai.assistant import (
    SUGGESTED_QUESTIONS,
    AssistantAnswer,
    CampaignGrounding,
    answer,
    clear_log,
    estimated_input_tokens,
    report_wrong_answer,
    validate_question,
)
from webapp_core import ai_usage
from webapp_core.run_summary import run_summary
from webapp_core.threshold import ThresholdType, format_value

RUN_RESULT_KEY = "run_result"  # same key as app/main.py
PERSONA_RESULT_KEY = "persona_run_result"  # same key as app/persona_page.py
HISTORY_KEY = "assistant_history"
_SEEDED_REWARD = "Bonus interest"
# Round 3: the assistant is given the mechanic's plain name, so a code such
# as TOP_UP never shows in an answer (same names as the New Promo select).
_MECHANIC_NAMES = {
    "TOP_UP": "Top Up",
    "NEW_ACCOUNT": "New Account",
    "ADB_INCREASE": "ADB Increase",
    "OTHER": "Other",
}

EMPTY_CAMPAIGN_MESSAGE = (
    "Fill in the campaign details or upload a campaign file first, "
    "then ask your question."
)
LOG_NOTICE = "This answer could not be saved to the assistant log."
LIMIT_MESSAGE = (
    f"This session has reached its limit of {ai_usage.SESSION_QUESTION_LIMIT} questions. "
    "Clear the conversation to start again."
)
DOES_LINE = (
    "Here the AI answers questions about your campaign and the run's totals. "
    "It never produces or changes a number: scoring is the prediction model, "
    "and built-in rules answer when the AI is not used."
)
FIELD_NAMES = {
    "question": "your question",
    "form_fields": "the New Promo form",
    "field_tags": "which fields came from the file",
    "context": "the campaign context",
    "document_text": "the uploaded file's text (masked)",
    "known_gaps": "the gaps the app found",
    "run_summary": "the run's totals by segment, the impact figures and persona names",
}


def _threshold_label(state: Any) -> str | None:
    result = state.get(RUN_RESULT_KEY)
    spec = getattr(result, "promo_spec", None)
    if spec is None:
        return None
    try:
        t_type = ThresholdType(spec.threshold_type)
    except ValueError:
        t_type = ThresholdType.TOP_UP
    value = (
        spec.threshold_pct
        if t_type is ThresholdType.BALANCE_INCREASE and spec.threshold_pct is not None
        else spec.threshold_php
    )
    try:
        return format_value(t_type, float(value))
    except Exception:  # noqa: BLE001 - a label must never break the page
        return None


def _impact(result: Any) -> dict[str, Any] | None:
    try:
        from webapp_core.impact import compute_impact, load_channel_costs

        impact = compute_impact(result, load_channel_costs())
    except Exception:  # noqa: BLE001 - impact is optional context
        return None
    if not getattr(impact, "available", False):
        return None
    return {
        "messages_saved": impact.messages_saved,
        "joiners_kept_pct": impact.joiners_kept_pct,
        "cost_saved_php": impact.cost_saved,
    }


def build_grounding(state: Any = None) -> CampaignGrounding:
    """Build the assistant grounding from form widgets, tags, context, text and run."""
    state = st.session_state if state is None else state
    ttype = state.get(upload_panel.THRESHOLD_TYPE_KEY)
    form: dict[str, Any] = {
        "product_type": state.get(upload_panel.PRODUCT_TYPE_KEY),
        "mechanic": _MECHANIC_NAMES.get(
            str(state.get(upload_panel.MECHANIC_KEY)), state.get(upload_panel.MECHANIC_KEY)
        ),
        "reward": state.get(upload_panel.REWARD_KEY),
        "min_adb": state.get(upload_panel.MIN_ADB_KEY),
        "eligible_segments": list(state.get(upload_panel.SEGMENTS_KEY) or []),
        "channels": list(state.get(upload_panel.CHANNELS_KEY) or []),
    }
    result = state.get(RUN_RESULT_KEY)
    spec = getattr(result, "promo_spec", None)
    if spec is not None and getattr(spec, "threshold_php", None) is not None:
        # Once a run exists its threshold wins: What-If rescoring moves the
        # run's threshold while the New Promo slider keeps its old value.
        try:
            run_type = ThresholdType(spec.threshold_type)
        except ValueError:
            run_type = ThresholdType.TOP_UP
        form["threshold_type"] = run_type.value
        form["threshold_value"] = (
            spec.threshold_pct
            if run_type is ThresholdType.BALANCE_INCREASE and spec.threshold_pct is not None
            else spec.threshold_php
        )
    elif isinstance(ttype, ThresholdType):
        form["threshold_type"] = ttype.value
        form["threshold_value"] = state.get(upload_panel.threshold_value_key(ttype))

    run = None
    if result is not None:
        personas = state.get(PERSONA_RESULT_KEY)
        run = run_summary(
            result,
            threshold_label=_threshold_label(state),
            impact=_impact(result),
            persona_sets=getattr(personas, "persona_sets", None),
        )
    return CampaignGrounding(
        form=form,
        tags=dict(state.get(upload_panel.TAGS_KEY) or {}),
        context=dict(state.get(upload_panel.CONTEXT_KEY) or {}),
        document_text=str(state.get(upload_panel.DOCUMENT_TEXT_KEY) or ""),
        run=run,
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


def _md(text: str) -> str:
    """Answer text for st.markdown: no LaTeX from a currency sign."""
    return str(text).replace("$", "\\$")


def _record_of(message: dict) -> ai_usage.UsageRecord | None:
    rec = message.get("usage")
    if isinstance(rec, dict):
        return ai_usage.UsageRecord(**rec)
    return None


def _render_turn(index: int, message: dict) -> None:
    """One transcript row: the marker column, then the turn's text."""
    if message["role"] == "user":
        with st.container(key=f"pan_turn_u{index}"):
            theme.st_markdown(f'<div class="pan-turn-mark">{theme.user_marker_html()}</div>')
            theme.st_markdown(f'<div class="pan-turn-user">{html.escape(message["text"])}</div>')
        return
    with st.container(key=f"pan_turn_a{index}"):
        theme.st_markdown(f'<div class="pan-turn-mark">{theme.bedrock_html("rest")}</div>')
        st.markdown(_md(message["text"]))
        rec = _record_of(message)
        if rec is not None and message.get("mode") != "Local":
            theme.st_markdown(ai_ui.meta_html(rec))
        if message.get("flagged"):
            figures = ", ".join(message["flagged"])
            theme.st_markdown(
                f'<div class="pan-ai-flag">Check these figures: {html.escape(figures)}. '
                "They were not found in the campaign or the run.</div>"
            )
        if message.get("log_notice"):
            st.caption(LOG_NOTICE)
        if message.get("mode") != "Local":
            with st.expander("What The AI Used", key=f"assistant_used_{index}"):
                sent = [FIELD_NAMES.get(k, k) for k in message.get("fields_sent", [])]
                st.caption("Sent: " + (", ".join(sent) if sent else "nothing"))
                mode = "Bedrock" if message.get("mode") == "Bedrock" else "Built-in rules (Demo Mode)"
                st.caption(f"Answered by: {mode}")
                if rec is not None:
                    st.caption(ai_usage.usage_line(rec))
                st.caption("No client-level data is ever sent. Only totals and the campaign.")
        if message.get("reported"):
            st.caption("Reported as wrong. Thank you; it was logged for review.")
        elif message.get("mode") != "Local":
            if st.button("Report A Wrong Answer", key=f"assistant_report_{index}", type="tertiary"):
                question = ""
                history = st.session_state.get(HISTORY_KEY, [])
                for earlier in reversed(history[:index]):
                    if earlier["role"] == "user":
                        question = earlier["text"]
                        break
                report_wrong_answer(question, message["text"])
                message["reported"] = True
                st.rerun()


def _finish_seconds() -> float:
    """How long the block's finish plays before the answer shows (a token)."""
    import ui_effects

    try:
        parsed = ui_effects._parse_duration_s(theme.token_pair("--pan-dur-cube-finish")[0])
    except Exception:  # noqa: BLE001 - the token is optional; fall back
        parsed = None
    return parsed if parsed else 0.9


def _reveal_steps(text: str) -> list[str]:
    """The answer as growing prefixes of its lines (each keeps valid Markdown)."""
    lines = text.split("\n")
    steps = ["\n".join(lines[: i + 1]) for i, line in enumerate(lines) if line.strip()]
    return steps or [text]


def _questions_asked(history: list[dict]) -> int:
    return sum(1 for m in history if m["role"] == "user")


def _handle_question(question: str, history: list[dict], thread) -> None:
    """Validate, answer, and append to the history (no call when invalid).

    Everything is drawn into ``thread``, the message area above the input,
    so the question and the reply never land under the box.
    """
    with thread:
        error = validate_question(question)
        if error is not None:
            st.warning(error)
            return
        if _questions_asked(history) >= ai_usage.SESSION_QUESTION_LIMIT:
            st.info(LIMIT_MESSAGE)
            return
        grounding = build_grounding()
        if campaign_is_empty(grounding):
            st.info(EMPTY_CAMPAIGN_MESSAGE)
            return
        history.append({"role": "user", "text": question})
        _render_turn(len(history) - 1, history[-1])
        allowed, off_reason = ai_ui.can_call()
        estimate = estimated_input_tokens(question, grounding) if allowed else None
        with st.container(key=f"pan_turn_a{len(history)}_wait"):
            mark = st.empty()
            mark.markdown(f'<div class="pan-turn-mark">{theme.bedrock_html("spin")}</div>',
                          unsafe_allow_html=True)
            slot = st.empty()
            slot.markdown(ai_ui.wait_html(estimate), unsafe_allow_html=True)
            reply: AssistantAnswer = answer(question, grounding, use_ai=allowed, off_reason=off_reason)
            mark.markdown(f'<div class="pan-turn-mark">{theme.bedrock_html("finish")}</div>',
                          unsafe_allow_html=True)
            time.sleep(_finish_seconds())
            # Stepped reveal: converse returns the whole reply, so it is shown
            # in short steps here (no streaming API, Requirement 35.7).
            for step in _reveal_steps(reply.text):
                slot.markdown(_md(step))
                time.sleep(0.05)
    feature_mode = "Local" if reply.mode == "Local" else reply.mode
    rec = ai_ui.record(ai_usage.record_from(
        ai_usage.FEATURE_ASSISTANT, feature_mode, reply.usage, reply.seconds, reply.reason,
    ))
    history.append({
        "role": "assistant", "text": reply.text, "mode": reply.mode,
        "usage": rec.as_dict() if reply.mode != "Local" else None,
        "flagged": list(reply.flagged), "fields_sent": list(reply.fields_sent),
    })
    if not reply.log_saved:
        history[-1]["log_notice"] = True
    st.rerun()


def render_assistant_page() -> None:
    """Render the Ask Assistant tab."""
    st.subheader("Ask Assistant")
    st.caption(
        "Ask about the campaign proposal and, after Run Analysis, its results: "
        "offer, eligibility, channels, timeline, messaging, segments and expected joiners."
    )
    ai_ui.notice("bedrock", DOES_LINE, chips=True)
    switch_col, _rest = st.columns([1, 2])
    with switch_col:
        ai_ui.ai_switch()
    history: list[dict] = st.session_state.setdefault(HISTORY_KEY, [])

    pending: str | None = None
    columns = st.columns(len(SUGGESTED_QUESTIONS))
    for index, (column, label) in enumerate(zip(columns, SUGGESTED_QUESTIONS)):
        with column:
            if st.button(label, key=f"assistant_suggested_{index}", width="stretch"):
                pending = label

    # The conversation is one container drawn before the input, and a new
    # question and its reply are added into it, so they stay above the box.
    thread = st.container()
    with thread:
        for index, message in enumerate(history):
            _render_turn(index, message)

    if history:
        if st.button("Clear Conversation And Log", key="assistant_clear", type="tertiary"):
            st.session_state[HISTORY_KEY] = []
            clear_log()
            st.rerun()

    asked = _questions_asked(history)
    theme.st_markdown(
        '<div class="pan-prompt-hint"><span>Enter to send | 500 characters max</span>'
        f'<span class="pan-chat-count">0 / 500 characters</span>'
        f"<span>{asked} of {ai_usage.SESSION_QUESTION_LIMIT} questions</span></div>"
    )
    typed = st.chat_input("Ask About This Campaign", max_chars=500)
    question = pending if pending is not None else typed
    if question is not None:
        _handle_question(question, history, thread)
    ai_ui.usage_expander()
