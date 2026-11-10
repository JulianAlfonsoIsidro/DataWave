"""Streamlit session wiring for the Part 8 UI effects.

Presentation only. Holds the session-state key names, the one-shot flag
helpers (Requirement 5), the Job_Button ring slot wiring of the F2 redesign
(Requirement 7: ring slot, phase continuity, job-end record, keyboard guard),
and the keyed ``p8_fx`` container that receives injected effect markup. Pure
logic lives in ``webapp_core.toast_queue`` and ``webapp_core.job_motion``;
this module adds no modelling.
"""

from __future__ import annotations

import re
import time
from typing import Any

from webapp_core.job_motion import is_duplicate_submit, ring_phase
from webapp_core.toast_queue import consume_flag

# --- Session-state keys (design: "Session-state keys") ---------------------
P8_TOASTS = "p8_toasts"
P8_TOAST_SEQ = "p8_toast_seq"
P8_ONESHOT_ANALYSIS = "p8_oneshot_analysis"
P8_ONESHOT_PERSONAS = "p8_oneshot_personas"
P8_JOB_STARTED = "p8_job_started"  # {job: started_at}
P8_JOB_END = "p8_job_end"  # {job: {"ok", "started_at", "ended_at", "signature"}}
P8_NUM_PREV = "p8_num_prev"
P8_GROUP_PICKER = "p8_group_picker"
P8_GROUP_LAST = "p8_group_last"
P8_LAST_SPLIT = "p8_last_split"
P8_GROUP_PREV = "p8_group_prev"

# Last job-end record per job, kept for the duplicate-submit guard. Unlike
# P8_JOB_END it is never popped, so the guard can compare after the done/error
# ring has been drawn (Requirements 7.11, 7.12).
P8_JOB_LAST_END = "p8_job_last_end"

# --- Container keys (not widget keys) --------------------------------------
P8_FX = "p8_fx"
P8_BTN_RUN_ANALYSIS = "p8_btn_run_analysis"
P8_BTN_BUILD_PERSONAS = "p8_btn_build_personas"
P8_GROUP_VISUAL = "p8_group_visual"

_JOBS = ("analysis", "personas")
_ONESHOT_KEYS = {"analysis": P8_ONESHOT_ANALYSIS, "personas": P8_ONESHOT_PERSONAS}

# Session-state slot holding (run token, container) for the current run.
_FX_CACHE_KEY = "p8_fx_cache"

# Lap length used when the ``--pan-dur-ring-lap`` token cannot be read.
_DEFAULT_LAP_S = 1.4
_LAP_CACHE: list[float] = []
_DURATION_RE = re.compile(r"\s*([0-9]*\.?[0-9]+)\s*(ms|s)\s*")


def _key_for(table: dict[str, str], job: str) -> str:
    if job not in table:
        raise ValueError(f"job must be one of {_JOBS}, got {job!r}")
    return table[job]


def _check_job(job: str) -> None:
    if job not in _JOBS:
        raise ValueError(f"job must be one of {_JOBS}, got {job!r}")


def _state() -> Any:
    import streamlit as st

    return st.session_state


def _store(key: str) -> dict:
    """Return the per-job dict stored under ``key``, creating it if missing."""
    state = _state()
    value = state.get(key)
    if not isinstance(value, dict):
        value = {}
        state[key] = value
    return value


def set_oneshot(job: str) -> None:
    """Mark that ``job`` succeeded so the next render plays its effect once."""
    _state()[_key_for(_ONESHOT_KEYS, job)] = True


def consume_oneshot(job: str) -> bool:
    """Return True once after ``set_oneshot(job)``, then False (Requirement 5.2)."""
    return consume_flag(_state(), _key_for(_ONESHOT_KEYS, job))


# --- F2 redesign: Job_Button ring (Requirement 7) --------------------------

def _parse_duration_s(text: str) -> float | None:
    """Parse ``"1400ms"`` or ``"1.4s"`` into seconds; None when unparseable."""
    m = _DURATION_RE.fullmatch(str(text))
    if not m:
        return None
    value = float(m.group(1))
    seconds = value / 1000.0 if m.group(2) == "ms" else value
    return seconds if seconds > 0 else None


def ring_lap_s() -> float:
    """Return one running-ring lap in seconds from ``--pan-dur-ring-lap`` (cached).

    Reads the light value through ``theme.token_pair`` so the server-side phase
    matches the CSS lap (Requirement 7.5). Falls back to 1.4 s when the token
    cannot be read or parsed, so a token problem never breaks a Job.
    """
    if _LAP_CACHE:
        return _LAP_CACHE[0]
    lap = None
    try:
        import theme

        lap = _parse_duration_s(theme.token_pair("--pan-dur-ring-lap")[0])
    except Exception:  # noqa: BLE001 - presentation fallback only
        lap = None
    _LAP_CACHE.append(lap if lap is not None else _DEFAULT_LAP_S)
    return _LAP_CACHE[0]


