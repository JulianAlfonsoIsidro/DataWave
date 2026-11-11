"""Streamlit session wiring for the Part 8 UI effects.

Presentation only. Holds the session-state key names, the one-shot flag
helpers (Requirement 5), the Job_Button ring slot wiring of the F2 redesign
(Requirement 7: ring slot, phase continuity, job-end record, keyboard guard),
and the keyed ``p8_fx`` container that receives injected effect markup. Pure
logic lives in ``webapp_core.toast_queue`` and ``webapp_core.job_motion``;
this module adds no modelling.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from webapp_core.job_motion import is_duplicate_submit, ring_phase
from webapp_core.toast_queue import consume_flag

# --- Session-state keys (design: "Session-state keys") ---------------------
P8_TOASTS = "p8_toasts"
P8_TOAST_SEQ = "p8_toast_seq"
P8_ONESHOT_ANALYSIS = "p8_oneshot_analysis"
P8_ONESHOT_PERSONAS = "p8_oneshot_personas"
P8_ONESHOT_SUGGEST = "p8_oneshot_suggest"
P8_JOB_STARTED = "p8_job_started"  # {job: started_at}
P8_JOB_END = "p8_job_end"  # {job: {"ok", "started_at", "ended_at", "signature"}}
P8_NUM_PREV = "p8_num_prev"
P8_GROUP_PICKER = "p8_group_picker"
P8_GROUP_LAST = "p8_group_last"
P8_LAST_SPLIT = "p8_last_split"
P8_GROUP_PREV = "p8_group_prev"
# Generation per job: {job: {"id": str, "at": float}}, written when a Job
# succeeds. Reveals and count-ups play once per generation id and continue
# (negative delay) if a rerun lands while they play; never on later reruns.
P8_GEN = "p8_gen"
P8_GEN_SEQ = "p8_gen_seq"
# Card entrances: {card key: {"sig": content fingerprint, "at": when it changed}}
P8_CARD_SIGS = "p8_card_sigs"
_CARD_RUN_KEY = "p8_card_run"     # (run token, {key: count}, next stagger slot)
CARD_STAGGER_MAX = 9              # later cards start with the tenth

# Last job-end record per job, kept for the duplicate-submit guard. Unlike
# P8_JOB_END it is never popped, so the guard can compare after the done/error
# ring has been drawn (Requirements 7.11, 7.12).
P8_JOB_LAST_END = "p8_job_last_end"

# --- Container keys (not widget keys) --------------------------------------
P8_FX = "p8_fx"
P8_BTN_RUN_ANALYSIS = "p8_btn_run_analysis"
P8_BTN_BUILD_PERSONAS = "p8_btn_build_personas"
P8_GROUP_VISUAL = "p8_group_visual"

# "suggest" is the Personas page's "Suggest a number" scan: same loader,
# trace, fireworks and finish clock, its own dot motif.
_JOBS = ("analysis", "personas", "suggest")
_ONESHOT_KEYS = {"analysis": P8_ONESHOT_ANALYSIS, "personas": P8_ONESHOT_PERSONAS,
                 "suggest": P8_ONESHOT_SUGGEST}

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
    # The button itself stays static: the running/finishing line now lives
    # on the loader (theme.loader_html), so no ring is drawn here.
    return slot


def is_duplicate(job: str, signature: str) -> bool:
    """True when ``job`` with ``signature`` just ended (keyboard guard, Req 7.11, 7.12)."""
    _check_job(job)
    last_end = _store(P8_JOB_LAST_END).get(job)
    return is_duplicate_submit(last_end, signature, time.time())


def start_job(job: str, slot: Any) -> None:
    """Record the Job start (the loader shows the running line; ``slot`` is unused)."""
    _check_job(job)
    _store(P8_JOB_STARTED)[job] = time.time()


def job_elapsed(job: str) -> float:
    """Seconds since ``job`` started (0 when unknown)."""
    _check_job(job)
    started = _store(P8_JOB_STARTED).get(job)
    return max(0.0, time.time() - float(started)) if started is not None else 0.0


def job_phase(job: str) -> float:
    """Position of the loader's running line, as a fraction of one lap."""
    _check_job(job)
    return _phase_since(_store(P8_JOB_STARTED).get(job))


def _end_record(job: str, ok: bool, signature: str) -> dict:
    return {
        "ok": bool(ok),
        "started_at": _store(P8_JOB_STARTED).get(job),
        "ended_at": time.time(),
        "signature": signature,
    }


