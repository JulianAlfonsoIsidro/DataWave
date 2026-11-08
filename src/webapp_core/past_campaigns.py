"""Past campaign loading, filtering, sorting, paging, and detail (Requirement 11).

Pure logic behind the smarter PAST PROMOS tab. It reads campaign metadata from
``data/promo_history.csv`` and lead outcomes from ``data/promo_leads.csv``
(Requirement 11.1), derives each campaign's audience segments from the leads
joined to ``data/customer_dna.csv``, and offers deterministic sort, filter, and
paging helpers.

The existing :func:`webapp_core.past_promos.predicted_vs_actual` logic is reused
unchanged (Requirements 11.17, 11.20); this module only re-exports it.

No Streamlit, Bedrock, LLM, embedding, or network imports (Requirement 11.19).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from webapp_core.past_promos import (  # noqa: F401  (reused unchanged, 11.17/11.20)
    predicted_vs_actual,
    read_sendable_ids_by_cell,
)
from webapp_core.similarity import (
    CampaignProfile,
    NewPromoProfile,
    SimilarityResult,
    duration_days,
    similarity,
)

# Sort modes (Requirement 11.2).
SORT_NEWEST = "Newest"
SORT_OLDEST = "Oldest"
SORT_MOST_SIMILAR = "Most Similar"
SORT_MODES: tuple[str, ...] = (SORT_NEWEST, SORT_OLDEST, SORT_MOST_SIMILAR)

FILTER_ALL = "All"
NOT_AVAILABLE = "Not Available"
NOT_ENOUGH_DATA = "Not Enough Data"

# Paging (Requirements 11.6, 11.7).
INITIAL_VISIBLE = 5
PAGE_STEP = 5

# A segment is part of a campaign's audience at this share of its leads.
AUDIENCE_SHARE_MIN = 0.10

_DEFAULT_HISTORY = Path("data/promo_history.csv")
_DEFAULT_LEADS = Path("data/promo_leads.csv")
_DEFAULT_DNA = Path("data/customer_dna.csv")


class PastCampaignsDataError(Exception):
    """A required input file is missing or unreadable; names the file (11.18)."""

    def __init__(self, path: Path | str, reason: str = "missing or unreadable") -> None:
        self.path = Path(path)
        super().__init__(f"Cannot load {self.path.name} ({reason}): {self.path}")


@dataclass(frozen=True)
class CampaignRow:
    """One list row: the campaign profile and its optional similarity result."""

    profile: CampaignProfile
    similarity: SimilarityResult | None = None


@dataclass(frozen=True)
class SegmentResponse:
    segment: str
    treated: int
    joined: int
    rate: float | None


@dataclass(frozen=True)
class CampaignDetail:
    """Detail view facts for one campaign (Requirements 11.15, 11.16)."""

    profile: CampaignProfile
    start: date | None
    end: date | None
    duration_days: int | None
    treated_leads: int
    joined: int
    opt_in_rate: float | None
    opt_in_display: str  # "12.3%" or "Not Available"
    segment_responses: tuple[SegmentResponse, ...]
    similarity: SimilarityResult | None


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _read_required(path: Path | str, **kwargs) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise PastCampaignsDataError(path, "file not found")
    try:
        return pd.read_csv(path, **kwargs)
    except Exception as exc:  # unreadable / malformed
        raise PastCampaignsDataError(path, f"unreadable: {exc}") from exc


def load_promo_history(path: Path | str = _DEFAULT_HISTORY) -> pd.DataFrame:
    """Load ``promo_history.csv``; raises naming the file when missing."""
    frame = _read_required(path, dtype={"promo_id": "object"})
    missing = {"promo_id", "start_date", "end_date"} - set(frame.columns)
    if missing:
        raise PastCampaignsDataError(path, f"missing columns {sorted(missing)}")
    return frame


def load_promo_leads(path: Path | str = _DEFAULT_LEADS) -> pd.DataFrame:
    """Load ``promo_leads.csv``; raises naming the file when missing."""
    frame = _read_required(path, dtype={"promo_id": "object", "client_id": "object"})
    missing = {"promo_id", "client_id", "control_group", "joined"} - set(frame.columns)
    if missing:
        raise PastCampaignsDataError(path, f"missing columns {sorted(missing)}")
    return frame


def load_customer_dna(path: Path | str = _DEFAULT_DNA) -> pd.DataFrame:
    """Load ``customer_dna.csv`` (audience derivation). Empty frame if absent."""
    p = Path(path)
    if not p.is_file():
        return pd.DataFrame(columns=["client_id", "segment"])
    try:
        return pd.read_csv(p, dtype={"client_id": "object"})
    except Exception:
        return pd.DataFrame(columns=["client_id", "segment"])


def load_all(
    history_path: Path | str = _DEFAULT_HISTORY,
    leads_path: Path | str = _DEFAULT_LEADS,
    dna_path: Path | str = _DEFAULT_DNA,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load history, leads, and DNA; any required-file failure raises, no partials."""
    history = load_promo_history(history_path)
    leads = load_promo_leads(leads_path)
    dna = load_customer_dna(dna_path)
    return history, leads, dna


