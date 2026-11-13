"""Help And FAQs dialog (Part 9 round 2, Requirement 28).

Presentation only. The words live in ``webapp_core.help_content`` (pure, no
Streamlit); this module only draws them in an ``st.dialog`` opened by the
round "?" button (key ``help_open``) at the top right.

Why a dialog: a separate page or a seventh tab would unmount the other tabs,
and Streamlit drops the state of widgets that are not rendered, so the New
Promo form would lose its values. A dialog draws over the page instead.

Three parts, in order (Requirement 28.6): "How The Numbers Fit Together"
(the formulas), "Common Questions" (closed dropdowns, one per question) and
"Where To Go Next" (buttons that switch the section; they change no widget
value). Pressing one reruns the app, which closes the dialog.
"""

from __future__ import annotations

import html
import re
from typing import Callable

import streamlit as st

from webapp_core.help_content import ENTRIES, FORMULAS, NEXT_STEPS


def formula_card_html(formula) -> str:
    """One formula card: the name in bold, then the equation in its own inner
    box (math font, normal weight), then an optional plain note."""
    note = (
        f'<div class="pan-formula-note">{html.escape(formula.note)}</div>'
        if formula.note else ""
    )
    return (
        '<div class="pan-formula-card">'
        f'<div class="pan-formula-name">{html.escape(formula.name)}</div>'
        f'<div class="pan-formula-eq">{html.escape(formula.equation)}</div>'
        f"{note}</div>"
    )


def formulas_html() -> str:
    """The formula cards (``.pan-formulas``)."""
    return f'<div class="pan-formulas">{"".join(formula_card_html(f) for f in FORMULAS)}</div>'


_MARK = re.compile(r"\[\[(.+?)\]\]")


def marked_html(text: str) -> str:
    """Escape ``text`` and show each ``[[Name]]`` as bold, quoted: "Name"."""
    return _MARK.sub(lambda m: f"<strong>&quot;{m.group(1)}&quot;</strong>", html.escape(text))


def marked_md(text: str) -> str:
    """The same for an expander label (Markdown): ``**"Name"**``."""
    return _MARK.sub(lambda m: f'**"{m.group(1)}"**', text)


def entry_html(entry) -> str:
    """One answer: the text, the formula when there is one, then where to see it."""
    out = f'<p class="pan-help-answer">{marked_html(entry.answer)}</p>'
    if entry.formula:
        out += f'<div class="pan-formula-eq">{html.escape(entry.formula)}</div>'
    out += f'<div class="pan-help-where">Where to see it: {marked_html(entry.where)}</div>'
    return out


def _draw(go_to: Callable[[str], None] | None) -> None:
    st.subheader("How The Numbers Fit Together")
    st.markdown(formulas_html(), unsafe_allow_html=True)

    st.subheader("Common Questions")
    for entry in ENTRIES:
        with st.expander(marked_md(entry.question), key=f"help_q_{entry.id}"):
            st.markdown(entry_html(entry), unsafe_allow_html=True)

    st.subheader("Where To Go Next")
    with st.container(key="pan_help_next", horizontal=True):
        for section, why in NEXT_STEPS:
            st.button(
                section,
                key=f"help_go_{section.lower().replace('-', '_')}",
                help=why,
                on_click=go_to if go_to else None,
                args=(section,) if go_to else None,
            )


@st.dialog("Help And FAQs", width="large")
def open_help(go_to: Callable[[str], None] | None = None) -> None:
    """The Help And FAQs dialog. ``go_to`` switches the section (``_go_to_now``)."""
    _draw(go_to)
