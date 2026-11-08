"""Shared Hypothesis strategies for the Part 7 (AI and finishing) tests.

Generators here cover the input spaces used by the eight Part 7 properties:

- ``payload_trees`` / ``private_payloads`` / ``leaky_payloads``: nested payloads
  for the Bedrock privacy guard (Property 1).
- ``card_dicts``: Part 4 decision-card dicts (Property 3).
- ``adb_series``: latest-ADB series with optional missing values (Property 4).
- ``baseline_frames``: non-excluded lead frames for the impact math (Property 5).
- ``campaign_profiles`` / ``past_campaign_profiles``: profiles for similarity
  scoring (Properties 7 and 8).

Import with ``from tests.strategies_part7 import ...``. Tests get ``src/`` on
the path from ``tests/conftest.py``; no ``sys.path`` handling lives here.
"""
from __future__ import annotations

import string
from datetime import date, timedelta

import numpy as np
import pandas as pd
from hypothesis import strategies as st

CHANNELS = ["In-app", "Email", "SMS"]
PRODUCT_TYPES = ["Savings", "Time Deposit", "Investment", "Credit Card"]
MECHANICS = ["TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE", "OTHER"]
SEGMENTS = ["Ready Toppers", "Untapped Wealth", "Willing but Stretched", "Not Now"]
CARD_ACTIONS = ["Prioritize", "Offer lower tier", "Include", "Skip"]
CHANNEL_COSTS = {"In-app": 0.5, "Email": 1.0, "SMS": 2.5}

_SAFE_ALPHABET = string.ascii_letters + " "
_CODE_ALPHABET = string.ascii_lowercase + "_"

# --------------------------------------------------------------------------- #
# Payload trees (Property 1)
# --------------------------------------------------------------------------- #

# Keys that never normalise to "clientid" and are not per-client record keys.
_safe_keys = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8).filter(
    lambda k: k != "clientid"
)
# Text that cannot match the client id pattern ``\bC\d{5,}\b``: no digits.
_safe_text = st.text(alphabet=_SAFE_ALPHABET, max_size=30)

_safe_leaf = st.one_of(
    _safe_text,
    st.integers(-1000, 1000),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.booleans(),
    st.none(),
)


def _extend_safe(children):
    return st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(_safe_keys, children, max_size=4),
    )


# Aggregate-only payloads: the guard must accept these.
private_payloads = st.recursive(_safe_leaf, _extend_safe, max_leaves=12)

payload_trees = private_payloads  # alias used by the spec wording

client_id_keys = st.sampled_from(
    ["client_id", "Client_ID", "CLIENT-ID", "clientId", "client id", "ClientID"]
)
client_id_values = st.integers(10_000, 9_999_999).map(lambda n: f"C{n}")
_record_keys = ["client_id", "p_join", "best_channel", "control"]


@st.composite
def per_client_record_lists(draw) -> list[dict]:
    """Two or more dicts that each carry a per-client record key."""
    n = draw(st.integers(2, 5))
    out = []
    for _ in range(n):
        key = draw(st.sampled_from(_record_keys[1:]))  # not client_id: separate rule
        out.append({key: draw(_safe_leaf)})
    return out


@st.composite
def leaky_payloads(draw):
    """A private payload with exactly one privacy violation injected."""
    base = draw(st.dictionaries(_safe_keys, _safe_leaf, max_size=3))
    kind = draw(st.sampled_from(["key", "value", "frame", "series", "records"]))
    if kind == "key":
        base[draw(client_id_keys)] = draw(_safe_leaf)
    elif kind == "value":
        base["note"] = f"see {draw(client_id_values)} for details"
    elif kind == "frame":
        base["data"] = pd.DataFrame({"x": [1, 2]})
    elif kind == "series":
        base["data"] = pd.Series([1, 2])
    else:
        base["rows"] = draw(per_client_record_lists())
    # Optionally nest the payload so the guard's recursion is exercised.
    if draw(st.booleans()):
        return {"outer": [base]}
    return base


# --------------------------------------------------------------------------- #
# Card dicts (Property 3)
# --------------------------------------------------------------------------- #

driver_codes = st.one_of(
    st.sampled_from(
        [
            "mechanic",
            "threshold_php",
            "spend_share_retail",
            "out_other_bank",
            "ndb_flag",
            "avg_contacts_per_month",
            "investment_propensity_decile",
            "digital_app_user",
            "latest_adb",
        ]
    ),
    st.text(alphabet=_CODE_ALPHABET, min_size=1, max_size=25).filter(
        lambda s: s.strip("_") != ""
    ),
)
exclusion_codes = st.one_of(
    st.sampled_from(["over_contacted", "ndb", "no reachable channel"]),
    st.text(alphabet=_CODE_ALPHABET + " ", min_size=1, max_size=20).filter(
        lambda s: s.strip(" _") != ""
    ),
)


