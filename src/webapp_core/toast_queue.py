"""Pure toast-queue and one-shot flag helpers for the Part 8 UI effects.

Governs Requirement 5 (one-shot effects never replay on a rerun) and
Requirement 8 (the bottom-right Toast_Stack: at most three visible, 4 s life,
oldest evicted, no replay across ``st.rerun()``).

No Streamlit import: the session wiring lives in ``app/p8_effects.py`` and the
markup in ``app/theme.py``. Times are server ``time.time()`` seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, MutableMapping, Sequence

# Toast life in seconds: 0.21 s enter, 3.78 s hold, 0.21 s exit (mirrors the
# ``--pan-dur-toast`` token). Dismissal starts 3.99 s after appearing, inside
# the 4 s +/- 0.25 s window of Requirement 8.5.
LIFE_S = 4.2
ENTER_S = 0.21
MAX_VISIBLE = 3

ALL_LEADS_TEXT = "Building personas for all leads..."


@dataclass(frozen=True)
class Toast:
    """One notification. ``kind`` is ``"start"`` or ``"done"``."""

    id: str
    job: Literal["analysis", "personas"]
    kind: Literal["start", "done"]
    text: str
    created_at: float
    # Seconds the toast waits before its entry (a completion toast enters as
    # the button sparks fade). Its life of LIFE_S starts after the wait.
    delay_s: float = 0.0


@dataclass(frozen=True)
class ToastView:
    """How one toast is drawn in this render.

    ``slot`` 0 is the newest (front, bottom-most); ``elapsed_s`` drives the
    negative animation delay so a rerun continues the toast where it was (it
    is negative while a delayed toast still waits for its entry);
    ``evicting`` marks the overflow toast that fades out this render.
    """

    toast: Toast
    slot: int
    elapsed_s: float
    evicting: bool


def push(queue: Sequence[Toast], toast: Toast) -> list[Toast]:
    """Return a new queue with ``toast`` appended (the input is not modified)."""
    return [*queue, toast]


def prune(queue: Sequence[Toast], now: float) -> list[Toast]:
    """Drop every toast whose age is at or above :data:`LIFE_S` (Req 8.5)."""
    return [t for t in queue if _age(t, now) < LIFE_S]


def _age(toast: Toast, now: float) -> float:
    """Seconds since the toast's entry began (negative while it waits)."""
    return now - toast.created_at - toast.delay_s


def _newest_first(queue: Sequence[Toast]) -> list[Toast]:
    # Stable: among equal times the later-pushed toast counts as newer.
    indexed = list(enumerate(queue))
    indexed.sort(key=lambda p: (p[1].created_at, p[0]), reverse=True)
    return [t for _, t in indexed]


def plan_view(queue: Sequence[Toast], now: float) -> tuple[ToastView, ...]:
    """Views for the live toasts, newest first (Requirements 8.3, 8.4).

    Expired toasts are left out. The newest :data:`MAX_VISIBLE` get slots
    0..2; anything older is marked ``evicting`` so it fades out once.
    """
    views: list[ToastView] = []
    for slot, toast in enumerate(_newest_first(prune(queue, now))):
        elapsed = _age(toast, now)
        views.append(ToastView(toast, slot, elapsed, slot >= MAX_VISIBLE))
    return tuple(views)


def settle(queue: Sequence[Toast]) -> list[Toast]:
    """Keep only the newest :data:`MAX_VISIBLE` toasts, in their queue order.

    Applied after a render has drawn the evicting fade, so the evicted toast is
    never drawn again (Requirement 8.4).
    """
    keep = {id(t) for t in _newest_first(queue)[:MAX_VISIBLE]}
    return [t for t in queue if id(t) in keep]


def start_text(job: str, label: str | Sequence[str]) -> str:
    """Start_Toast text (Requirement 8.8).

    ``analysis``: ``label`` is the Promo ID. ``personas``: ``label`` is the
    display label(s) of the selected split columns in selection order; empty
    means no split.
    """
    if job == "analysis":
        return f"Running analysis for {label}..."
    labels = [label] if isinstance(label, str) else list(label)
    labels = [str(x) for x in labels if str(x)]
    if not labels:
        return ALL_LEADS_TEXT
    return f"Building personas by {', '.join(labels)}..."


DONE_TEXT = {"analysis": "Analysis complete", "personas": "Personas ready"}


def consume_flag(state: MutableMapping[str, Any], key: str) -> bool:
    """Return whether ``key`` was set in ``state`` and remove it.

    Implements the one-shot rule (Requirement 5.2): the render that reads a
    flag consumes it, so the key is gone afterwards and a later rerun sees
    ``False``. Missing keys return ``False``; other keys are untouched.
    """
    return bool(state.pop(key, False))
