"""Mask personal details in campaign text before it leaves the app.

Pure, no Streamlit (spec part9-layout-fixes, Requirement 37.2). Used before
every extraction, Bedrock or built-in, so the text kept for the assistant is
masked too. Masks, in this order:

- email addresses -> ``[email]``
- phone numbers (Philippine mobile and landline shapes, and international
  ``+`` numbers) -> ``[phone]``
- any other run of 10 or more digits (account or card numbers, ids) ->
  ``[number]``

Amounts such as ``530,000`` or ``PHP 1,500,000`` are kept, because they are
campaign facts the form needs (they have separators, so they never form a
10-digit run). The result says how many items of each kind were masked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(
    r"(?<![\w])(?:\+?63[\s-]?|0)9\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d)"   # PH mobile
    r"|(?<![\w])\(?0?2\)?[\s-]?\d{4}[\s-]?\d{4}(?!\d)"                 # Metro Manila landline
    r"|(?<![\w])\+\d{1,3}[\s-]?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}(?!\d)"  # international
)
_LONG_DIGITS = re.compile(r"(?<!\d)\d{10,}(?!\d)")


@dataclass(frozen=True)
class MaskResult:
    """The masked text and how many items of each kind were replaced."""

    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def mask_pii(text: str) -> MaskResult:
    """Replace emails, phone numbers and long digit strings; count each kind."""
    value = text if isinstance(text, str) else ""
    counts = {"email": 0, "phone": 0, "number": 0}
    for kind, pattern in (("email", _EMAIL), ("phone", _PHONE), ("number", _LONG_DIGITS)):
        value, n = pattern.subn(f"[{kind}]", value)
        counts[kind] = n
    return MaskResult(value, counts)


def masked_note(result: MaskResult) -> str:
    """One plain line for the page: what was masked before sending."""
    if result.total == 0:
        return "No phone numbers, email addresses or long numbers were found to mask."
    parts = []
    for kind, word in (("phone", "phone number"), ("email", "email address"), ("number", "long number")):
        n = result.counts.get(kind, 0)
        if n:
            parts.append(f"{n} {word}{'' if n == 1 else 's'}")
    return "Masked before sending: " + ", ".join(parts) + "."
