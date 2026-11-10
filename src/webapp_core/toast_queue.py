"""Pure toast-queue and one-shot flag helpers for the Part 8 UI effects.

Governs Requirement 5 (one-shot effects never replay on a rerun) and
Requirement 7.1 (Start/Done/Error toasts). This module will also hold the
toast queue itself (Toast, push, prune, trim to three); only
``consume_flag`` exists for now.

No Streamlit import: the session wiring lives in ``app/p8_effects.py``.
"""

from __future__ import annotations

from typing import Any, MutableMapping


def consume_flag(state: MutableMapping[str, Any], key: str) -> bool:
    """Return whether ``key`` was set in ``state`` and remove it.

    Implements the one-shot rule (Requirement 5.2): the render that reads a
    flag consumes it, so the key is gone afterwards and a later rerun sees
    ``False``. Missing keys return ``False``; other keys are untouched.
    """
    return bool(state.pop(key, False))
