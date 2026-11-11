"""Region_Mapping for the Part 8 region map (F6, Requirements 13, 14).

Pure: no Streamlit import, no file or session access, inputs never modified.
The four ``region`` data values are matched exactly and case-sensitively to
four Map_Areas. ``AREA_SHAPES`` (PSGC adm1 codes from faeldon/philippines-
json-maps v1.1.1) is used only by ``scripts/build_ph_regions.py`` to dissolve
each area into one outline; no region-level border or click exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

MAP_AREAS: tuple[str, ...] = ("NCR", "Luzon", "Visayas", "Mindanao")

# Map_Area -> PSGC region codes it is built from (outlines only, Gate 4).
AREA_SHAPES: dict[str, tuple[int, ...]] = {
    "NCR": (1300000000,),
    "Luzon": (1400000000, 100000000, 200000000, 300000000, 400000000, 1700000000, 500000000),
    "Visayas": (600000000, 700000000, 800000000, 1800000000),
    "Mindanao": (900000000, 1000000000, 1100000000, 1200000000, 1600000000, 1900000000),
}


@dataclass(frozen=True)
class MapAreaEntry:
    """One Map_Area for the current run."""

    region: str
    lead_count: int
    selectable: bool
    shape_codes: tuple[int, ...]


@dataclass(frozen=True)
class RegionMapResult:
    """Always the four areas in fixed order, plus unmatched data values."""

    entries: tuple[MapAreaEntry, ...]
    unmatched: tuple[str, ...]


def _valid_count(region: str, count: object) -> int:
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"invalid lead count {count!r} for region {region!r}")
    return count


def build_region_map(group_lead_counts: Iterable[tuple[str, int]]) -> RegionMapResult:
    """Map ``(region, lead_count)`` pairs onto the four Map_Areas (Req 14.2-14.7).

    Exact, case-sensitive matching ("ncr" or "Metro Manila" are unmatched).
    Absent areas get a count of 0 and are not selectable. A negative or
    non-integer count raises ``ValueError`` naming the region; nothing partial
    is returned. Repeated regions add up.
    """
    pairs = list(group_lead_counts)
    counts: dict[str, int] = {}
    unmatched: list[str] = []
    for region, count in pairs:
        value = _valid_count(str(region), count)
        if region in AREA_SHAPES:
            counts[region] = counts.get(region, 0) + value
        elif region not in unmatched:
            unmatched.append(region)
    entries = tuple(
        MapAreaEntry(area, counts.get(area, 0), counts.get(area, 0) > 0, AREA_SHAPES[area])
        for area in MAP_AREAS
    )
    return RegionMapResult(entries, tuple(unmatched))


def area_label(entry: MapAreaEntry) -> str:
    """The aria-label text, e.g. ``"Visayas, 362 leads"`` (Requirement 13.6)."""
    noun = "lead" if entry.lead_count == 1 else "leads"
    return f"{entry.region}, {entry.lead_count:,} {noun}"


def shape_owner(code: int) -> str | None:
    """The Map_Area that owns a PSGC region code, or None (Requirement 14.3)."""
    for area, codes in AREA_SHAPES.items():
        if code in codes:
            return area
    return None


def unassigned_shape_codes(source_codes: Iterable[int]) -> tuple[int, ...]:
    """Source codes that no Map_Area owns, in input order without repeats."""
    out: list[int] = []
    for code in source_codes:
        if shape_owner(code) is None and code not in out:
            out.append(code)
    return tuple(out)
