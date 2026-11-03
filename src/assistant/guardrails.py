"""Privacy, scope, and length guardrails for assistant replies.

These are pure, UI-free helpers shared by both the Mock and Bedrock drivers:

- ``is_in_scope`` decides whether a question is about the promo campaign
  (Requirement 5.3). Out-of-scope questions get the fixed ``OUT_OF_SCOPE_REDIRECT``.
- ``scrub_privacy`` is a defense-in-depth pass that removes any ``client_id``-shaped
  token from text before it is returned or logged (Requirements 5.1, 5.2, 6.3, 7.9).
  It is idempotent: ``scrub_privacy(scrub_privacy(x)) == scrub_privacy(x)``.
- ``cap_length`` trims a reply to roughly ``max_words`` words with an ellipsis
  (Requirement 5.4).
"""

from __future__ import annotations

import re

# Fixed polite redirect returned for out-of-scope questions in both drivers
# (Requirement 5.3).
OUT_OF_SCOPE_REDIRECT = (
    "I can only help with questions about this promo campaign — segments, "
    "thresholds, expected joiners, and past-promo accuracy. Try one of the "
    "suggested questions."
)

# Placeholder substituted for any client-id-shaped token.
REDACTION_PLACEHOLDER = "[redacted]"

# The four Part 3 segment labels (campaign vocabulary).
_SEGMENT_LABELS = (
    "ready toppers",
    "willing but stretched",
    "untapped wealth",
    "not now",
)

# Plain campaign-vocabulary keywords that keep a question in scope.
_SCOPE_KEYWORDS = (
    "promo",
    "threshold",
    "joiners",
    "segment",
    "card",
    "channel",
    "what if",
    "accurate",
    "actual",
)

# A promo-id pattern such as ``P001`` keeps a question in scope.
_PROMO_ID_RE = re.compile(r"\bP\d{3,}\b", re.IGNORECASE)

# A client-id-shaped token such as ``C100000`` (see data/customer_dna.csv:
# client_id is "C" followed by digits). Matched case-insensitively and scrubbed.
_CLIENT_ID_RE = re.compile(r"\bC\d+\b", re.IGNORECASE)


def is_in_scope(question: str) -> bool:
    """Return True only when the question contains campaign vocabulary.

    Vocabulary includes the four segment labels, the plain keywords in
    ``_SCOPE_KEYWORDS`` (promo, threshold, joiners, segment, card, channel,
    "what if", accurate/actual), and a promo-id pattern like ``P001``. The check
    is case-insensitive (Requirement 5.3).
    """
    if not question:
        return False

    lowered = question.lower()

    if any(label in lowered for label in _SEGMENT_LABELS):
        return True
    if any(keyword in lowered for keyword in _SCOPE_KEYWORDS):
        return True
    if _PROMO_ID_RE.search(question):
        return True
    return False


def scrub_privacy(text: str) -> str:
    """Remove any ``client_id``-shaped token, replacing it with a placeholder.

    Client ids in this project are a "C" followed by digits (e.g. ``C100000``).
    This pass is idempotent because the placeholder ``[redacted]`` contains no
    client-id-shaped token, so a second call finds nothing left to replace
    (Requirements 5.1, 5.2, 6.3, 7.9).
    """
    if not text:
        return text
    return _CLIENT_ID_RE.sub(REDACTION_PLACEHOLDER, text)


def cap_length(text: str, max_words: int = 120) -> str:
    """Trim ``text`` to roughly ``max_words`` words, appending an ellipsis.

    Text already at or under the cap is returned unchanged, so capping an
    already-short reply is a no-op (Requirement 5.4).
    """
    if not text:
        return text

    words = text.split()
    if len(words) <= max_words:
        return text

    return " ".join(words[:max_words]) + " …"
