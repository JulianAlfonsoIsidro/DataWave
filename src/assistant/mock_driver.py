"""Offline Mock Mode: keyword-routed chat answers and rule-based extraction.

This driver answers chat turns with no AWS call at all (Requirement 4.2). It
keyword-routes the question to one of the four :mod:`assistant.tools` tools on a
first-match-wins basis, runs that tool, and renders a short templated answer
that interpolates only the numbers the :class:`~assistant.models.ToolResult`
carries and explicitly names the tool as the source (Requirements 2.1, 2.6). A
question with no campaign vocabulary gets the fixed scope refusal and calls no
tool (Requirement 5.3).
"""

from __future__ import annotations

import re

from assistant import tools
from assistant.guardrails import OUT_OF_SCOPE_REDIRECT
from assistant.tools import SEGMENT_LABELS

# A promo-id pattern such as ``P001`` / ``PROMO-2024-03``. We accept both the
# short ``P###`` form and a token that merely starts with ``P`` followed by a
# digit so a brief like "promo P001" or "PROMO-2024-03" both route to accuracy.
_PROMO_ID_RE = re.compile(r"\bP(?:ROMO)?[-\s]?\d[\w-]*\b", re.IGNORECASE)

# A peso / numeric amount: an optional ``P``/``PHP``/``₱`` prefix, then digits
# with optional thousands separators and an optional decimal part. Captures the
# numeric body so commas can be stripped before parsing.
_AMOUNT_RE = re.compile(
    r"(?:php|p|₱)?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Keyword groups driving the routing (all matched case-insensitively).
_WHAT_IF_KEYWORDS = ("threshold", "what if")
_ACCURACY_KEYWORDS = ("accurate", "actual")
_COMPARE_KEYWORDS = ("compare", "all segments", "which segment", "skip")


def _parse_amount(question: str) -> float | None:
    """Return the first peso/numeric amount in ``question``, or ``None``.

    Strips a leading ``P``/``PHP``/``₱`` and any thousands separators before
    parsing, so "P300,000" and "300000" both yield ``300000.0``.
    """
    match = _AMOUNT_RE.search(question)
    if match is None:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_promo_id(question: str) -> str | None:
    """Return the first promo-id-shaped token in ``question``, or ``None``."""
    match = _PROMO_ID_RE.search(question)
    return match.group(0) if match else None


def _find_segment(question_lower: str) -> str | None:
    """Return the first Segment_Label named in ``question_lower``, or ``None``.

    Matching is case-insensitive and respects :data:`SEGMENT_LABELS` priority
    order, so the first label that appears wins.
    """
    for label in SEGMENT_LABELS:
        if label.lower() in question_lower:
            return label
    return None


def _fmt(value) -> str:
    """Render a surfaced number compactly: ints without a trailing ``.0``."""
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return f"{int(value):,}"
        return f"{value:,.2f}"
    return str(value)


def _render_get_card(result) -> str:
    """One-line card summary citing ``get_card``."""
    d = result.data
    # The surfaced card carries a ``segment``? No -- get_card projects fields
    # only, so name the segment from the action context instead.
    return (
        f"Based on get_card: {d.get('action')} — "
        f"channel {d.get('dominant_channel')}, "
        f"~{_fmt(d.get('expected_joiners'))} expected joiners "
        f"(90% {_fmt(d.get('joiners_90_low'))}-{_fmt(d.get('joiners_90_high'))}), "
        f"expected value {_fmt(d.get('expected_value'))}. (source: get_card)"
    )


def _render_compare_segments(result) -> str:
    """Per-segment one-liners citing ``compare_segments``."""
    parts = []
    for segment, card in result.data.items():
        parts.append(
            f"{segment}: ~{_fmt(card.get('expected_joiners'))} joiners "
            f"(90% {_fmt(card.get('joiners_90_low'))}-"
            f"{_fmt(card.get('joiners_90_high'))}), "
            f"value {_fmt(card.get('expected_value'))}"
        )
    body = "; ".join(parts) if parts else "no segment cards available"
    return f"Based on compare_segments: {body}. (source: compare_segments)"


def _render_what_if(result) -> str:
    """Per-segment totals and deltas at the new threshold citing ``what_if``."""
    d = result.data
    threshold = _fmt(d.get("threshold_php"))
    totals = d.get("totals_by_segment", {})
    deltas = d.get("delta_by_segment", {})
    parts = []
    for segment, total in totals.items():
        delta = deltas.get(segment, {})
        joiners = _fmt(total.get("expected_joiners"))
        djoiners = delta.get("expected_joiners", 0.0)
        sign = "+" if djoiners >= 0 else ""
        parts.append(
            f"{segment}: ~{joiners} joiners ({sign}{_fmt(djoiners)} vs current)"
        )
    body = "; ".join(parts) if parts else "no segment totals available"
    return (
        f"Based on what_if at a threshold of {threshold}: {body}. "
        f"(source: what_if)"
    )


def _render_past_promo_accuracy(result) -> str:
    """Predicted vs actual per segment citing ``past_promo_accuracy``."""
    d = result.data
    promo_id = d.get("promo_id")
    parts = []
    for row in d.get("segments", []):
        parts.append(
            f"{row.get('segment')}: predicted {_fmt(row.get('predicted'))}, "
            f"actual {_fmt(row.get('actual'))}"
        )
    body = "; ".join(parts) if parts else "no segment rows available"
    return (
        f"Based on past_promo_accuracy for {promo_id}: {body}. "
        f"(source: past_promo_accuracy)"
    )


# Map each tool name to the renderer used for its ok=True result.
_RENDERERS = {
    "get_card": _render_get_card,
    "compare_segments": _render_compare_segments,
    "what_if": _render_what_if,
    "past_promo_accuracy": _render_past_promo_accuracy,
}


def _render(result) -> str:
    """Render a tool result into answer text, always citing the tool.

    On ``ok=False`` the tool's note is relayed verbatim (e.g. the needs-a-run
    guidance) with the tool named as the source so the citation is always
    present (Requirement 2.6). On ``ok=True`` the tool-specific template
    interpolates the surfaced numbers.
    """
    if not result.ok:
        return f"{result.note} (source: {result.tool_name})"
    renderer = _RENDERERS.get(result.tool_name)
    if renderer is None:  # defensive; every tool has a renderer
        return f"{result.note} (source: {result.tool_name})"
    return renderer(result)


def answer_with_mock(question, run_result, run_context):
    """Answer one chat turn offline by keyword-routing to a tool (Req 4.2).

    Routing is first-match-wins and case-insensitive:

    1. a numeric amount OR "threshold"/"what if" -> :func:`tools.what_if`
    2. a promo-id pattern OR "accurate"/"actual" -> :func:`tools.past_promo_accuracy`
    3. "compare"/"all segments"/"which segment"/"skip" -> :func:`tools.compare_segments`
    4. a known Segment_Label -> :func:`tools.get_card`
    5. otherwise -> the fixed scope refusal, calling no tool (Requirement 5.3)

    For routes 1-4 the routed tool is run and a templated answer that
    interpolates its numbers and cites it is returned; ``tool_called`` is the
    tool name even when the tool returns ``ok=False`` (so the needs-a-run note
    is relayed). Route 5 returns ``(OUT_OF_SCOPE_REDIRECT, None)``. Never calls
    AWS (Requirements 2.1, 2.6, 5.3).

    Returns:
        tuple[str, str | None]: ``(answer_text, tool_called)``.
    """
    text = question or ""
    lowered = text.lower()

    amount = _parse_amount(text)
    promo_id = _parse_promo_id(text)

    # Route 1: what_if.
    if amount is not None or any(kw in lowered for kw in _WHAT_IF_KEYWORDS):
        threshold = amount
        if threshold is None and run_result is not None:
            # Fall back to the current run's threshold when a keyword routed us
            # here without a parseable number, so the tool has something to run.
            spec = getattr(run_result, "promo_spec", None)
            threshold = getattr(spec, "threshold_php", None)
        result = tools.what_if(threshold, run_result, run_context)
        return _render(result), result.tool_name

    # Route 2: past_promo_accuracy.
    if promo_id is not None or any(kw in lowered for kw in _ACCURACY_KEYWORDS):
        result = tools.past_promo_accuracy(promo_id)
        return _render(result), result.tool_name

    # Route 3: compare_segments.
    if any(kw in lowered for kw in _COMPARE_KEYWORDS):
        result = tools.compare_segments(run_result)
        return _render(result), result.tool_name

    # Route 4: get_card for a named segment.
    segment = _find_segment(lowered)
    if segment is not None:
        result = tools.get_card(segment, run_result)
        return _render(result), result.tool_name

    # Route 5: out of scope -- fixed refusal, no tool.
    return OUT_OF_SCOPE_REDIRECT, None


# --- Upload field extraction (Mock rules) ---------------------------------

# Mechanic synonyms -> canonical MECHANIC_OPTIONS token. Checked in order so a
# more specific phrase ("adb increase") wins over a generic one. Keys are
# lowercase; the scan lowercases the campaign text before matching.
_MECHANIC_SYNONYMS: tuple[tuple[str, str], ...] = (
    ("top up", "TOP_UP"),
    ("top-up", "TOP_UP"),
    ("topup", "TOP_UP"),
    ("new account", "NEW_ACCOUNT"),
    ("new-account", "NEW_ACCOUNT"),
    ("account opening", "NEW_ACCOUNT"),
    ("open an account", "NEW_ACCOUNT"),
    ("adb increase", "ADB_INCREASE"),
    ("increase adb", "ADB_INCREASE"),
    ("increase in adb", "ADB_INCREASE"),
    ("grow adb", "ADB_INCREASE"),
    ("raise adb", "ADB_INCREASE"),
)

# Channel synonyms to scan for (raw tokens; validate_fields + map_channel
# normalize and drop). Each entry is a (regex, raw_name) pair.
_CHANNEL_SYNONYMS: tuple[tuple[str, str], ...] = (
    ("in-app", "in-app"),
    ("in app", "in-app"),
    ("inapp", "in-app"),
    ("push", "push"),
    ("notification", "notification"),
    ("e-mail", "email"),
    ("email", "email"),
    ("sms", "sms"),
    ("text message", "message"),
)

# A peso amount: an optional P/PHP/₱ marker then digits with optional thousands
# separators and decimals. Captures the numeric body for comma stripping. Used
# with finditer so we can locate an amount near a cue word.
_PESO_AMOUNT_RE = re.compile(
    r"(?:php|p|₱)\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# A short reward phrase following a reward cue word, captured to end of line.
_REWARD_RE = re.compile(
    r"(?:reward|bonus|cashback)\s*[:\-]?\s*([^\r\n.]+)",
    re.IGNORECASE,
)

# Title Case runs following a segment/eligibility cue; raw candidates that
# validate_fields intersects against segment_options.
_SEGMENT_RE = re.compile(
    r"(?:segments?|eligible)\s*[:\-]?\s*"
    r"([A-Z][\w']*(?:\s+(?:but|and|&|[A-Z][\w']*))*)",
)


def _extract_product_type(lowered: str):
    """Return the first PRODUCT_TYPE_OPTIONS label present, else None."""
    from assistant.extract import PRODUCT_TYPE_OPTIONS

    for option in PRODUCT_TYPE_OPTIONS:
        if option.lower() in lowered:
            return option
    return None


def _extract_mechanic(lowered: str):
    """Return the first matching canonical mechanic token, else None."""
    for phrase, token in _MECHANIC_SYNONYMS:
        if phrase in lowered:
            return token
    return None


def _amount_near(text: str, cues: tuple[str, ...]):
    """Return the peso amount whose match is nearest any cue word, else None.

    Scans every peso amount and every cue occurrence and picks the amount with
    the smallest distance to a cue. Returns ``None`` when no amount is found.
    """
    lowered = text.lower()
    cue_positions: list[int] = []
    for cue in cues:
        start = 0
        while True:
            idx = lowered.find(cue, start)
            if idx == -1:
                break
            cue_positions.append(idx)
            start = idx + len(cue)
    if not cue_positions:
        return None

    best_value = None
    best_distance = None
    for match in _PESO_AMOUNT_RE.finditer(text):
        try:
            value = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        pos = match.start()
        distance = min(abs(pos - cue) for cue in cue_positions)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_value = value
    return best_value


def _all_amounts(text: str) -> list[float]:
    """Return every peso amount in order of appearance."""
    values: list[float] = []
    for match in _PESO_AMOUNT_RE.finditer(text):
        try:
            values.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return values


def _extract_amounts(text: str):
    """Return ``(threshold_php, min_adb)`` candidates, each possibly ``None``.

    Prefers an amount near "threshold" for ``threshold_php`` and near
    "min adb"/"minimum adb" for ``min_adb``. When only one amount is present in
    the whole text, it is assigned to ``threshold_php``.
    """
    threshold = _amount_near(text, ("threshold",))
    min_adb = _amount_near(text, ("min adb", "minimum adb", "min. adb"))
    if threshold is None and min_adb is None:
        amounts = _all_amounts(text)
        if len(amounts) == 1:
            threshold = amounts[0]
    return threshold, min_adb


def _extract_reward(text: str):
    """Return a short reward phrase following a reward cue, else None."""
    match = _REWARD_RE.search(text)
    if match is None:
        return None
    reward = match.group(1).strip()
    return reward or None


def _extract_segments(text: str) -> list[str]:
    """Return raw Title Case segment candidates after a segment/eligible cue.

    validate_fields intersects these against the real ``segment_options``, so
    this stays deliberately permissive and only collects plausible names.
    """
    candidates: list[str] = []
    for match in _SEGMENT_RE.finditer(text):
        phrase = match.group(1).strip()
        if phrase and phrase not in candidates:
            candidates.append(phrase)
    return candidates


def _extract_channels(lowered: str) -> list[str]:
    """Return raw channel tokens detected in the text (deduplicated)."""
    found: list[str] = []
    for needle, raw in _CHANNEL_SYNONYMS:
        if needle in lowered and raw not in found:
            found.append(raw)
    return found


def extract_fields_rules(campaign_text):
    """Derive raw promo-form candidates from ``campaign_text`` (Requirement 7.5).

    Scans the text case-insensitively with simple keyword and peso-amount rules
    and returns a RAW candidate ``dict`` — only the keys it actually found, since
    :func:`assistant.extract.validate_fields` tolerates missing keys and drops
    anything invalid. Never calls AWS.

    Candidate keys (each omitted when nothing is found):

    * ``product_type`` — a canonical ``PRODUCT_TYPE_OPTIONS`` label
    * ``mechanic`` — a canonical ``MECHANIC_OPTIONS`` token
    * ``threshold_php`` / ``min_adb`` — peso amounts near their cue words
    * ``reward`` — a short reward phrase
    * ``eligible_segments`` — raw Title Case segment candidates
    * ``channels`` — raw channel tokens (validate_fields maps/drops them)

    Returns:
        dict[str, Any]: The raw candidate values that were detected.
    """
    text = campaign_text or ""
    lowered = text.lower()
    candidates: dict[str, object] = {}

    product_type = _extract_product_type(lowered)
    if product_type is not None:
        candidates["product_type"] = product_type

    mechanic = _extract_mechanic(lowered)
    if mechanic is not None:
        candidates["mechanic"] = mechanic

    threshold, min_adb = _extract_amounts(text)
    if threshold is not None:
        candidates["threshold_php"] = threshold
    if min_adb is not None:
        candidates["min_adb"] = min_adb

    reward = _extract_reward(text)
    if reward is not None:
        candidates["reward"] = reward

    segments = _extract_segments(text)
    if segments:
        candidates["eligible_segments"] = segments

    channels = _extract_channels(lowered)
    if channels:
        candidates["channels"] = channels

    return candidates
