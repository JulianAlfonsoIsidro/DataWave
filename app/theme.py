"""Theme for the Promo Audience Navigator webapp (Requirement 2).

The fixed visual identity is adapted from ``data/theme_reference.png`` (the BPI
mobile app mock) for a desktop web layout. The exact colors were sampled from
that image at implementation time and recorded in two places that must stay in
sync: the ``[theme]`` block of ``.streamlit/config.toml`` and the ``PALETTE``
dict below.

Sampling method: a short Pillow script (kept in ``scratch/`` during
implementation, then removed) read flat regions of the 1600x1200 reference and
took the most-common color per region:

* ``PRIMARY_RED`` ``#A42A26`` -- the deep red of the header bar and the action
  band (identical in both regions).
* ``ACCENT_GOLD`` ``#DBB32D`` -- the mustard background, the circular-button
  rings, the active-tab underline, and the card dividers.
* ``PANEL_WHITE`` ``#FFFFFF`` -- the white balance panel and the content cards.
* ``TEXT_DARK`` ``#1A1A1A`` -- the near-black balance number and body text (the
  balance glyphs sample as pure black; softened slightly for body readability).

This module exposes a single injected CSS block (:func:`build_css`) and small
render helpers (:func:`header`, :func:`metric_panel`, :func:`action_band`,
:func:`card`). ``streamlit`` is imported lazily inside the helpers so importing
``app.theme`` never requires a running Streamlit server (Requirement 2.1).
"""

from __future__ import annotations

import html

# --- palette sampled from data/theme_reference.png (Requirement 2.1) ---

PALETTE = {
    "PRIMARY_RED": "#A42A26",  # deep-red header bar / action band
    "ACCENT_GOLD": "#DBB32D",  # mustard rings / tab underline / card dividers
    "PANEL_WHITE": "#FFFFFF",  # white balance panel / cards
    "TEXT_DARK": "#1A1A1A",    # dark balance number / body text
}

# Convenience module-level aliases.
PRIMARY_RED = PALETTE["PRIMARY_RED"]
ACCENT_GOLD = PALETTE["ACCENT_GOLD"]
PANEL_WHITE = PALETTE["PANEL_WHITE"]
TEXT_DARK = PALETTE["TEXT_DARK"]

# The app title is text only -- no logo image (Requirement 2.2).
APP_TITLE = "Promo Audience Navigator"


def build_css() -> str:
    """Return the single CSS block injected once into the page.

    Styles, from the palette: the full-width deep-red header bar; the uppercase
    tab strip (active = white text + gold bottom border, inactive = gold text,
    Requirement 2.3); the balance-style metric panel (large bold number above a
    small uppercase caption, white panel, Requirement 2.4); the four circular
    action buttons (white fill, gold ring, red glyph, white label beneath,
    Requirement 2.5); and the content cards (white, rounded, red heading, gold
    ``hr`` divider, Requirement 2.6).
    """
    red = PALETTE["PRIMARY_RED"]
    gold = PALETTE["ACCENT_GOLD"]
    white = PALETTE["PANEL_WHITE"]
    dark = PALETTE["TEXT_DARK"]
    return f"""
<style>
:root {{
  --pan-red: {red};
  --pan-gold: {gold};
  --pan-white: {white};
  --pan-dark: {dark};
}}

/* Deep-red full-width header bar with bold white text title (Req 2.2). */
.pan-header {{
  background: var(--pan-red);
  color: var(--pan-white);
  width: 100%;
  padding: 18px 28px;
  border-radius: 0 0 6px 6px;
  margin: -1rem -1rem 1rem -1rem;
}}
.pan-header .pan-title {{
  font-size: 1.9rem;
  font-weight: 800;
  letter-spacing: 0.5px;
  color: var(--pan-white);
  margin: 0;
}}

/* Uppercase tab strip (Req 2.3): active = white + gold underline, else gold. */
.stTabs [data-baseweb="tab-list"] {{
  background: var(--pan-red);
  gap: 8px;
  padding: 0 16px;
  border-radius: 6px;
}}
.stTabs [data-baseweb="tab"] {{
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 700;
  color: var(--pan-gold);
  background: transparent;
  border-bottom: 3px solid transparent;
}}
.stTabs [data-baseweb="tab"][aria-selected="true"] {{
  color: var(--pan-white);
  border-bottom: 3px solid var(--pan-gold);
}}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: transparent; }}

/* Balance-style metric panel: big bold number + small uppercase caption (Req 2.4). */
.pan-metric-panel {{
  background: var(--pan-white);
  color: var(--pan-dark);
  text-align: center;
  padding: 22px 12px;
  border-radius: 8px;
  border: 1px solid #ececec;
  margin-bottom: 1rem;
}}
.pan-metric-number {{
  font-size: 2.6rem;
  font-weight: 800;
  line-height: 1.1;
  color: var(--pan-dark);
}}
.pan-metric-caption {{
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: #666;
  margin-top: 4px;
}}

/* Deep-red action band with four gold-ringed circular buttons (Req 2.5). */
.pan-action-band {{
  background: var(--pan-red);
  border-radius: 8px;
  padding: 18px 10px;
  display: flex;
  justify-content: space-around;
  gap: 8px;
  margin-bottom: 1rem;
}}
.pan-action-item {{
  text-align: center;
  flex: 1;
}}
.pan-action-button {{
  width: 58px;
  height: 58px;
  margin: 0 auto 8px auto;
  border-radius: 50%;
  background: var(--pan-white);
  border: 3px solid var(--pan-gold);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4rem;
  color: var(--pan-red);
}}
.pan-action-label {{
  color: var(--pan-white);
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 1px;
  font-weight: 700;
}}

/* Content cards: white, rounded, red heading, gold hr divider (Req 2.6). */
.pan-card {{
  background: var(--pan-white);
  border-radius: 10px;
  padding: 16px 20px;
  border: 1px solid #ececec;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  margin-bottom: 1rem;
}}
.pan-card .pan-card-heading {{
  color: var(--pan-red);
  font-weight: 800;
  font-size: 1.15rem;
  margin: 0 0 6px 0;
}}
.pan-card hr.pan-divider {{
  border: none;
  border-top: 2px solid var(--pan-gold);
  margin: 8px 0 12px 0;
}}
</style>
"""


