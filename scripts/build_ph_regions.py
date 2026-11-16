"""One-off: build app/static/group_picker/ph_regions.svg (Part 8, F6).

Input: the approved faeldon/philippines-json-maps v1.1.1 country-level GeoJSON
(``latest/geojson/country/lowres/country.0.001.json``, 18 region features),
downloaded once to a working folder outside ``data/``.

Output: one SVG with exactly four Map_Areas (NCR, Luzon, Visayas, Mindanao),
each one dissolved outline with no internal region border, plus the NCR
callout bubble (enlarged NCR copy + leader line). Standard library only.

Method (design F6, option B with A as fallback):
  1. assign each region to a Map_Area with ``webapp_core.region_map.AREA_SHAPES``;
  2. equirectangular projection centred near 12.5 N, snapped to a 0.05 grid;
  3. per area, cancel every edge that occurs twice (shared internal borders)
     and chain the remaining edges into outer rings (a true union);
  4. Douglas-Peucker simplify the outer rings, drop tiny islets;
  5. if an area leaves unmatched edges, fall back to emitting its member
     rings in one path (the picker then hides seams with a same-fill stroke).

Usage (from the repo root):
    python -I scripts/build_ph_regions.py <country.0.001.json> app/static/group_picker/ph_regions.svg
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# The mapping has one home: webapp_core.region_map (src/ layout).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from webapp_core.region_map import AREA_SHAPES, MAP_AREAS, shape_owner  # noqa: E402

LAT0 = 12.5
WIDTH_UNITS = 300.0      # map width in SVG units (before the bubble margin)
GRID = 20                # snap grid: 1 / 20 = 0.05 units
SIMPLIFY = 0.45          # Douglas-Peucker tolerance in units
MIN_RING_AREA = 2.0      # drop islets smaller than this (square units)
MAX_RINGS_FLAG = 80      # report areas with more outer rings than this
BUBBLE_R = 46.0          # NCR callout radius in units
PAD = 8.0


def load(path: str) -> list[tuple[int, list[list[list[tuple[float, float]]]]]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for feat in data["features"]:
        code = int(feat["properties"]["adm1_psgc"])
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        out.append((code, [[[(float(x), float(y)) for x, y in ring] for ring in poly] for poly in polys]))
    return out


def ring_area(ring: list[tuple[float, float]]) -> float:
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += x1 * y2 - x2 * y1
    return s / 2.0


def dp(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas-Peucker on an open polyline (iterative)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = points[a], points[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-12
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            x0, y0 = points[i]
            d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / norm
            if d > best:
                best, idx = d, i
        if best > tol and idx > 0:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(ring) < 8:
        return ring
    # split at the farthest point from the first so the closed ring keeps shape
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - ring[0][0]) ** 2 + (ring[i][1] - ring[0][1]) ** 2)
    a = dp(ring[: far + 1], SIMPLIFY)
    b = dp(ring[far:] + [ring[0]], SIMPLIFY)
    return a[:-1] + b[:-1]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    regions = load(argv[1])
    codes = [c for c, _ in regions]

    # --- projection bounds ---
    lons = [x for _, polys in regions for poly in polys for ring in poly for x, _ in ring]
    lats = [y for _, polys in regions for poly in polys for ring in poly for _, y in ring]
    kx = math.cos(math.radians(LAT0))
    scale = WIDTH_UNITS / ((max(lons) - min(lons)) * kx)
    left = BUBBLE_R * 2 + PAD * 3  # room for the NCR bubble west of Luzon
    lon0, lat_top = min(lons), max(lats)

    def proj(lon: float, lat: float) -> tuple[int, int]:
        x = left + (lon - lon0) * kx * scale
        y = PAD + (lat_top - lat) * scale
        return round(x * GRID), round(y * GRID)

    report: list[str] = []
    paths: dict[str, list[list[tuple[float, float]]]] = {}
    fallback: list[str] = []
    for area in MAP_AREAS:
        members = [polys for c, polys in regions if c in AREA_SHAPES[area]]
        edges: dict[tuple, int] = {}
        directed: list[tuple] = []
        member_rings: list[list[tuple[int, int]]] = []
        for polys in members:
            for poly in polys:
                for ring in poly:
                    pts = [proj(x, y) for x, y in ring]
                    dedup = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
                    if dedup and dedup[0] == dedup[-1]:
                        dedup = dedup[:-1]
                    if len(dedup) < 3:
                        continue
                    member_rings.append(dedup)
                    for a, b in zip(dedup, dedup[1:] + dedup[:1]):
                        key = (a, b) if a < b else (b, a)
                        edges[key] = edges.get(key, 0) + 1
                        directed.append((a, b))
        boundary = [(a, b) for a, b in directed if edges[(a, b) if a < b else (b, a)] == 1]
        nxt: dict[tuple, list[tuple]] = {}
        for a, b in boundary:
            nxt.setdefault(a, []).append(b)
        rings: list[list[tuple[int, int]]] = []
        unmatched = 0
        while nxt:
            start = next(iter(nxt))
            ring = [start]
            cur = start
            while True:
                outs = nxt.get(cur)
                if not outs:
                    unmatched += 1
                    break
                nb = outs.pop()
                if not outs:
                    del nxt[cur]
                if nb == start:
                    break
                ring.append(nb)
                cur = nb
            if len(ring) >= 3:
                rings.append(ring)
        use_rings = rings
        if unmatched > 3:
            fallback.append(area)
            use_rings = member_rings
        out_rings = []
        for ring in use_rings:
            fr = [(x / GRID, y / GRID) for x, y in ring]
            fr = simplify_ring(fr)
            if len(fr) >= 3 and abs(ring_area(fr)) >= MIN_RING_AREA:
                out_rings.append(fr)
        paths[area] = out_rings
        flag = "  <-- many rings, edges may not match" if len(out_rings) > MAX_RINGS_FLAG else ""
        report.append(f"{area:9s} outer rings kept: {len(out_rings):3d} (chained {len(rings)}), unmatched chains: {unmatched}{flag}")

    # --- NCR callout ---
    ncr = paths["NCR"]
    allpts = [p for r in ncr for p in r]
    cx = sum(x for x, _ in allpts) / len(allpts)
    cy = sum(y for _, y in allpts) / len(allpts)
    span = max(max(x for x, _ in allpts) - min(x for x, _ in allpts), max(y for _, y in allpts) - min(y for _, y in allpts))
    zoom = (BUBBLE_R * 1.3) / span
    bx, by = PAD + BUBBLE_R, cy - BUBBLE_R * 0.6
    width = max(x for r in paths.values() for ring in r for x, _ in ring) + PAD
    height = max(y for r in paths.values() for ring in r for _, y in ring) + PAD

    def d_of(rings: list[list[tuple[float, float]]]) -> str:
        return "".join("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in ring) + "Z" for ring in rings)

    # leader line from the bubble edge towards NCR's true centroid
    ang = math.atan2(cy - by, cx - bx)
    lx, ly = bx + BUBBLE_R * math.cos(ang), by + BUBBLE_R * math.sin(ang)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        'data-source="faeldon/philippines-json-maps v1.1.1 (MIT); boundaries CC BY-IGO, NAMRIA, PSA via OCHA">'
    ]
    for area in MAP_AREAS:
        extra = ""
        if area == "NCR":
            extra = (
                f'<line class="leader" x1="{lx:.1f}" y1="{ly:.1f}" x2="{cx:.1f}" y2="{cy:.1f}"/>'
                f'<circle class="bubble" cx="{bx:.1f}" cy="{by:.1f}" r="{BUBBLE_R:.0f}"/>'
                f'<path class="area-shape ncr-zoom" transform="translate({bx:.1f} {by:.1f}) scale({zoom:.3f}) '
                f'translate({-cx:.1f} {-cy:.1f})" d="{d_of(ncr)}"/>'
            )
        parts.append(
            f'<g data-area="{area}"><path class="area-shape" fill-rule="evenodd" d="{d_of(paths[area])}"/>{extra}</g>'
        )
    parts.append("</svg>")
    out = Path(argv[2])
    out.write_text("".join(parts), encoding="utf-8")

    print("ph_regions build report")
    print("\n".join(report))
    print(f"fallback areas: {fallback or 'none'}")
    print(f"source codes not in AREA_SHAPES: {[c for c in codes if shape_owner(c) is None] or 'none'}")
    mapped = [c for cs in AREA_SHAPES.values() for c in cs]
    print(f"mapped codes missing from source: {[c for c in mapped if c not in codes] or 'none'}")
    print(f"wrote {out} ({out.stat().st_size / 1024:.1f} KB), viewBox {width:.0f} x {height:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
