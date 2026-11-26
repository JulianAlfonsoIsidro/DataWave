"""Help And FAQs content (Part 9 round 2, Requirement 28).

Pure, no Streamlit. ``app/help_page.py`` only draws what is here. Rates and
amounts come from ``part4_cards.config`` through ``webapp_core.number_help``
so the answers follow the model's real assumptions (Requirement 28.8).

- :data:`FORMULAS`: "How The Numbers Fit Together", as :class:`HelpFormula`.
- :data:`ENTRIES`: "Common Questions", as :class:`HelpEntry` in page order.
  Each answer is plain and at most five sentences, and ``where`` names the
  section to look at (Requirement 28.9, 28.10).
- :data:`NEXT_STEPS`: "Where To Go Next", as ``(section, why)``.

A page section, tab or button named in a question or answer is written as
``[[Name]]``; ``app/help_page.py`` shows it bold and in quotes.
"""

from __future__ import annotations

from dataclasses import dataclass

from webapp_core.number_help import control_pct, value_per_joiner, z_90


@dataclass(frozen=True)
class HelpEntry:
    id: str
    question: str
    answer: str
    formula: str | None
    where: str


@dataclass(frozen=True)
class HelpFormula:
    """One "How The Numbers Fit Together" card: a name, its equation and an
    optional plain note under the equation."""

    name: str
    equation: str
    note: str | None = None


FORMULAS: tuple[HelpFormula, ...] = (
    HelpFormula(
        "Clients",
        "Clients = Not Contacted + Control Group + Sendable",
        "Every client in a segment lands in exactly one of the three.",
    ),
    HelpFormula(
        "Expected Joiners",
        "Expected Joiners = p\u2081 + p\u2082 + \u2026 + p\u2099",
        "p is each sendable lead's chance of joining, from the model.",
    ),
    HelpFormula(
        "Share Of Sendable Leads",
        "Share = Expected Joiners \u00f7 Sendable Leads \u00d7 100%",
        "Uses the exact forecast, before rounding.",
    ),
    HelpFormula(
        "Likely Range (90%)",
        f"Likely Range = Expected Joiners \u00b1 {z_90()} \u00d7 \u221a(\u03a3 p \u00d7 (1 \u2212 p))",
        "The low end never goes below 0.",
    ),
    HelpFormula(
        "Expected Value",
        f"Expected Value = Expected Joiners \u00d7 {value_per_joiner()} \u2212 Message Cost",
        "Message cost uses each lead's best reachable channel.",
    ),
    HelpFormula(
        "Joiners Kept",
        "Joiners Kept = Recommended Expected Joiners \u00f7 Baseline Expected Joiners \u00d7 100%",
        "Baseline messages every eligible lead; Recommended skips segments marked Skip.",
    ),
    HelpFormula(
        "Similarity Score",
        "Similarity Score = Audience + Need + Product And Mechanic + Economics "
        "+ Duration + Channels + Objective + Name And Summary",
        "Eight parts with weights adding to 100; a missing part's weight is shared out.",
    ),
    HelpFormula(
        "Gap",
        "Gap = Actual Join Rate \u2212 Predicted Join Rate",
        "In percentage points: +1.2 pts means more joined than forecast.",
    ),
)

_EJ_EQ = "Expected Joiners = p\u2081 + p\u2082 + \u2026 + p\u2099"
_SHARE_EQ = "Share = Expected Joiners \u00f7 Sendable Leads \u00d7 100%"

