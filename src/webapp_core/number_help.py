"""Plain descriptions of the figures, for CRM managers (Part 9 round 2).

Pure, no Streamlit (spec ``part9-layout-fixes``, Requirement 22). One
function per figure so the page and the Help And FAQs dialog use the same
words. Each description is at most 90 characters and uses no code names.
Rates and amounts are read from ``part4_cards.config``, never copied, so a
changed assumption changes the text (Requirement 22.5).
"""

from __future__ import annotations

from part4_cards.config import CONTROL_FRACTION, VALUE_PER_JOIN_PHP, Z_90

from webapp_core.number_format import of_sendable_text

MAX_CHARS = 90


def control_pct() -> str:
    """The control-group share as text: ``10%``."""
    return f"{CONTROL_FRACTION * 100:.0f}%"


def value_per_joiner() -> str:
    """The value of one joiner as text: ``₱1,000``."""
    return f"₱{VALUE_PER_JOIN_PHP:,.0f}"


def z_90() -> str:
    """The 90% range multiplier as text: ``1.645``."""
    return f"{Z_90:g}"


def header_help() -> str:
    return "The share of messages you can send that we expect to turn into joiners."


def joiners_of_sendable(forecast: float, sendable: int) -> str:
    return of_sendable_text(forecast, sendable)


def clients_help() -> str:
    return "Everyone in this group."


def not_contacted_help() -> str:
    return "Left out: do-not-bother list, contacted too often, or no channel."


def control_help() -> str:
    return f"Held back (about {control_pct()}) so you can measure the promo's effect."


def sendable_help() -> str:
    return "The leads in the file. You can message these."


def range_help() -> str:
    return "We are 90% sure the number who join will land in this range."


def value_help() -> str:
    return f"Joiners at {value_per_joiner()} each, minus the cost of the messages."


def threshold_help() -> str:
    return "Clients at or above this amount qualify."


def adb_help() -> str:
    return "ADB is the average daily balance."


def control_reason_help() -> str:
    """Why a slice of each group is not messaged (shown in the download check)."""
    return "Not messaged on purpose, so you can compare and see if the promo works."


def impact_help() -> str:
    return "Compared with messaging every eligible lead, skipping segments marked Skip."


def impact_why() -> str:
    """Why these three figures are shown, and why some leads are left out.

    Longer than the one-line helps on purpose: it is the one place the
    summary says what the figures are for. Not in ``ALL_STATIC`` (90 chars).
    """
    return (
        "Why these figures? Segments marked Skip are the least likely to join, so "
        "leaving them out saves messages and money while keeping most of the "
        f"expected joiners. About {control_pct()} of each group is also held back "
        "on purpose, as a control group. Comparing it with the messaged leads "
        "later shows whether the promo itself worked."
    )


def whatif_table_help() -> str:
    return "Sendable = leads you can message. Expected Joiners is the forecast among them."


def flow_help() -> str:
    return "Clients = Not Contacted + Control Group + Sendable."


def flow_table_help() -> str:
    return "Expected Joiners is the forecast among Sendable leads only."


def predicted_actual_help() -> str:
    return "Predicted: the join rate we forecast. Actual: the join rate that happened."


def gap_help() -> str:
    return "Actual minus predicted, in percentage points."


def similarity_help() -> str:
    return "0 to 100. How alike this promo is to the one you are designing."


def recommended_caption(forecast: float, sendable: int) -> str:
    """``about 87 of the 282 sendable leads are expected to join``."""
    from webapp_core.number_format import shown_joiners

    noun = "lead is" if sendable == 1 else "leads are"
    return f"about {shown_joiners(forecast):,} of the {sendable:,} sendable {noun} expected to join"


def persona_group_caption(group: str, size: int, total: int, *, sendable: bool) -> str:
    """``Luzon · 376 of 1,595 sendable leads`` above a persona group."""
    kind = "sendable leads" if sendable else "leads"
    return f"{group} · {size:,} of {total:,} {kind}"


ALL_STATIC = (
    header_help, clients_help, not_contacted_help, control_help, sendable_help,
    range_help, value_help, threshold_help, adb_help, impact_help, control_reason_help,
    whatif_table_help, flow_help, flow_table_help, predicted_actual_help,
    gap_help, similarity_help,
)