def end_job(job: str, ok: bool, signature: str, *, headline: str | None = None) -> None:
    """Write the job-end record consumed once by the next :func:`ring_slot`.

    Set before ``st.rerun()``; also updates the last-end store so the guard
    sees the Job that just ended. On success it also sets the job's One_Shot
    flag (Requirement 5.1); the completion render picks up the record to show
    the Completion_Toast and the finishing overlay once.
    """
    _check_job(job)
    record = _end_record(job, ok, signature)
    if headline:
        record["headline"] = headline       # the finishing overlay's headline
    _store(P8_JOB_END)[job] = record
    _store(P8_JOB_LAST_END)[job] = record
    if ok:
        set_oneshot(job)
        _new_generation(job, record["ended_at"])


def _new_generation(job: str, at: float) -> None:
    state = _state()
    seq = int(state.get(P8_GEN_SEQ, 0)) + 1
    state[P8_GEN_SEQ] = seq
    # The end time makes the id unique across sessions too (the iframe keeps
    # the last id it revealed in sessionStorage, which outlives a session).
    _store(P8_GEN)[job] = {"id": f"{job}-{seq}-{int(float(at) * 1000)}", "at": float(at)}


_WINDOW_CACHE: list[float] = []


def _reveal_window_s() -> float:
    """``--pan-reveal-window`` in seconds (cached); 2.4 s if unreadable."""
    if _WINDOW_CACHE:
        return _WINDOW_CACHE[0]
    value = None
    try:
        import theme

        value = _parse_duration_s(theme.token_pair("--pan-reveal-window")[0])
    except Exception:  # noqa: BLE001 - presentation fallback only
        value = None
    _WINDOW_CACHE.append(value if value is not None else 2.4)
    return _WINDOW_CACHE[0]


def generation(job: str) -> str | None:
    """The current generation id of ``job`` (None before its first success)."""
    _check_job(job)
    rec = _store(P8_GEN).get(job)
    return rec.get("id") if isinstance(rec, dict) else None


def reveal(job: str) -> tuple[float | None, str]:
    """``(reveal_el(job), generation id)``; ``(None, "")`` outside the window.

    Pass straight to ``theme.counting(*p8_effects.reveal(job))``.
    """
    el = reveal_el(job)
    return (el, generation(job) or "") if el is not None else (None, "")


def reveal_el(job: str) -> float | None:
    """Seconds since ``job``'s latest generation, while its reveal may play.

    ``None`` outside the window: the render is then plain and static, so a
    later rerun, tab switch or slider move never replays the reveal.
    """
    _check_job(job)
    rec = _store(P8_GEN).get(job)
    if not isinstance(rec, dict):
        return None
    el = time.time() - float(rec.get("at", 0.0))
    return el if 0.0 <= el < _reveal_window_s() else None


def fail_job_in_place(job: str, slot: Any, signature: str | None = None) -> None:
    """Draw the error ring in ``slot`` for an error that does not rerun.

    Records a last-end (``ok`` False) for the guard but no pending job-end
    record, since nothing will consume it later (Requirement 7.8).
    """
    _check_job(job)
    record = _end_record(job, False, signature if signature is not None else "")
    _store(P8_JOB_LAST_END)[job] = record


# --- p8_fx: one keyed effects container per run ------------------------------
#
# Children, always in this order so React keeps each element in place:
#   1. the page-lock component (zero height, decision A7)
#   2. the toast slot (st.empty, re-filled whenever a toast is pushed)
#   3. the finishing overlay, only on a completion render (design section l)

_LOCK_JS_PATH = Path(__file__).resolve().parent / "static" / "p8_page_lock.js"


def _run_token() -> Any:
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    ctx = get_script_run_ctx()
    return ctx.cursors if ctx is not None else None


def _page_lock_html(code: str) -> str:
    """Iframe markup that copies the lock script into the main page once.

    The script must live in the main page's own realm so it keeps working if
    the zero-height iframe is later re-created; the element id makes the copy
    idempotent across reruns.
    """
    return (
        "<script>(function(){try{var d=window.parent.document;"
        "if(d.getElementById('p8-page-lock'))return;"
        "var s=d.createElement('script');s.id='p8-page-lock';"
        f"s.textContent={json.dumps(code).replace('</', '<' + chr(92) + '/')};"
        "d.head.appendChild(s);}catch(e){}})();</script>"
    )