@st.composite
def card_dicts(draw) -> dict:
    """A Part 4 card dict with ``low <= expected <= high`` joiner stats."""
    low = draw(st.floats(0, 500, allow_nan=False, allow_infinity=False))
    expected = low + draw(st.floats(0, 200, allow_nan=False, allow_infinity=False))
    high = expected + draw(st.floats(0, 200, allow_nan=False, allow_infinity=False))
    excluded = draw(
        st.dictionaries(exclusion_codes, st.integers(1, 500), max_size=4)
    )
    n_clients = draw(st.integers(0, 5000))
    return {
        "promo_id": draw(st.sampled_from(["P001", "P002", "NEW-001", "NEW-002"])),
        "segment": draw(st.sampled_from(SEGMENTS)),
        "n_clients": n_clients,
        "excluded_by_reason": excluded,
        "control_count": draw(st.integers(0, 100)),
        "sendable_count": draw(st.integers(0, max(n_clients, 1))),
        "top_drivers": draw(st.lists(driver_codes, min_size=0, max_size=5, unique=True)),
        "dominant_channel": draw(st.sampled_from(CHANNELS)),
        "expected_joiners": round(expected, 2),
        "joiners_90_low": round(low, 2),
        "joiners_90_high": round(high, 2),
        "total_channel_cost": draw(
            st.floats(0, 10_000, allow_nan=False, allow_infinity=False)
        ),
        "expected_value": draw(
            st.floats(0, 5_000_000, allow_nan=False, allow_infinity=False)
        ),
        "action": draw(st.sampled_from(CARD_ACTIONS)),
        "message_angle": draw(st.text(alphabet=_SAFE_ALPHABET, min_size=1, max_size=40)),
    }


# --------------------------------------------------------------------------- #
# ADB series (Property 4)
# --------------------------------------------------------------------------- #

pct_grid = st.sampled_from(list(range(5, 101, 5)))


@st.composite
def adb_series(draw, *, allow_missing: bool = True, min_size: int = 1) -> pd.Series:
    """Latest-ADB values indexed by client id; may include NaN."""
    n = draw(st.integers(min_size, 40))
    value = st.floats(0, 5_000_000, allow_nan=False, allow_infinity=False)
    if allow_missing:
        value = st.one_of(value, st.just(float("nan")))
    values = draw(st.lists(value, min_size=n, max_size=n))
    index = [f"C{100000 + i}" for i in range(n)]
    return pd.Series(values, index=index, name="latest_adb", dtype=float)


@st.composite
def all_missing_adb_series(draw) -> pd.Series:
    n = draw(st.integers(1, 10))
    return pd.Series(
        [float("nan")] * n,
        index=[f"C{100000 + i}" for i in range(n)],
        name="latest_adb",
        dtype=float,
    )


# --------------------------------------------------------------------------- #
# Baseline frames (Property 5)
# --------------------------------------------------------------------------- #


@st.composite
def baseline_frames(draw, *, min_size: int = 0, max_size: int = 40) -> pd.DataFrame:
    """Non-excluded leads: ``client_id, best_channel, p_join, control``."""
    n = draw(st.integers(min_size, max_size))
    p = draw(
        st.lists(
            st.floats(0, 1, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )
    ch = draw(st.lists(st.sampled_from(CHANNELS), min_size=n, max_size=n))
    ctrl = draw(st.lists(st.integers(0, 1), min_size=n, max_size=n))
    return pd.DataFrame(
        {
            "client_id": [f"C{100000 + i}" for i in range(n)],
            "best_channel": pd.Series(ch, dtype=object),
            "p_join": np.array(p, dtype=float),
            "control": np.array(ctrl, dtype=int),
        }
    )


@st.composite
def frame_and_subset(draw, **kwargs) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A baseline frame and an arbitrary subset of its rows (the recommended set)."""
    frame = draw(baseline_frames(**kwargs))
    mask = draw(
        st.lists(st.booleans(), min_size=len(frame), max_size=len(frame))
    )
    return frame, frame[np.array(mask, dtype=bool)] if len(frame) else frame


# --------------------------------------------------------------------------- #
# Campaign profiles (Properties 7 and 8)
# --------------------------------------------------------------------------- #

_dates = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))
_optional = lambda s: st.one_of(st.none(), s)  # noqa: E731


@st.composite
def campaign_profiles(draw) -> dict:
    """A New Promo profile; any component may be missing (None)."""
    start = draw(_dates)
    end = start + timedelta(days=draw(st.integers(0, 365)))
    return {
        "promo_id": draw(st.sampled_from(["NEW-001", "NEW-002"])),
        "product_type": draw(_optional(st.sampled_from(PRODUCT_TYPES))),
        "mechanic": draw(_optional(st.sampled_from(MECHANICS))),
        "threshold_php": draw(
            _optional(st.floats(1_000, 5_000_000, allow_nan=False, allow_infinity=False))
        ),
        "channels": draw(
            _optional(st.lists(st.sampled_from(CHANNELS), min_size=1, max_size=3, unique=True))
        ),
        "reward": draw(_optional(st.text(alphabet=_SAFE_ALPHABET, min_size=1, max_size=30))),
        "start_date": draw(_optional(st.just(start))),
        "end_date": draw(_optional(st.just(end))),
    }


@st.composite
def past_campaign_profiles(draw) -> dict:
    """A past campaign row with a score slot and a unique-ish promo id."""
    p = draw(campaign_profiles())
    p["promo_id"] = "P" + draw(st.integers(1, 999)).__str__().zfill(3)
    p["score"] = draw(
        st.one_of(
            st.none(),
            st.floats(0, 100, allow_nan=False, allow_infinity=False).map(lambda x: round(x, 1)),
        )
    )
    return p


@st.composite
def date_ranges(draw) -> tuple[date, date]:
    """A start date and an end date at or after it."""
    start = draw(_dates)
    return start, start + timedelta(days=draw(st.integers(0, 2000)))