# --------------------------------------------------------------------------
# Derivation
# --------------------------------------------------------------------------

def _to_date(value) -> date | None:
    ts = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(ts) else ts.date()


def _split_channels(value) -> tuple[str, ...]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ()
    return tuple(p.strip() for p in str(value).split(",") if p.strip())


def _text(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value)


def _treated(leads: pd.DataFrame) -> pd.DataFrame:
    control = pd.to_numeric(leads["control_group"], errors="coerce")
    return leads[control == 0]


def opt_in_rate(leads: pd.DataFrame) -> tuple[float | None, int, int]:
    """Return ``(rate, treated, joined)`` over treated leads (control_group == 0).

    ``rate`` is ``None`` when there are zero treated leads (Requirement 11.16).
    """
    treated = _treated(leads)
    n = int(len(treated))
    if n == 0:
        return None, 0, 0
    joined = int((pd.to_numeric(treated["joined"], errors="coerce").fillna(0) > 0).sum())
    return joined / n, n, joined


def format_opt_in(rate: float | None) -> str:
    """One-decimal percentage, or "Not Available" (Requirements 11.15, 11.16)."""
    return NOT_AVAILABLE if rate is None else f"{rate * 100:.1f}%"


def derive_audience_segments(
    campaign_leads: pd.DataFrame, dna: pd.DataFrame
) -> tuple[str, ...]:
    """Segments making up at least 10% of the campaign's leads (sorted)."""
    if campaign_leads.empty or dna.empty or not {"client_id", "segment"} <= set(dna.columns):
        return ()
    seg_by_client = dna.drop_duplicates("client_id").set_index(
        dna.drop_duplicates("client_id")["client_id"].astype(str)
    )["segment"]
    segs = campaign_leads["client_id"].astype(str).map(seg_by_client).dropna()
    if segs.empty:
        return ()
    shares = segs.value_counts() / len(campaign_leads)
    return tuple(sorted(str(s) for s, share in shares.items() if share >= AUDIENCE_SHARE_MIN))


def build_profiles(
    history: pd.DataFrame, leads: pd.DataFrame, dna: pd.DataFrame
) -> list[CampaignProfile]:
    """Build one :class:`CampaignProfile` per ``promo_history`` row."""
    leads = leads.copy()
    leads["promo_id"] = leads["promo_id"].astype(str)
    profiles: list[CampaignProfile] = []
    for rec in history.to_dict("records"):
        pid = str(rec["promo_id"])
        cl = leads[leads["promo_id"] == pid]
        rate, treated, _ = opt_in_rate(cl)
        thr = pd.to_numeric(rec.get("threshold_php"), errors="coerce")
        profiles.append(
            CampaignProfile(
                promo_id=pid,
                name=_text(rec.get("promo_name")),
                product_type=_text(rec.get("product_type")),
                mechanic=_text(rec.get("mechanic")),
                threshold_php=None if pd.isna(thr) else float(thr),
                reward=_text(rec.get("reward")),
                start=_to_date(rec.get("start_date")),
                end=_to_date(rec.get("end_date")),
                channels=_split_channels(rec.get("channels")),
                audience_segments=derive_audience_segments(cl, dna),
                opt_in_rate=rate,
                treated_leads=treated,
            )
        )
    return profiles


def build_rows(
    profiles: Sequence[CampaignProfile], current: NewPromoProfile | None = None
) -> list[CampaignRow]:
    """Wrap profiles as rows; scores are computed only when ``current`` exists (11.3)."""
    return [
        CampaignRow(p, similarity(current, p) if current is not None else None)
        for p in profiles
    ]


# --------------------------------------------------------------------------
# Sort / filter / page
# --------------------------------------------------------------------------

def similarity_available(rows: Sequence[CampaignRow]) -> bool:
    """True when any row carries a similarity result ("Most Similar" enabled)."""
    return any(r.similarity is not None for r in rows)


def _date_key(d: date | None, newest_first: bool) -> int:
    # Missing dates sort last in both directions.
    if d is None:
        return 10**9
    return -d.toordinal() if newest_first else d.toordinal()


def _score_key(row: CampaignRow) -> float:
    # Unscored ("Not Enough Data" or absent) sort after all scored rows.
    if row.similarity is None or row.similarity.score is None:
        return math.inf
    return -round(row.similarity.score, 9)


