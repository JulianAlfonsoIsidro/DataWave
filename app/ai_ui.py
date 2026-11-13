"""Shared drawers for the AI features (Part 9 round 3).

Presentation and session state only (spec part9-layout-fixes, Requirements
32, 33, 35, 37.6). The pure logic is in ``webapp_core.ai_usage`` and
``ai.bedrock``. Every Bedrock_Feature page uses these, so the notices, the
mode chip, the token lines, the wait line and the usage records look and
behave the same everywhere. No credential is ever read here except to say
whether one exists; the model id is shown because it is not a secret.
"""

from __future__ import annotations

import streamlit as st

import theme
from ai import bedrock
from webapp_core import ai_usage

USAGE_KEY = "ai_usage_records"          # list[UsageRecord]
AI_ENABLED_KEY = "ai_enabled"           # the "Use AI Features" switch


def records() -> list[ai_usage.UsageRecord]:
    return list(st.session_state.get(USAGE_KEY, []))


def record(rec: ai_usage.UsageRecord) -> ai_usage.UsageRecord:
    """Keep one call's record for the session totals."""
    st.session_state.setdefault(USAGE_KEY, []).append(rec)
    return rec


def ai_enabled() -> bool:
    return bool(st.session_state.get(AI_ENABLED_KEY, True))


def can_call() -> tuple[bool, str]:
    """(may this session call Bedrock now, the reason code when not)."""
    if not ai_enabled():
        return False, "ai_off"
    if ai_usage.cap_reached(records()):
        return False, "cap_reached"
    if not bedrock.credentials_available():
        return False, "no_credentials"
    return True, ""


def mode_label() -> str:
    """"Bedrock" when a call would go to Bedrock now, else "Demo Mode"."""
    ok, _reason = can_call()
    return "Bedrock" if ok else "Demo Mode"


def status_chips_html() -> str:
    """The mode chip and the model id (never a key or secret)."""
    mode = mode_label()
    chips = theme.ai_chip_html(mode, icon=mode == "Bedrock",
                               kind="bedrock" if mode == "Bedrock" else "demo")
    model = bedrock.model_id()
    if model:
        chips += theme.ai_chip_html(f"Model: {model}")
    return f'<div class="pan-ai-status">{chips}</div>'


def notice(kind: str, does: str = "", *, chips: bool = False) -> None:
    """One section notice (Requirement 32); with ``chips`` the mode chips too."""
    markup = theme.ai_notice_html(kind, does)
    if chips:
        markup = status_chips_html() + markup
    theme.st_markdown(markup)


def token_line(rec: ai_usage.UsageRecord | None) -> None:
    if rec is not None:
        theme.st_markdown(theme.token_line_html(ai_usage.usage_line(rec)))


def meta_html(rec: ai_usage.UsageRecord | None) -> str:
    """Tag, mode chip and token line for one AI output."""
    if rec is None:
        return ""
    bedrock_used = rec.mode == "Bedrock"
    tag = "AI-generated" if bedrock_used else "Built-in rules"
    chip = theme.ai_chip_html("Bedrock" if bedrock_used else "Demo Mode",
                              icon=bedrock_used, kind="bedrock" if bedrock_used else "demo")
    line = ai_usage.usage_line(rec)
    if not bedrock_used and rec.reason:
        why = ai_usage.reason_text(rec.reason)
        line += f" | {why[:1].upper() + why[1:]}"
    return theme.ai_meta_html(tag, chip, line)


def wait_html(estimate_tokens: int | None = None) -> str:
    """The Bedrock wait line with the labelled input estimate."""
    est = ai_usage.estimate_line(estimate_tokens) if estimate_tokens else ""
    return theme.wait_line_html(est)


def ai_switch() -> None:
    """The "Use AI Features" switch (Requirement 37.6)."""
    st.toggle(
        "Use AI Features",
        value=True,
        key=AI_ENABLED_KEY,
        help="Off: every AI feature uses the built-in rules and nothing is sent to Bedrock.",
    )


def usage_expander() -> None:
    """The "AI Usage" dropdown: session totals per feature (Requirement 33.5)."""
    recs = records()
    with st.expander("AI Usage", key="ai_usage_panel"):
        if not recs:
            st.caption("No AI calls yet in this session.")
            return
        rows = []
        for t in ai_usage.session_totals(recs):
            rows.append(
                f"<tr><td class='pan-td pan-strong'>{t.feature}</td>"
                f"<td class='pan-td pan-num'>{t.calls:,}</td>"
                f"<td class='pan-td pan-num'>{t.bedrock_calls:,}</td>"
                f"<td class='pan-td pan-num'>{t.demo_calls:,}</td>"
                f"<td class='pan-td pan-num'>{t.total_tokens:,}</td>"
                f"<td class='pan-td'>{'; '.join(t.reasons) or 'None'}</td></tr>"
            )
        theme.st_markdown(
            "<table class='pan-table'><tr><th class='pan-th'>Feature</th>"
            "<th class='pan-th pan-num'>Calls</th><th class='pan-th pan-num'>Bedrock</th>"
            "<th class='pan-th pan-num'>Built-in</th><th class='pan-th pan-num'>Tokens</th>"
            "<th class='pan-th'>Why built-in was used</th></tr>" + "".join(rows) + "</table>"
        )
        used = ai_usage.tokens_used(recs)
        st.caption(
            f"Session total: {used:,} of {ai_usage.SESSION_TOKEN_CAP:,} tokens. "
            "Built-in answers use no tokens."
        )
