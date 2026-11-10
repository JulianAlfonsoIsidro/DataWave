"""Pure timing helpers for the F2 Job_Button redesign (Part 8).

No Streamlit imports. ``app/p8_effects.py`` calls these and ``app/theme.py``
turns the results into markup.

- ``ring_phase`` gives the server-timed position of the running ring as a
  fraction of one lap, so a re-mounted ring continues where it was during a
  Job (Requirement 7.5) and the done/error ring starts from the line's current
  position (Requirement 7.8).
- ``is_duplicate_submit`` is the keyboard guard: a second activation of the
  same Job with the same inputs within ``DUPLICATE_WINDOW_S`` of the previous
  Job's end starts no second Job (Requirements 7.11, 7.12).

The lap length is not duplicated here; callers pass it (it mirrors the
``--pan-dur-ring-lap`` token).
"""

from __future__ import annotations

import math
from collections.abc import Mapping

# Requirement 7.12: window after a Job ends in which a same-input
# re-activation (Enter/Space or a queued click) is ignored.
DUPLICATE_WINDOW_S = 1.5


def ring_phase(started_at: float, now: float, lap_s: float) -> float:
    """Return ``((now - started_at) / lap_s) mod 1``, always in ``[0, 1)``.

    ``now`` before ``started_at`` (clock skew) is treated as zero elapsed time.
    Raises ``ValueError`` when ``lap_s <= 0``. Floating-point round-off that
    would give exactly 1.0 is folded back to 0.0 (Requirements 7.5, 7.8).
    """
    if not lap_s > 0:
        raise ValueError(f"lap_s must be > 0, got {lap_s!r}")
    elapsed = max(0.0, float(now) - float(started_at))
    phase = math.fmod(elapsed / lap_s, 1.0)
    if phase >= 1.0 or phase < 0.0:
        phase = 0.0
    return phase


def is_duplicate_submit(
    last_end: Mapping | None,
    signature: str,
    now: float,
    window_s: float = DUPLICATE_WINDOW_S,
) -> bool:
    """Return True when a click repeats the Job that just ended.

    True only when ``last_end`` exists, ``last_end["signature"] == signature``
    and ``0 <= now - last_end["ended_at"] <= window_s`` (Requirements 7.11,
    7.12). ``last_end`` is the job-end record
    ``{"ok", "started_at", "ended_at", "signature"}``.
    """
    if last_end is None:
        return False
    if last_end.get("signature") != signature:
        return False
    ended_at = last_end.get("ended_at")
    if ended_at is None:
        return False
    gap = float(now) - float(ended_at)
    return 0.0 <= gap <= window_s