def sort_campaigns(rows: Sequence[CampaignRow], mode: str = SORT_NEWEST) -> list[CampaignRow]:
    """Deterministic sort independent of input order (Requirements 11.2, 11.13).

    "Newest" / "Oldest" order by ``start`` with ascending ``promo_id`` tiebreak.
    "Most Similar" orders by score descending (unscored last), then newest
    ``start``, then ascending ``promo_id``; it is only honored when a similarity
    score exists, otherwise it falls back to "Newest" (Requirement 11.3).
    """
    if mode == SORT_MOST_SIMILAR and similarity_available(rows):
        return sorted(
            rows,
            key=lambda r: (_score_key(r), _date_key(r.profile.start, True), r.profile.promo_id),
        )
    if mode == SORT_OLDEST:
        return sorted(rows, key=lambda r: (_date_key(r.profile.start, False), r.profile.promo_id))
    return sorted(rows, key=lambda r: (_date_key(r.profile.start, True), r.profile.promo_id))


def filter_options(rows: Sequence[CampaignRow]) -> tuple[list[str], list[str]]:
    """Product Type and Target Audience choices, each led by "All"."""
    products = sorted({r.profile.product_type for r in rows if r.profile.product_type})
    audiences = sorted({s for r in rows for s in r.profile.audience_segments})
    return [FILTER_ALL, *products], [FILTER_ALL, *audiences]


def filter_campaigns(
    rows: Sequence[CampaignRow],
    product_type: str = FILTER_ALL,
    audience: str = FILTER_ALL,
) -> list[CampaignRow]:
    """Apply the Product Type and Target Audience filters (Requirement 11.4)."""
    out = []
    for r in rows:
        if product_type != FILTER_ALL and r.profile.product_type != product_type:
            continue
        if audience != FILTER_ALL and audience not in r.profile.audience_segments:
            continue
        out.append(r)
    return out


def page(
    rows: Sequence[CampaignRow], visible: int = INITIAL_VISIBLE
) -> tuple[list[CampaignRow], bool]:
    """Return ``(shown, show_view_more)`` (Requirements 11.5, 11.6)."""
    visible = max(0, int(visible))
    shown = list(rows[:visible])
    return shown, len(rows) > visible


def next_visible(visible: int) -> int:
    """Visible count after one "View More" click."""
    return visible + PAGE_STEP


# --------------------------------------------------------------------------
# Detail
# --------------------------------------------------------------------------

def campaign_detail(
    row: CampaignRow, leads: pd.DataFrame, dna: pd.DataFrame
) -> CampaignDetail:
    """Detail facts for one campaign (Requirements 11.15, 11.16)."""
    p = row.profile
    cl = leads[leads["promo_id"].astype(str) == p.promo_id]
    rate, treated, joined = opt_in_rate(cl)

    responses: list[SegmentResponse] = []
    t = _treated(cl)
    if not t.empty and not dna.empty and {"client_id", "segment"} <= set(dna.columns):
        d = dna.drop_duplicates("client_id")
        seg = t["client_id"].astype(str).map(
            pd.Series(d["segment"].values, index=d["client_id"].astype(str))
        )
        j = pd.to_numeric(t["joined"], errors="coerce").fillna(0) > 0
        frame = pd.DataFrame({"segment": seg.values, "joined": j.values}).dropna(subset=["segment"])
        for name, grp in sorted(frame.groupby("segment"), key=lambda kv: str(kv[0])):
            n = int(len(grp))
            jn = int(grp["joined"].sum())
            responses.append(SegmentResponse(str(name), n, jn, jn / n if n else None))

    days = duration_days(p.start, p.end) if p.start and p.end else None
    return CampaignDetail(
        profile=p,
        start=p.start,
        end=p.end,
        duration_days=days,
        treated_leads=treated,
        joined=joined,
        opt_in_rate=rate,
        opt_in_display=format_opt_in(rate),
        segment_responses=tuple(responses),
        similarity=row.similarity,
    )


def display_score(result: SimilarityResult | None) -> str:
    """Whole-number score text, or "Not Enough Data" when no component is available."""
    if result is None:
        return ""
    if result.score is None:
        return NOT_ENOUGH_DATA
    return str(int(round(result.score)))


def prediction_comparison(
    promo_id: str,
    cards: Sequence[Mapping],
    leads: pd.DataFrame,
    leads_dir: Path | str = Path("outputs/leads"),
) -> list[dict]:
    """Predicted vs actual rows for one campaign, ``[]`` when no artifacts (11.17)."""
    mine = [c for c in cards if str(c.get("promo_id")) == promo_id]
    if not mine:
        return []
    ids = read_sendable_ids_by_cell(mine, leads_dir)
    return predicted_vs_actual(mine, leads, ids)