def _draw_page_lock() -> None:
    import streamlit.components.v1 as components

    try:
        code = _LOCK_JS_PATH.read_text(encoding="utf-8")
    except OSError:
        return  # the CSS click block still applies
    components.html(_page_lock_html(code), height=0)


def fx_container() -> Any:
    """Return the keyed ``p8_fx`` container, creating it at most once per run.

    Streamlit raises if a keyed container is created twice in one script run.
    Each run gets a fresh ``ScriptRunContext.cursors`` dict (``reset()``
    rebinds it), so that object is used as the run token. The token and the
    container are kept in session state; holding the token reference also
    prevents id reuse. Works the same whether ``main.py`` or only
    ``persona_page.render_persona_tab`` runs (AppTest).

    On creation it draws the page lock, the toast stack (adding the
    Completion_Toast of a Job that just succeeded) and, on that completion
    render only, the finishing overlay.
    """
    import streamlit as st

    token = _run_token()
    if token is None:
        return st.container(key=P8_FX)
    cached = st.session_state.get(_FX_CACHE_KEY)
    if cached is not None and cached[0] is token:
        return cached[1]
    container = st.container(key=P8_FX)
    with container:
        _draw_page_lock()
        toast_slot = st.empty()
    st.session_state[_FX_CACHE_KEY] = (token, container, toast_slot)

    finishing = _pick_up_completions()
    render_toasts()
    if finishing is not None:
        import theme

        with container:
            st.markdown(
                theme.finishing_overlay_html(
                    finishing, phase=job_phase(finishing), elapsed=job_elapsed(finishing),
                    headline=_FINISH_HEADLINE[0],
                ),
                unsafe_allow_html=True,
            )
    return container


def install_page_lock() -> None:
    """Make sure this run's ``p8_fx`` (which holds the page lock) exists."""
    fx_container()


# --- toasts (F3, Requirements 8, 9) ------------------------------------------

_TOAST_DELAY_CACHE: list[float] = []


def toast_delay_s() -> float:
    """Wait before a Completion_Toast enters: ring fill + half the sparks.

    Mirrors ``--pan-dur-ring-fill`` and ``--pan-dur-spark`` so the toast
    arrives as the button sparks fade (Requirement 7.7). Cached; 0.6 s if the
    tokens cannot be read.
    """
    if _TOAST_DELAY_CACHE:
        return _TOAST_DELAY_CACHE[0]
    value = 0.6
    try:
        import theme

        fill = _parse_duration_s(theme.token_pair("--pan-dur-ring-fill")[0])
        spark = _parse_duration_s(theme.token_pair("--pan-dur-spark")[0])
        if fill is not None and spark is not None:
            value = fill + spark / 2
    except Exception:  # noqa: BLE001 - presentation fallback only
        pass
    _TOAST_DELAY_CACHE.append(value)
    return value


def _queue() -> list:
    from webapp_core.toast_queue import Toast

    state = _state()
    value = state.get(P8_TOASTS)
    if not isinstance(value, list) or not all(isinstance(t, Toast) for t in value):
        value = []  # corrupted or wrong types: reset (design, Error Handling)
        state[P8_TOASTS] = value
    return value


def push_toast(job: str, kind: str, text: str, *, delay_s: float = 0.0) -> None:
    """Add a toast and redraw the stack straight away (it streams to the browser)."""
    from webapp_core.toast_queue import Toast, push

    _check_job(job)
    state = _state()
    seq = int(state.get(P8_TOAST_SEQ, 0)) + 1
    state[P8_TOAST_SEQ] = seq
    toast = Toast(id=f"t{seq}", job=job, kind=kind, text=text,
                  created_at=time.time(), delay_s=delay_s)
    state[P8_TOASTS] = push(_queue(), toast)
    render_toasts()


def render_toasts() -> None:
    """Draw the Toast_Stack into this run's toast slot, then settle the queue."""
    import theme
    from webapp_core.toast_queue import plan_view, prune, settle

    cached = _state().get(_FX_CACHE_KEY)
    if not cached or len(cached) < 3 or cached[0] is not _run_token():
        return
    now = time.time()
    queue = prune(_queue(), now)
    views = plan_view(queue, now)
    slot = cached[2]
    if views:
        slot.markdown(theme.toast_stack_html(views), unsafe_allow_html=True)
    else:
        slot.empty()
    _state()[P8_TOASTS] = settle(queue)