ENTRIES: tuple[HelpEntry, ...] = (
    HelpEntry(
        "sendable",
        "On the [[Results]] tab, why are the sendable leads fewer than the total clients in each segment?",
        "Not every client can be messaged. Some are left out by the contact rules "
        "(Not Contacted), and some are held back as a Control Group. The rest are "
        "Sendable: the leads in your download file.",
        "Clients = Not Contacted + Control Group + Sendable",
        "[[Results]] tab, [[Where Each Segment's Clients Go]]",
    ),
    HelpEntry(
        "expected_joiners",
        "What does the Expected Joiners number at the top of [[Results]] and on the [[Results Grid]] actually mean?",
        "The model gives every sendable lead a chance of joining, for example 0.31. "
        "Expected Joiners adds those chances up, so it is the number we expect to "
        "join on average, not a head count. The real result will land near it.",
        _EJ_EQ,
        "[[Results Grid]] and the top of [[Results]] and [[Personas]]",
    ),
    HelpEntry(
        "forecasted",
        "On the [[Results Grid]], why does Expected Joiners show a whole number like 87 and then (Forecasted: 87.3) beside it?",
        "People come in whole numbers, so the main figure is rounded (halves round "
        "up). The bracket keeps the exact forecast for anyone who wants it.",
        None,
        "[[Results Grid]] and the [[What-If]] tab",
    ),
    HelpEntry(
        "totals",
        "In the [[What-If]] table, why don't the Expected Joiners rows add up exactly to the total?",
        "Each row is rounded on its own, and the total is rounded from the exact "
        "sum. So the rounded rows can differ from the rounded total by 1. The "
        "forecasts in brackets always add up.",
        None,
        "[[What-If]] tab and the [[Results Grid]]",
    ),
    HelpEntry(
        "percentage",
        "What does the percentage under Expected Joiners at the top of [[Results]] mean?",
        "It is the share of the leads you can message that we expect to join: "
        "Expected Joiners divided by Sendable leads. It tells you how well the "
        "send list is likely to convert.",
        _SHARE_EQ,
        "Top of [[Results]] and [[Personas]]",
    ),
    HelpEntry(
        "recommended",
        "How many of the leads in [[Download Leads]] are expected to join?",
        "Open [[Download Leads]] and pick a segment in [[Choose Leads To Download]]. "
        "[[Check Before You Download]] shows that segment's sendable leads and how "
        "many of them are expected to join, for example 87 of 282. That number is the "
        "segment's Expected Joiners. The segment marked [[Act first]] is the one to start with.",
        None,
        "[[Results]] tab, in the [[Download Leads]] dropdown",
    ),
    HelpEntry(
        "control",
        "What is the Control Group in the [[Download Leads]] rows, and why are some leads held back?",
        f"About {control_pct()} of each group's contactable leads are held back and "
        "not messaged. Comparing them with the messaged leads later shows how much "
        "the promo itself changed behaviour.",
        None,
        "[[Results]] tab, [[Download Leads]]",
    ),
    HelpEntry(
        "not_contacted",
        "Who falls under Not Contacted on the [[Results]] tab, and why are they left out?",
        "Clients on the do-not-bother list, clients contacted too often recently, "
        "and clients with no reachable channel. They are left out of every file.",
        None,
        "[[Results]] tab, [[Download Leads]] (each row lists the reasons)",
    ),
    HelpEntry(
        "act_first",
        "What does the [[Act first]] tag on the [[Results Grid]] and [[Decision Cards]] mean?",
        "It marks the segment whose recommended action is Prioritize: the best "
        "place to start. To get its leads, open [[Download Leads]], pick the "
        "segment in [[Choose Leads To Download]], read [[Check Before You Download]], "
        "tick [[I Checked These Figures]], then press Download Leads.",
        None,
        "[[Results Grid]], [[Decision Cards]] and the [[Download Leads]] dropdown",
    ),
    HelpEntry(
        "threshold",
        "What does the threshold on the [[New Promo]] form do, and what changes when I move the [[What-If]] slider?",
        "The threshold is the amount a client must reach to qualify, for example a "
        "top-up of \u20b1530,000. The [[What-If]] slider rescores the same audience at "
        "another threshold without retraining the model, so you can see how the "
        "numbers move.",
        None,
        "[[New Promo]] and [[What-If]] tabs",
    ),
    HelpEntry(
        "whatif_mismatch",
        "Why does the [[New Promo]] form still show my old threshold after I changed it in [[What-If]]?",
        "[[What-If]] changes the threshold the results use, but not the [[New Promo]] "
        "form. The [[Results]] tab shows which threshold it uses and a Reset button. "
        "[[Run Analysis]] always uses the form.",
        None,
        "Top of the [[Results]] tab, and the [[New Promo]] tab",
    ),
    HelpEntry(
        "likely_range",
        "What does the Likely Range on each [[Decision Card]] tell me?",
        "We are 90% sure the number who join will land in this range. It is wider "
        "for bigger groups and when chances are closer to 50/50.",
        f"Likely Range = Expected Joiners \u00b1 {z_90()} \u00d7 \u221a(\u03a3 p \u00d7 (1 \u2212 p))",
        "[[Results]] tab, [[Decision Cards]]",
    ),
    HelpEntry(
        "expected_value",
        "How is the Expected Value on each [[Decision Card]] calculated?",
        f"Each expected joiner is valued at {value_per_joiner()}. The cost of sending "
        "the messages is taken off, so it is the forecast value of contacting the "
        "segment.",
        f"Expected Value = Expected Joiners \u00d7 {value_per_joiner()} \u2212 Message Cost",
        "[[Results]] tab, [[Decision Cards]]",
    ),
    HelpEntry(
        "impact",
        "What do Messages Saved, Joiners Kept and Cost Saved under the [[Results Grid]] mean?",
        "They compare the recommended plan with messaging every eligible lead. "
        "Messages Saved is how many fewer messages you send. Joiners Kept is the "
        "share of expected joiners you still reach. Cost Saved is the channel cost "
        "you avoid.",
        "Joiners Kept = Recommended Expected Joiners \u00f7 Baseline Expected Joiners \u00d7 100%",
        "[[Results]] tab, under the [[Results Grid]]",
    ),
    HelpEntry(
        "personas",
        "On the [[Personas]] tab, how are personas built, and why do the lead counts change with the grouping I pick?",
        "Leads with similar traits are grouped into personas. With All leads, every "
        "client is grouped. By campaign with the current run, only the sendable "
        "leads are grouped. A split, for example by region, builds personas inside "
        "each group, so the counts add up to that group.",
        None,
        "[[Personas]] tab",
    ),
    HelpEntry(
        "demo_mode",
        "Why do I see a [[Demo Mode]] badge in [[Ask Assistant]] or on the persona cards?",
        "When the AI service is not available, the AI features use built-in "
        "rules instead and show a [[Demo Mode]] badge. Scores and segments never use "
        "AI, so they are the same either way.",
        None,
        "[[Ask Assistant]], [[Personas]] and [[Upload Campaign File]]",
    ),
    HelpEntry(
        "page_lock",
        "Why does the page lock while [[Run Analysis]] or [[Build Personas]] is loading?",
        "Both take a moment. The page locks so a second click cannot start the "
        "same job twice. You can still scroll.",
        None,
        "[[New Promo]] and [[Personas]] tabs",
    ),
)