def _phase_since(started_at: float | None) -> float:
    if started_at is None:
        return 0.0
    return ring_phase(float(started_at), time.time(), ring_lap_s())


def _draw(slot: Any, state: str, phase: float) -> None:
    import theme

    slot.markdown(theme.job_ring_html(state, phase), unsafe_allow_html=True)


def ring_slot(job: str) -> Any:
    """Create the ring slot for ``job`` and draw a pending done/error ring once.

    Call inside the Job's keyed container, before the button. When a job-end
    record is pending (set by :func:`end_job` before ``st.rerun()``), it is
    popped so the done/error ring plays once (Requirements 7.7, 7.8), starting
    from the line's position when the Job ended. The record stays in the
    last-end store for :func:`is_duplicate`.
    """
    import streamlit as st

    _check_job(job)
    slot = st.empty()
    pending = _store(P8_JOB_END).pop(job, None)
    if isinstance(pending, dict):
        _store(P8_JOB_LAST_END)[job] = pending
        # The browser's running line keeps looping until this run replaces it,
        # so the done/error ring starts from the phase at "now".
        phase = _phase_since(pending.get("started_at"))
        _draw(slot, "done" if pending.get("ok") else "error", phase)
    return slot


def is_duplicate(job: str, signature: str) -> bool:
    """True when ``job`` with ``signature`` just ended (keyboard guard, Req 7.11, 7.12)."""
    _check_job(job)
    last_end = _store(P8_JOB_LAST_END).get(job)
    return is_duplicate_submit(last_end, signature, time.time())


def start_job(job: str, slot: Any) -> None:
    """Record the Job start and draw the running ring in ``slot`` (Requirement 7.2)."""
    _check_job(job)
    _store(P8_JOB_STARTED)[job] = time.time()
    _draw(slot, "running", 0.0)


def _end_record(job: str, ok: bool, signature: str) -> dict:
    return {
        "ok": bool(ok),
        "started_at": _store(P8_JOB_STARTED).get(job),
        "ended_at": time.time(),
        "signature": signature,
    }


def end_job(job: str, ok: bool, signature: str) -> None:
    """Write the job-end record consumed once by the next :func:`ring_slot`.

    Set before ``st.rerun()``; also updates the last-end store so the guard
    sees the Job that just ended.
    """
    _check_job(job)
    record = _end_record(job, ok, signature)
    _store(P8_JOB_END)[job] = record
    _store(P8_JOB_LAST_END)[job] = record


def fail_job_in_place(job: str, slot: Any, signature: str | None = None) -> None:
    """Draw the error ring in ``slot`` for an error that does not rerun.

    Records a last-end (``ok`` False) for the guard but no pending job-end
    record, since nothing will consume it later (Requirement 7.8).
    """
    _check_job(job)
    record = _end_record(job, False, signature if signature is not None else "")
    _store(P8_JOB_LAST_END)[job] = record
    _draw(slot, "error", _phase_since(record["started_at"]))


def fx_container() -> Any:
    """Return the keyed ``p8_fx`` container, creating it at most once per run.

    Streamlit raises if a keyed container is created twice in one script run.
    Each run gets a fresh ``ScriptRunContext.cursors`` dict (``reset()``
    rebinds it), so that object is used as the run token. The token and the
    container are kept in session state; holding the token reference also
    prevents id reuse. When no script run context exists (bare import), a
    new container is returned each call. Works the same whether ``main.py``
    or only ``persona_page.render_persona_tab`` runs (AppTest).
    """
    import streamlit as st
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    ctx = get_script_run_ctx()
    if ctx is None:
        return st.container(key=P8_FX)
    token = ctx.cursors
    cached = st.session_state.get(_FX_CACHE_KEY)
    if cached is not None and cached[0] is token:
        return cached[1]
    container = st.container(key=P8_FX)
    st.session_state[_FX_CACHE_KEY] = (token, container)
    return container


def emit(markup: str) -> None:
    """Write trusted effect HTML into the ``p8_fx`` container.

    ``markup`` must be built by this app's own HTML builders, never from
    user data, because it is rendered with ``unsafe_allow_html=True``.
    """
    import streamlit as st

    with fx_container():
        st.markdown(markup, unsafe_allow_html=True)