def _pick_up_completions() -> str | None:
    """Queue the Completion_Toast of a Job that just succeeded (once).

    Reads the pending job-end record (``ring_slot`` pops it later in the same
    run) and marks it, so the toast is queued exactly once per Job
    (Requirement 5.5). Returns the job whose finishing overlay to draw, or
    None. Errors queue nothing (Requirements 8.9, 8.10).
    """
    finishing = None
    for job in _JOBS:
        record = _store(P8_JOB_END).get(job)
        if not isinstance(record, dict) or record.get("toasted"):
            continue
        record["toasted"] = True
        if record.get("ok"):
            # No Completion_Toast for these flows: the loader's status line
            # already said it; the finishing overlay closes the loader.
            finishing = job
            _FINISH_HEADLINE[0] = record.get("headline")
    return finishing


_FINISH_HEADLINE: list = [None]


def start_toast(job: str, text: str) -> None:
    """Show the Start_Toast for a Job, before its blocking call (Req 8.8)."""
    fx_container()
    push_toast(job, "start", text)


# --- animated numbers (F5, Requirement 11) -----------------------------------

def number_prev(key: str, current: str) -> str | None:
    """Return the previously shown text of number ``key`` and store ``current``.

    ``None`` the first time a key renders (static, Requirement 11.3); after
    that, the stored text, which equals ``current`` on an unrelated rerun (all
    cells static, Requirement 11.5).
    """
    store = _store(P8_NUM_PREV)
    prev = store.get(key)
    store[key] = str(current)
    return prev if isinstance(prev, str) else None


# --- card entrances (Part 8 polish) -------------------------------------------

def card_motion(key: str, sig: str, group: str = "page") -> tuple[float, int, int] | None:
    """Whether the card ``key`` swoops in this render, and its stagger slot.

    A card swoops in when it is new or its content fingerprint ``sig``
    changed. Every card that changed in the same update takes the next slot
    in render (reading) order within its ``group`` (one per tab), so they
    arrive one by one: left, right, next row. Returns ``(seconds since it changed, slot, variant)`` while the entrance may
    still play (a rerun continues it with a negative delay), else None, and
    None outside a Streamlit run (unit tests render plain markup).
    """
    token = _run_token()
    if token is None:
        return None
    state = _state()
    run = state.get(_CARD_RUN_KEY)
    if not run or run[0] is not token:
        run = (token, {}, {})
        state[_CARD_RUN_KEY] = run
    seen = run[1]
    n = seen.get(key, 0)
    seen[key] = n + 1
    full_key = key if n == 0 else f"{key}#{n}"      # repeated headings stay apart
    store = _store(P8_CARD_SIGS)
    now = time.time()
    rec = store.get(full_key)
    if not isinstance(rec, dict) or rec.get("sig") != sig:
        slot = run[2].get(group, 0)
        # The variant flips on every change, so the card's class and its
        # animation name both change and the entrance always restarts.
        flip = 1 - int(rec.get("v", 1)) if isinstance(rec, dict) else 0
        rec = {"sig": sig, "at": now, "slot": min(slot, CARD_STAGGER_MAX), "v": flip}
        run[2][group] = slot + 1
        store[full_key] = rec
    el = now - float(rec["at"])
    if el >= _reveal_window_s():
        return None
    return el, int(rec.get("slot", 0)), int(rec.get("v", 0))


# --- quiet flash alerts (Requirement 8.14) -----------------------------------

_QUIET_COUNT_KEY = "p8_quiet_count"


def quiet_container(level: str) -> Any:
    """A keyed container that styles one success/warning flash quietly.

    Keys are unique within a run (a per-run counter), so several flashes can
    render in the same run. Text, role and trigger are unchanged.
    """
    import streamlit as st

    token = _run_token()
    count = st.session_state.get(_QUIET_COUNT_KEY)
    if not count or count[0] is not token:
        count = (token, 0)
    n = count[1] + 1
    st.session_state[_QUIET_COUNT_KEY] = (token, n)
    return st.container(key=f"p8_quiet_{level}_{n}")


def emit(markup: str) -> None:
    """Write trusted effect HTML into the ``p8_fx`` container.

    ``markup`` must be built by this app's own HTML builders, never from
    user data, because it is rendered with ``unsafe_allow_html=True``.
    """
    import streamlit as st

    with fx_container():
        st.markdown(markup, unsafe_allow_html=True)