def _tokens_answer() -> str:
    from webapp_core import ai_usage as u

    q, n, f = u.MEASURED_TOKENS_PER_QUESTION, u.MEASURED_TOKENS_PER_PERSONA, u.MEASURED_TOKENS_PER_UPLOAD
    if not (q and n and f):
        return ("Every call shows its tokens under the answer, and the [[AI Usage]] dropdown "
                "adds them up. The averages are in docs/ai-token-report.md. Built-in answers use none.")
    return (f"On average ({u.MEASURED_LABEL}): about {q:,} tokens per assistant question, "
            f"{n:,} per persona named and {f:,} per file read. Built-in answers use none. "
            "Each call shows its own count, and the [[AI Usage]] dropdown adds them up.")


# Part 9 round 3 (Requirement 39.2): what the AI does, and its limits.
ENTRIES = ENTRIES + (
    HelpEntry(
        "ai_does",
        "What does the AI do in this app, and what does it never do?",
        "It reads an uploaded file to fill the form, suggests persona names, and answers "
        "questions in [[Ask Assistant]]. It never produces or changes a number: every "
        "score and forecast comes from the prediction model. When the AI is off or not "
        "available, built-in rules do the same jobs.",
        None,
        "[[Upload Campaign File]], [[Personas]] and [[Ask Assistant]]",
    ),
    HelpEntry(
        "ai_why",
        "Why use AI here instead of only built-in rules?",
        "Campaign files and questions are written in free text that rules read poorly. "
        "The AI handles that wording, and its output is checked: fields are validated, "
        "persona names are checked against the persona's own figures, and answers are "
        "checked for figures that are not in your campaign or run.",
        None,
        "[[Upload Campaign File]], [[Personas]] and [[Ask Assistant]]",
    ),
    HelpEntry(
        "ai_privacy",
        "What data is sent to the AI, and how is it protected?",
        "Only totals and campaign text. Phone numbers, email addresses and long numbers "
        "are masked before a file is sent, and nothing is sent until you press a button "
        "with the Bedrock mark. A guard blocks any request that holds a client id or "
        "per-client rows.",
        None,
        "[[Upload Campaign File]] and [[Ask Assistant]]",
    ),
    HelpEntry(
        "ai_check_persona",
        "How do I check a persona name from Bedrock?",
        "Read the card under the name: the size, share and what sets it apart come from "
        "the clustering, not the AI. The name should match those traits. If it does not, "
        "switch [[Persona Names]] back to built-in names; who is in each persona never changes.",
        None,
        "[[Personas]] tab",
    ),
    HelpEntry(
        "ai_tokens",
        "How many tokens does the AI use?",
        _tokens_answer(),
        "Total Tokens = Input Tokens + Output Tokens",
        "Under each AI answer, and [[AI Usage]] in [[Ask Assistant]]",
    ),
)

NEXT_STEPS: tuple[tuple[str, str], ...] = (
    ("Results", "Which segment to act on, and the files to send."),
    ("What-If", "Try another threshold and compare."),
    ("Personas", "Who is in each segment, and how to message them."),
)