def inject_css() -> None:
    """Inject the single CSS block into the page once (Requirement 2.1)."""
    import streamlit as st

    st.markdown(build_css(), unsafe_allow_html=True)


def header(title: str = APP_TITLE) -> None:
    """Render the full-width deep-red header bar with a bold white text title.

    No logo image is used -- the title is text only (Requirement 2.2).
    """
    import streamlit as st

    st.markdown(
        f'<div class="pan-header"><p class="pan-title">{html.escape(title)}</p></div>',
        unsafe_allow_html=True,
    )


def metric_panel(number: str, caption: str) -> None:
    """Render the balance-style white metric panel (Requirement 2.4).

    ``number`` is shown large and bold above ``caption`` (small, uppercase),
    mirroring the account-balance block in the reference image.
    """
    import streamlit as st

    st.markdown(
        (
            '<div class="pan-metric-panel">'
            f'<div class="pan-metric-number">{html.escape(str(number))}</div>'
            f'<div class="pan-metric-caption">{html.escape(str(caption))}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


# The four action-band buttons, in fixed order: glyph + white label (Req 2.5).
ACTION_BUTTONS = [
    ("\u25B6", "RUN"),            # play triangle
    ("\u2699", "WHAT-IF"),         # gear
    ("\u2B07", "DOWNLOAD LEADS"),  # down arrow
    ("\U0001F4AC", "ASK ASSISTANT"),  # speech balloon
]


def action_band(buttons=ACTION_BUTTONS) -> None:
    """Render the deep-red action band with four gold-ringed circular buttons.

    Each button is a white circle with a gold ring and a red glyph, with its
    label below in white (Requirement 2.5). This renders the visual band; the
    live click handlers are wired as Streamlit buttons in ``app/main.py``.
    """
    import streamlit as st

    items = "".join(
        (
            '<div class="pan-action-item">'
            f'<div class="pan-action-button">{glyph}</div>'
            f'<div class="pan-action-label">{html.escape(label)}</div>'
            "</div>"
        )
        for glyph, label in buttons
    )
    st.markdown(f'<div class="pan-action-band">{items}</div>', unsafe_allow_html=True)


def card(heading: str, body_html: str) -> None:
    """Render a white rounded content card (Requirement 2.6).

    The card has a red heading, a gold ``hr`` divider, then ``body_html`` (which
    the caller is responsible for building safely).
    """
    import streamlit as st

    st.markdown(
        (
            '<div class="pan-card">'
            f'<div class="pan-card-heading">{html.escape(heading)}</div>'
            '<hr class="pan-divider" />'
            f"{body_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
