"""Deterministic rule-based Mocks for the AI features (Requirement 1.9).

Each Mock is a pure function of its input: no network, no clock, no randomness,
and no Streamlit import. This module is organised in sections, one per AI
feature, so later tasks can add the assistant and persona-namer Mocks without
touching the extraction section.

Section 1: extraction Mock (Requirement 2.8) -- ``mock_extract``.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Shared constants (kept local so this module has no app dependencies)
# ---------------------------------------------------------------------------

# Channel labels must match Part 4 exactly (In-app, Email, SMS).
CHANNEL_LABELS: tuple[str, ...] = ("In-app", "Email", "SMS")

KNOWN_SEGMENTS: tuple[str, ...] = (
    "Affluent-Gold",
    "Affluent-Preferred",
    "Mass",
    "Mid-Market",
)

# Threshold type labels (design section 7).
TOP_UP = "Top-Up Amount"
MIN_BALANCE = "Minimum Balance To Maintain"
BALANCE_INCREASE = "Balance Increase"
OPENING_AMOUNT = "Opening Amount For A New Account"

CONTEXT_KEYS: tuple[str, ...] = (
    "objective",
    "target_audience",
    "offer_details",
    "timeline",
    "key_messages",
)

# ---------------------------------------------------------------------------
# Section 1: extraction Mock
# ---------------------------------------------------------------------------

# Product keyword table; first match in this order wins.
_PRODUCT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Time Deposit", re.compile(r"time\s+deposit|placement|\bTD\b", re.I)),
    ("Credit Card", re.compile(r"credit\s+card", re.I)),
    ("Investment", re.compile(r"invest|mutual\s+fund|uitf|bond", re.I)),
    ("Savings", re.compile(r"saving|deposit|account", re.I)),
)

# Mechanic keyword table; first match in this order wins.
_MECHANIC_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TOP_UP", re.compile(r"top[\s-]?up", re.I)),
    ("NEW_ACCOUNT", re.compile(r"new\s+account|open(?:ing)?\s+(?:an?\s+)?account|opening", re.I)),
    ("ADB_INCREASE", re.compile(r"\badb\b|increase|maintain|average\s+(?:daily\s+)?balance", re.I)),
)

# Threshold keyword -> threshold type.
_THRESHOLD_KEYWORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (TOP_UP, re.compile(r"top[\s-]?up", re.I)),
    (MIN_BALANCE, re.compile(r"minimum\s+balance|maintain", re.I)),
    (OPENING_AMOUNT, re.compile(r"opening\s+(?:amount|deposit|balance)|initial\s+deposit|open(?:ing)?\s+(?:an?\s+)?account", re.I)),
)

_MECHANIC_TO_TYPE = {
    "TOP_UP": TOP_UP,
    "NEW_ACCOUNT": OPENING_AMOUNT,
    "ADB_INCREASE": MIN_BALANCE,
}

# Peso amount: PHP/Php/P/₱ prefix, digits with commas, optional k/m suffix.
_AMOUNT_RE = re.compile(
    r"(?:₱|PHP|Php|P(?=\d))\s?(\d[\d,]*(?:\.\d+)?)\s?((?i:million|thousand|mn|m|k))?\b",
)
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|percent\b)", re.I)
_BALANCE_INCREASE_RE = re.compile(
    r"(?:increase|grow|growth|raise)[^.\n]{0,40}?(\d+(?:\.\d+)?)\s?(?:%|percent\b)"
    r"|(\d+(?:\.\d+)?)\s?(?:%|percent\b)[^.\n]{0,30}?(?:increase|growth)",
    re.I,
)

_MIN_ADB_KEYWORDS = re.compile(
    r"min(?:imum)?\.?\s+adb|average\s+daily\s+balance|\badb\s+of\s+at\s+least",
    re.I,
)

_REWARD_KEYWORDS = re.compile(
    r"bonus\s+interest|cash\s?back|rebate|miles|reward\s+points|gift\s+card|"
    r"fee\s+waiver|promo\s+rate|bonus\s+points",
    re.I,
)

_CHANNEL_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("In-app", re.compile(r"in[\s-]?app|mobile\s+app|push\s+notification", re.I)),
    ("Email", re.compile(r"e-?mail", re.I)),
    ("SMS", re.compile(r"\bsms\b|text\s+message", re.I)),
)

# Labeled-line context parsing: key -> accepted labels.
_CONTEXT_LABELS: dict[str, tuple[str, ...]] = {
    "objective": ("objective", "objectives", "goal", "goals"),
    "target_audience": ("target audience", "audience", "target market", "target customers"),
    "offer_details": ("offer details", "offer", "promo details", "mechanics"),
    "timeline": ("timeline", "campaign period", "promo period", "duration", "schedule"),
    "key_messages": ("key messages", "key message", "messaging", "key messaging"),
}
_LABEL_TO_KEY = {
    label: key for key, labels in _CONTEXT_LABELS.items() for label in labels
}
_LABEL_LINE_RE = re.compile(
    r"^[ \t>*\-•]*(?P<label>[A-Za-z][A-Za-z ]{1,24}?)\s*[:：]\s*(?P<value>.+?)\s*$",
    re.M,
)
_REWARD_LABEL_RE = re.compile(
    r"^[ \t>*\-•]*(?:reward|incentive|benefit)\s*[:：]\s*(?P<value>.+?)\s*$",
    re.I | re.M,
)

_REWARD_MAX_CHARS = 200


def _to_number(digits: str, suffix: str | None) -> float:
    value = float(digits.replace(",", ""))
    unit = (suffix or "").lower()
    if unit in {"k", "thousand"}:
        value *= 1_000
    elif unit in {"m", "mn", "million"}:
        value *= 1_000_000
    return value


def _clean_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _amount_near(text: str, keyword: re.Pattern[str]) -> float | None:
    """First peso amount near a keyword (prefers amounts after it)."""
    for match in keyword.finditer(text):
        after = text[match.end() : match.end() + 80]
        found = _AMOUNT_RE.search(after)
        if found:
            return _to_number(found.group(1), found.group(2))
        before = text[max(0, match.start() - 60) : match.start()]
        found_all = list(_AMOUNT_RE.finditer(before))
        if found_all:
            last = found_all[-1]
            return _to_number(last.group(1), last.group(2))
    return None


def _first_rule(text: str, rules: tuple[tuple[str, re.Pattern[str]], ...]) -> str | None:
    for label, pattern in rules:
        if pattern.search(text):
            return label
    return None


_INLINE_LABEL_RE = re.compile(
    r"(?<=[.;!?])[ \t]+(?=(?:"
    + "|".join(re.escape(label) for label in sorted(_LABEL_TO_KEY, key=len, reverse=True))
    + r")[ \t]*[:：])",
    re.I,
)


def _parse_context(text: str) -> dict[str, str]:
    """Collect labeled lines (``Objective: ...``); first occurrence wins.

    A known label that follows a sentence end on the same line starts a new
    labeled line, so ``Objective: x. Timeline: y`` yields both.
    """
    text = _INLINE_LABEL_RE.sub("\n", text)
    context = {key: "" for key in CONTEXT_KEYS}
    for match in _LABEL_LINE_RE.finditer(text):
        key = _LABEL_TO_KEY.get(match.group("label").strip().lower())
        if key and not context[key]:
            context[key] = match.group("value").strip()
    return context


def _extract_threshold(text: str, mechanic: str | None) -> tuple[str | None, float | None]:
    # Percentage-of-ADB increase takes priority when explicitly stated.
    pct = _BALANCE_INCREASE_RE.search(text)
    if pct:
        raw = pct.group(1) or pct.group(2)
        return BALANCE_INCREASE, _clean_number(float(raw))

    candidates: list[str] = []
    for ttype, pattern in _THRESHOLD_KEYWORDS:
        if pattern.search(text):
            candidates.append(ttype)
    if mechanic in _MECHANIC_TO_TYPE:
        preferred = _MECHANIC_TO_TYPE[mechanic]
        candidates = [preferred] + [c for c in candidates if c != preferred]

    patterns = dict(_THRESHOLD_KEYWORDS)
    for ttype in candidates:
        amount = _amount_near(text, patterns[ttype])
        if amount is not None:
            return ttype, _clean_number(amount)
    return None, None


def mock_extract(text: str) -> dict[str, Any]:
    """Deterministically extract Campaign_Fields and Campaign_Context.

    Returns ``{"fields": {...}, "context": {...}}``. ``fields`` only holds keys
    the rules actually found (product_type, mechanic, threshold_type,
    threshold_value, reward, eligible_segments, min_adb, channels), so absent
    keys can be tagged "Needs Input". ``context`` always has the five keys
    objective, target_audience, offer_details, timeline, key_messages, with ""
    when no labeled line was found. Channels are exactly In-app, Email, SMS.
    Pure function of ``text``; never raises on string input.
    """
    text = text if isinstance(text, str) else ""
    fields: dict[str, Any] = {}

    product = _first_rule(text, _PRODUCT_RULES)
    if product:
        fields["product_type"] = product

    mechanic = _first_rule(text, _MECHANIC_RULES)
    if mechanic:
        fields["mechanic"] = mechanic

    ttype, tvalue = _extract_threshold(text, mechanic)
    if ttype is not None and tvalue is not None:
        fields["threshold_type"] = ttype
        fields["threshold_value"] = tvalue

    reward_match = _REWARD_LABEL_RE.search(text)
    if reward_match:
        reward = reward_match.group("value")
    else:
        keyword = _REWARD_KEYWORDS.search(text)
        reward = keyword.group(0) if keyword else ""
    reward = reward.strip()[:_REWARD_MAX_CHARS].strip()
    if reward:
        fields["reward"] = reward

    lowered = text.lower()
    segments = [s for s in KNOWN_SEGMENTS if s.lower() in lowered]
    if segments:
        fields["eligible_segments"] = segments

    min_adb = _amount_near(text, _MIN_ADB_KEYWORDS)
    if min_adb is not None:
        fields["min_adb"] = _clean_number(min_adb)

    channels = [label for label, pattern in _CHANNEL_RULES if pattern.search(text)]
    if channels:
        fields["channels"] = channels

    return {"fields": fields, "context": _parse_context(text)}


# ---------------------------------------------------------------------------
# Section 2: assistant Mock (Requirement 3.9)
# ---------------------------------------------------------------------------
# Templated answers built only from the form fields and the Campaign_Context.
# Pure functions: no network, no clock, no randomness, no model results.

_ASSISTANT_FIELD_LABELS: tuple[tuple[str, str], ...] = (
    ("product_type", "Product"),
    ("mechanic", "Mechanic"),
    ("threshold_type", "Threshold type"),
    ("threshold_value", "Threshold value"),
    ("reward", "Reward"),
    ("eligible_segments", "Eligible segments"),
    ("min_adb", "Minimum ADB"),
    ("channels", "Channels"),
)

_INTENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("missing", re.compile(r"missing|gap|incomplete|lack", re.I)),
    ("sms", re.compile(r"\bsms\b|text\s+message|draft", re.I)),
    ("eligibility", re.compile(r"eligib|qualif|who\s+can", re.I)),
    ("summary", re.compile(r"summar|overview|recap", re.I)),
)


def _fmt_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)


def _present_fields(form: Any) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for key, label in _ASSISTANT_FIELD_LABELS:
        value = form.get(key)
        if value is None or value == "" or value == [] or value == ():
            continue
        out.append((label, value))
    return out


def assistant_intent(question: str) -> str:
    """Classify a question as missing / sms / eligibility / summary / generic."""
    for intent, pattern in _INTENT_RULES:
        if pattern.search(question or ""):
            return intent
    return "generic"


def mock_assistant_answer(
    question: str,
    form: Any,
    context: Any,
    missing: list[str],
) -> str:
    """Deterministic templated answer from form fields and context only."""
    intent = assistant_intent(question)
    fields = _present_fields(form)
    ctx = {k: str(context.get(k) or "").strip() for k in CONTEXT_KEYS}

    if intent == "missing":
        if not missing:
            return "Nothing obvious is missing. Every field is filled in, each channel has a budget, and a control group is stated."
        return "Gaps found in this proposal: " + "; ".join(missing) + "."

    if intent == "sms":
        product = str(form.get("product_type") or "our offer")
        reward = str(form.get("reward") or "").strip()
        threshold = form.get("threshold_value")
        parts = [f"Hi! Enjoy our {product} offer"]
        if reward:
            parts[0] += f": {reward}"
        if threshold not in (None, ""):
            parts.append(f"Qualify with {_fmt_value(threshold)}.")
        if ctx["timeline"]:
            parts.append(f"{ctx['timeline']}.")
        parts.append("Reply STOP to opt out.")
        return "Draft SMS: " + " ".join(parts)

    if intent == "eligibility":
        segments = form.get("eligible_segments")
        min_adb = form.get("min_adb")
        bits: list[str] = []
        if segments:
            bits.append(f"eligible segments are {_fmt_value(segments)}")
        if min_adb not in (None, ""):
            bits.append(f"minimum ADB is {_fmt_value(min_adb)}")
        if ctx["target_audience"]:
            bits.append(f"target audience is {ctx['target_audience']}")
        if not bits:
            return "Eligibility is not clear: no segments, minimum ADB, or target audience is stated."
        text = "Eligibility as stated: " + "; ".join(bits) + "."
        if not segments or min_adb in (None, ""):
            text += " Consider stating both the eligible segments and the minimum ADB."
        return text

    # summary and generic share the same template
    lines = [f"{label}: {_fmt_value(value)}" for label, value in fields]
    for key, label in (
        ("objective", "Objective"),
        ("offer_details", "Offer"),
        ("timeline", "Timeline"),
        ("key_messages", "Key messages"),
    ):
        if ctx[key]:
            lines.append(f"{label}: {ctx[key]}")
    if not lines:
        return "There is not enough campaign detail yet to summarize."
    return "Campaign summary. " + "; ".join(lines) + "."


# ---------------------------------------------------------------------------
# Section 3: persona namer Mock (Requirements 6.9, 6.10, 6.12)
# ---------------------------------------------------------------------------
# Plain-English names, descriptions, difference statements, and actions built
# only from a PersonaAggregate (see ai.persona_narrator). Pure and
# deterministic: same aggregate and same ``taken`` set give the same text. No
# feature codes, no underscores, none of the banned phrases. Limits match the
# Bedrock validation rules: name 2-4 words / 40 chars, description 1-2
# sentences / 300 chars, difference 200 chars, 2-3 actions with exact channels
# and messages of at most 160 chars.

_PERSONA_NAME_MAX_CHARS = 40
_PERSONA_DESCRIPTION_MAX_CHARS = 300
_PERSONA_DIFFERENCE_MAX_CHARS = 200
_PERSONA_MESSAGE_MAX_CHARS = 160

# (keywords in a lower-cased trait label, angle name, base message), first hit wins.
_PERSONA_ANGLES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("other banks", "leaving", "outflow"), "Win-back offer",
     "Invite them to move more of their money back to us."),
    (("income", "inflow", "deposit", "balance", "payroll", "remittance"), "Savings bundle offer",
     "Show how a savings bundle can help their balance grow."),
    (("spend", "shopper"), "Rewards offer",
     "Highlight rewards on everyday spending."),
    (("invest", "wealth"), "Wealth-building offer",
     "Introduce a simple way to start building wealth."),
)
_PERSONA_DEFAULT_ANGLE = (
    "Tailored offer",
    "Share an offer that fits how they bank with us.",
)


def _persona_angle(label: str) -> tuple[str, str]:
    lowered = label.lower()
    for keywords, angle, message in _PERSONA_ANGLES:
        if any(k in lowered for k in keywords):
            return angle, message
    return _PERSONA_DEFAULT_ANGLE


def _persona_channels(reach: Any) -> list[str]:
    """Channels ordered by persona reach (highest first), In-app default order."""
    order = {c: i for i, c in enumerate(CHANNEL_LABELS)}
    shares = {c: s for c, s in reach if c in order}
    if not shares:
        return list(CHANNEL_LABELS)
    present = sorted(shares, key=lambda c: (-shares[c], order[c]))
    return present + [c for c in CHANNEL_LABELS if c not in shares]


def _join_phrases(phrases: list[str]) -> str:
    if len(phrases) <= 1:
        return "".join(phrases)
    return ", ".join(phrases[:-1]) + " and " + phrases[-1]


def _persona_name(agg: Any, taken: set[str]) -> str:
    used = {t.casefold() for t in taken}
    for trait in agg.traits:
        phrase = trait.phrase
        words = len(phrase.split())
        if 2 <= words <= 4 and len(phrase) <= _PERSONA_NAME_MAX_CHARS and phrase.casefold() not in used:
            return phrase
    # Letters, not digits, so the name never carries a number absent from the
    # aggregate (Requirement 6.5 applies to Bedrock and Mock text alike).
    index = 0
    while True:
        letters, n = "", index
        while True:
            letters = chr(ord("A") + n % 26) + letters
            n = n // 26 - 1
            if n < 0:
                break
        candidate = f"Customer Group {letters}"
        if candidate.casefold() not in used:
            return candidate
        index += 1


def mock_persona_narration(
    agg: Any, taken: set[str], archetypes: Any = None
) -> dict[str, Any]:
    """Build ``name``, ``description``, ``difference``, ``actions`` from ``agg``.

    ``agg`` is a ``PersonaAggregate``. ``taken`` is not mutated; the returned
    name is unique against it (Requirement 6.7 / 4.9 style).

    ``archetypes`` (the persona's traits as :class:`ai.archetypes.Archetype`,
    strongest first) turns on CRM-style names ("Disciplined Saver",
    "Digital-First Saver") and a "They are people with ..." description.
    """
    from ai.archetypes import archetype_name, people_with

    phrases = [t.phrase.lower() for t in agg.traits if t.phrase]

    # Description: 1-2 sentences within the length cap.
    first = f"This group is about {round(agg.share_pct)}% of the audience, with {agg.size:,} customers."
    description = first
    if archetypes:
        for count in range(min(3, len(archetypes)), 0, -1):
            second = f"They are people with {people_with(archetypes, count)}."
            if len(first) + 1 + len(second) <= _PERSONA_DESCRIPTION_MAX_CHARS:
                description = f"{first} {second}"
                break
    else:
        for count in range(min(3, len(phrases)), 0, -1):
            second = f"They stand out for {_join_phrases(phrases[:count])}."
            if len(first) + 1 + len(second) <= _PERSONA_DESCRIPTION_MAX_CHARS:
                description = f"{first} {second}"
                break

    # Difference statement within its cap.
    difference = "Compared with other personas, this group has no single standout trait."
    for count in range(min(2, len(phrases)), 0, -1):
        candidate = f"Compared with other personas, this group shows {_join_phrases(phrases[:count])}."
        if len(candidate) <= _PERSONA_DIFFERENCE_MAX_CHARS:
            difference = candidate
            break

    # Actions: 2 or 3, one per leading trait, each on a different channel.
    channels = _persona_channels(agg.channel_reach)
    count = min(3, max(2, len(agg.traits)))
    actions: list[str] = []
    for i in range(count):
        trait = agg.traits[i] if i < len(agg.traits) else None
        angle, message = _persona_angle(trait.label) if trait else _PERSONA_DEFAULT_ANGLE
        if trait and trait.phrase:
            message = f"{message} Speak to {trait.phrase.lower()[:60].rstrip()}."
        message = message[:_PERSONA_MESSAGE_MAX_CHARS]
        actions.append(f"{channels[i % len(channels)]}: {angle}. {message}")

    name = (archetype_name(archetypes, taken) if archetypes else None) or _persona_name(agg, taken)
    return {
        "name": name,
        "description": description,
        "difference": difference,
        "actions": actions,
    }


class MockPersonaNamer:
    """Rule-based ``PersonaNamer`` for Demo Mode (Requirements 6.9, 6.12).

    Leaves ``RuleBasedNamer`` untouched; its feature-code phrasing is exactly
    what Requirement 6.10 bans.
    """

    def name(self, profile: Any, taken: set[str]) -> Any:
        # Lazy import: persona_narrator imports this module at load time.
        from ai.archetypes import archetypes_for, trait_key
        from ai.persona_narrator import _focus_category, build_aggregate
        from part5_personas.labels import is_flag_attribute

        keys = [
            trait_key(attr, profile.distinguishing_directions.get(attr),
                      _focus_category(profile, attr), is_flag_attribute(attr))
            for attr in profile.distinguishing
        ]
        out = mock_persona_narration(build_aggregate(profile), taken, archetypes_for(keys))
        return {
            "name": out["name"],
            "description": out["description"],
            "actions": out["actions"],
            "difference": out["difference"],
        }
