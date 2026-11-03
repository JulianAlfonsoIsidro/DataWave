"""Property-based tests for the Part 6 privacy and length guardrails.

# Feature: part6-assistant, Property 4: scrub_privacy removes every client-id-shaped token and is idempotent
# Feature: part6-assistant, Property 5: cap_length yields at most ~max_words words

Covers two guardrail properties of the part6-assistant spec, exercising the pure
helpers in :mod:`assistant.guardrails`:

- **Property 4 (privacy):** ``scrub_privacy`` strips every ``client_id``-shaped
  token (a "C" followed by digits, e.g. ``C100000``) from any text, replacing it
  with a placeholder, and is idempotent so a second pass is a no-op. Promo ids
  ("P" + digits) are left untouched. Validates Requirements 5.1, 5.2, 6.3, 7.9.
- **Property 5 (length):** ``cap_length`` trims a reply to roughly ``max_words``
  words (the appended ellipsis may count as one extra token), and leaves text
  already within the cap unchanged. Validates Requirement 5.4.

The client-id detector used to *check* the scrubbed output is a separately
compiled regex, not the production object, so a divergence signals a real bug
rather than a shared mistake.
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from assistant.guardrails import cap_length, scrub_privacy

# Independent client-id matcher (compiled here, not reused from guardrails).
# A "C" followed by one or more digits on a word boundary, matched
# case-insensitively exactly like the production scrubber.
_CLIENT_ID_CHECK = re.compile(r"\bC\d+\b", re.IGNORECASE)

# Independent promo-id matcher used to confirm promo ids survive scrubbing.
_PROMO_ID_CHECK = re.compile(r"\bP\d+\b", re.IGNORECASE)

# Arbitrary "filler" words that never contain a client-id-shaped token. Short
# alpha tokens keep the composed text readable and keep the token boundaries
# clean so the embedded ids are the only C-digit shapes present.
_FILLER_WORDS = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz ",
    min_size=0,
    max_size=20,
)


@st.composite
def text_with_client_ids(draw: st.DrawFn) -> tuple[str, list[str]]:
    """Compose a string mixing arbitrary words with client-id-shaped tokens.

    Returns ``(text, client_ids)`` where ``client_ids`` is the non-empty list of
    tokens (shaped ``C`` + digits) actually embedded, so the test knows client
    ids were present before scrubbing.
    """
    client_ids = draw(
        st.lists(
            st.builds(lambda n: f"C{n}", st.integers(min_value=0, max_value=9_999_999)),
            min_size=1,
            max_size=5,
        )
    )

    # Interleave filler words around each client id so tokens stay on word
    # boundaries (guaranteed by surrounding spaces).
    parts: list[str] = []
    for client_id in client_ids:
        parts.append(draw(_FILLER_WORDS))
        parts.append(client_id)
    parts.append(draw(_FILLER_WORDS))

    text = " ".join(part for part in parts if part != "")
    return text, client_ids


@settings(max_examples=300, deadline=None)
@given(text_with_client_ids())
def test_scrub_privacy_removes_all_client_ids(payload: tuple[str, list[str]]):
    """No client-id-shaped token survives ``scrub_privacy`` (Property 4a).

    **Validates: Requirements 5.1, 5.2, 6.3, 7.9**
    """
    text, client_ids = payload

    # Precondition: the composed text really did contain client-id shapes.
    assert _CLIENT_ID_CHECK.search(text) is not None
    assert client_ids

    scrubbed = scrub_privacy(text)

    # Postcondition: no client-id-shaped token remains anywhere in the output.
    assert _CLIENT_ID_CHECK.search(scrubbed) is None


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=400))
def test_scrub_privacy_is_idempotent(text: str):
    """Scrubbing twice equals scrubbing once (Property 4b).

    **Validates: Requirements 5.1, 5.2, 6.3, 7.9**
    """
    once = scrub_privacy(text)
    twice = scrub_privacy(once)
    assert twice == once

    # And a single pass already leaves nothing to redact.
    assert _CLIENT_ID_CHECK.search(once) is None


@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.builds(lambda n: f"P{n:03d}", st.integers(min_value=1, max_value=999)),
        min_size=1,
        max_size=4,
    )
)
def test_scrub_privacy_preserves_promo_ids(promo_ids: list[str]):
    """Promo ids ("P" + digits) are not treated as client ids (Property 4).

    **Validates: Requirements 5.1, 5.2**
    """
    text = "promo " + " and ".join(promo_ids)
    scrubbed = scrub_privacy(text)

    # Every promo id survives untouched and no redaction happened.
    for promo_id in promo_ids:
        assert promo_id in scrubbed
    assert _CLIENT_ID_CHECK.search(scrubbed) is None


@settings(max_examples=300, deadline=None)
@given(
    st.text(max_size=2000),
    st.integers(min_value=1, max_value=200),
)
def test_cap_length_respects_word_cap(text: str, max_words: int):
    """``cap_length`` keeps the result within ``max_words`` (+ ellipsis) words.

    **Validates: Requirements 5.4**
    """
    result = cap_length(text, max_words=max_words)

    # The appended ellipsis token (" …") may count as one additional word, so
    # the cap is max_words + 1.
    assert len(result.split()) <= max_words + 1


@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
        min_size=0,
        max_size=120,
    )
)
def test_cap_length_leaves_short_text_unchanged(words: list[str]):
    """Text already within the cap is returned unchanged (Property 5).

    **Validates: Requirements 5.4**
    """
    text = " ".join(words)
    max_words = 120

    # Precondition: the text is at or under the cap.
    assert len(text.split()) <= max_words

    assert cap_length(text, max_words=max_words) == text
