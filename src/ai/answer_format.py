"""One layout for every assistant answer, Bedrock or Demo (Part 9 round 3).

Pure, no Streamlit (spec part9-layout-fixes, Requirement 29). The layout is:

    One short lead line.

    - one idea per bullet (3 to 6 of them)
    - ...

    > A drafted message, as a quote block, after a caption bullet that names
    > the channel and the character count.

:func:`format_answer` turns any reply into that shape. It keeps line breaks,
caps the answer at :data:`MAX_WORDS` words by whole blocks (it never cuts a
bullet or a quote), removes headings, tables and underscores, and is
idempotent: formatting a formatted answer changes nothing. The cause of the
earlier run-on answers was the old word cap, which split on whitespace and
rejoined with single spaces, so every line break was lost.

:func:`unsupported_numbers` lists the figures in an answer that are not in the
payload (the approach of ``persona_narrator.numbers_in``), so the page can
flag them.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_WORDS = 150
MAX_BULLETS = 6

_BULLET = re.compile(r"^\s*(?:[-*•‣▪]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#{1,6}\s*")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")
_CHAR_COUNT = re.compile(r"\b\d+\s+characters?\b", re.I)

# Code names a reply may echo from the payload, in plain words.
_CODE_WORDS = {
    "p_join": "chance of joining",
    "min_adb": "minimum ADB",
    "threshold_value": "threshold value",
    "threshold_type": "threshold type",
    "product_type": "product type",
    "eligible_segments": "eligible segments",
    "offer_details": "offer details",
    "target_audience": "target audience",
    "key_messages": "key messages",
    "excluded_by_reason": "left-out reasons",
    "expected_joiners": "expected joiners",
    "sendable_count": "sendable leads",
    "control_group": "control group",
    "not_contacted": "not contacted",
    "dominant_channel": "main channel",
    "known_gaps": "gaps",
    "document_text": "document",
    "form_fields": "form",
    "field_tags": "field tags",
    "run_summary": "run summary",
}


def plain_words(text: str) -> str:
    """Replace code names and any leftover underscores with plain words."""
    out = text
    for code, words in _CODE_WORDS.items():
        out = re.sub(rf"\b{re.escape(code)}\b", words, out)
    out = _BOLD.sub(lambda m: m.group(1) or m.group(2), out)
    return out.replace("_", " ")


def _words(text: str) -> int:
    return len(text.split())


def _blocks(text: str) -> tuple[str, list[str]]:
    """Split a reply into (lead, blocks). A block is one bullet or one quote."""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lead = ""
    blocks: list[str] = []
    prose: list[str] = []
    quote: list[str] = []

    def flush_quote() -> None:
        if quote:
            blocks.append("\n".join("> " + q for q in quote))
            quote.clear()

    for raw in lines:
        line = raw.strip()
        if not line or _TABLE_RULE.match(line):
            flush_quote()
            continue
        if line.startswith(">"):
            quote.append(line.lstrip("> ").strip())
            continue
        flush_quote()
        line = _HEADING.sub("", line)
        if "|" in line and line.count("|") >= 2:            # a table row: keep its words
            line = " · ".join(c.strip() for c in line.strip("|").split("|") if c.strip())
        if _BULLET.match(line):
            blocks.append("- " + _BULLET.sub("", line).strip())
        elif not lead and not blocks:
            lead = line
        else:
            prose.append(line)
    flush_quote()
    # Loose prose after the lead becomes bullets, one sentence each.
    for para in prose:
        for sentence in _SENTENCE.split(para):
            if sentence.strip():
                blocks.append("- " + sentence.strip())
    return lead, blocks


def _split_lead(lead: str) -> tuple[str, list[str]]:
    """A long lead keeps its first sentence; the rest become bullets."""
    sentences = [s for s in _SENTENCE.split(lead) if s.strip()]
    if len(sentences) <= 1:
        return lead, []
    return sentences[0].strip(), ["- " + s.strip() for s in sentences[1:]]


def format_answer(text: str, max_words: int = MAX_WORDS) -> str:
    """Normalise ``text`` into the answer layout (see the module docstring)."""
    if not isinstance(text, str) or not text.strip():
        return ""
    lead, blocks = _blocks(plain_words(text))
    if not lead and blocks and not blocks[0].startswith(">"):
        lead = blocks.pop(0)[2:]
    lead, extra = _split_lead(lead)
    blocks = extra + blocks

    words = _words(lead)
    if words > max_words:                      # one huge sentence: whole words only
        lead = " ".join(lead.split()[:max_words])
        words = max_words
    kept: list[str] = []
    bullets = 0
    for block in blocks:
        is_bullet = block.startswith("- ")
        if is_bullet and bullets >= MAX_BULLETS:
            continue
        n = _words(block.replace("> ", " ").replace("- ", " ", 1))
        if words + n > max_words:
            break                               # never cut a block; stop here
        kept.append(block)
        words += n
        bullets += 1 if is_bullet else 0
    # A caption bullet that introduced a draft is useless without its quote.
    if kept and kept[-1].startswith("- ") and kept[-1].rstrip().endswith(":"):
        kept.pop()
    parts = [lead] if lead else []
    out = "\n\n".join(parts)
    body = []
    for block in kept:
        if block.startswith(">"):
            body.append("\n" + block + "\n")
        else:
            body.append(block)
    if body:
        out += ("\n\n" if out else "") + "\n".join(body)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def word_count(text: str) -> int:
    """Words in a formatted answer, ignoring the bullet and quote marks."""
    return _words(re.sub(r"(?m)^\s*(?:- |> )", " ", text or ""))


def draft_block(channel: str, message: str) -> list[str]:
    """A caption bullet and a quote block for a drafted message."""
    message = re.sub(r"\s+", " ", message).strip()
    return [f"- {channel} draft, {len(message)} characters:", "> " + message]


def numbers_in(text: str) -> set[float]:
    """All numbers mentioned in ``text`` (thousands commas removed)."""
    return {float(m) for m in _NUMBER.findall(_THOUSANDS.sub("", text or ""))}


def unsupported_numbers(answer: str, payload: Any) -> list[str]:
    """Figures in ``answer`` that do not appear in ``payload``.

    Small counts (0 to 10) and the character count of a draft are allowed,
    because they describe the answer itself, not campaign facts.
    """
    allowed = numbers_in(json.dumps(payload, default=str, ensure_ascii=False))
    allowed |= {float(round(v)) for v in list(allowed)}
    allowed |= {round(v, 1) for v in list(allowed)}
    text = _CHAR_COUNT.sub(" ", answer or "")
    flagged = []
    for match in _NUMBER.finditer(_THOUSANDS.sub("", text)):
        value = float(match.group(0))
        if value <= 10 or value in allowed:
            continue
        if match.group(0) not in flagged:
            flagged.append(match.group(0))
    return flagged
