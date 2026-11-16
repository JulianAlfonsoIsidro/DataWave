"""Cut the supplied category sheets into one transparent image per value.

Source: the user-supplied sheets in ``app/static/group_picker/*.png`` (black
figures on white, a male and a female figure per value, labels drawn in).
Output: ``app/static/group_picker/img/<art-id>.png``, one per value, holding
that value's figure pair side by side, label text removed, white keyed out
to transparency (black figure, alpha from darkness). Nothing is drawn or
generated: every output pixel comes from the source sheet.

Run from the repo root:  .venv/Scripts/python scripts/slice_category_sheets.py
The script stops with an error if a sheet is missing or the number of figures
found differs from the expected count, so a bad cut never ships silently.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
SHEETS = ROOT / "app" / "static" / "group_picker"
OUT = SHEETS / "img"
OUT_H = 360  # output height in px (shown at about 84-110 px, so 3x for HiDPI)

# sheet -> (pairing, art ids in value order)
#   "seq":  figures in reading order are (male, female) per value
#   "rows": row 1 holds every male figure, row 2 every female figure
#   "yn":   each row is one column: Yes-male, Yes-female, No-male, No-female
LAYOUT: dict[str, tuple[str, list[str]]] = {
    "segment.png": ("seq", ["segment-mass", "segment-mid", "segment-pref", "segment-gold"]),
    "age_band.png": ("seq", ["age-18-24", "age-25-34", "age-35-44", "age-45-54", "age-55-plus"]),
    "sec_class.png": ("seq", ["sec-a", "sec-b1", "sec-b2", "sec-c1", "sec-c2", "sec-d"]),
    "inflow_type.png": ("seq", ["inflow-salary", "inflow-business", "inflow-remittance", "inflow-mixed"]),
    "online_shopper.png": ("rows", ["shop-1", "shop-2", "shop-3", "shop-4", "shop-5"]),
    "digital_app_user_frugal_flag.png": ("yn", ["yn-app", "yn-frugal"]),
    "email_valid_mobile_valid.png": ("yn", ["yn-email", "yn-mobile"]),
    "owns_CreditCard_owns_Insurance.png": ("yn", ["yn-card", "yn-insurance"]),
    "owns_Investment_owns_Loan.png": ("yn", ["yn-investment", "yn-loan"]),
}


def _figures(gray: np.ndarray) -> tuple[list[tuple[int, int, int, int]], np.ndarray]:
    """Bounding boxes (y0, y1, x0, x1) of each figure, in reading order, plus
    a mask of the label-text pixels to drop."""
    h = gray.shape[0]
    dark = gray < 140
    lab, n = ndimage.label(dark, structure=np.ones((3, 3)))
    boxes = ndimage.find_objects(lab)
    min_h = h * 0.04  # letters are ~2-3% of the sheet height; heads ~5%
    keep, small_parts = [], []
    for i, sl in enumerate(boxes, start=1):
        bh = sl[0].stop - sl[0].start
        box = [sl[0].start, sl[0].stop, sl[1].start, sl[1].stop]
        (keep if bh >= min_h else small_parts).append((i, box))
    keep = [b for _, b in keep]
    # Merge parts of one figure (head + body + held object): horizontal
    # overlap and a small vertical gap.
    merged = True
    while merged:
        merged = False
        for a in range(len(keep)):
            for b in range(a + 1, len(keep)):
                A, B = keep[a], keep[b]
                ox = min(A[3], B[3]) - max(A[2], B[2])
                gap = max(A[0], B[0]) - min(A[1], B[1])
                # ...or a small held object just beside the hand (a phone that
                # does not touch the arm): vertical overlap, tiny side gap.
                oy = min(A[1], B[1]) - max(A[0], B[0])
                small = min((A[1] - A[0]) * (A[3] - A[2]), (B[1] - B[0]) * (B[3] - B[2]))
                big = max((A[1] - A[0]) * (A[3] - A[2]), (B[1] - B[0]) * (B[3] - B[2]))
                beside = (oy > 0.5 * min(A[1] - A[0], B[1] - B[0])
                          and -ox < gray.shape[1] * 0.015 and small < 0.25 * big)
                if beside or (ox > 0.3 * min(A[3] - A[2], B[3] - B[2]) and gap < h * 0.05):
                    keep[a] = [min(A[0], B[0]), max(A[1], B[1]), min(A[2], B[2]), max(A[3], B[3])]
                    del keep[b]
                    merged = True
                    break
            if merged:
                break
    # A small part inside a big part's vertical span, close beside it, is a
    # held object (key fob, card, purse); labels sit above heads or below
    # feet, outside every span, and are dropped.
    text = np.zeros_like(dark)
    reach = gray.shape[1] * 0.06
    for i, (y0, y1, x0, x1) in small_parts:
        cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
        host, best = None, None
        for k, (Y0, Y1, X0, X1) in enumerate(keep):
            if not (Y0 <= cy <= Y1 and (Y1 - Y0) > h * 0.15):
                continue
            dist = max(X0 - cx, cx - X1, 0.0)
            if dist <= reach and (best is None or dist < best):
                host, best = k, dist
        if host is None:
            sl = boxes[i - 1]
            text[sl][lab[sl] == i] = True
        else:
            Y0, Y1, X0, X1 = keep[host]
            keep[host] = [min(Y0, y0), max(Y1, y1), min(X0, x0), max(X1, x1)]
    # Reading order: group into rows by vertical centre, then left to right.
    keep.sort(key=lambda r: (r[0] + r[1]) / 2)
    rows: list[list[list[int]]] = []
    for r in keep:
        cy = (r[0] + r[1]) / 2
        if rows and abs(cy - np.mean([(q[0] + q[1]) / 2 for q in rows[-1]])) < h * 0.12:
            rows[-1].append(r)
        else:
            rows.append([r])
    ordered = [tuple(r) for row in rows for r in sorted(row, key=lambda q: q[2])]
    text = ndimage.binary_dilation(text, iterations=3)
    return ordered, text, [len(r) for r in rows]


def _cut(alpha: np.ndarray, box) -> np.ndarray:
    y0, y1, x0, x1 = box
    pad = 4
    return alpha[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]


def _pair(left: np.ndarray, right: np.ndarray) -> Image.Image:
    """Male left, female right, bottom-aligned, on a transparent canvas."""
    hh = max(left.shape[0], right.shape[0])
    gap = int(hh * 0.06)
    w = left.shape[1] + gap + right.shape[1]
    canvas = np.zeros((hh, w), dtype=np.uint8)
    canvas[hh - left.shape[0]:, :left.shape[1]] = left
    canvas[hh - right.shape[0]:, left.shape[1] + gap:] = right
    a = Image.fromarray(canvas, "L")
    scale = OUT_H / hh
    a = a.resize((max(1, round(w * scale)), OUT_H), Image.LANCZOS)
    rgba = Image.new("RGBA", a.size, (0, 0, 0, 0))
    rgba.putalpha(a)
    return rgba


def main() -> int:
    OUT.mkdir(exist_ok=True)
    report = []
    for name, (mode, arts) in LAYOUT.items():
        path = SHEETS / name
        if not path.is_file():
            print(f"MISSING sheet: {path}", file=sys.stderr)
            return 1
        gray = np.asarray(Image.open(path).convert("L"), dtype=np.int32)
        figs, text, per_row = _figures(gray)
        expected = 2 * len(arts) * (2 if mode == "yn" else 1)
        if len(figs) != expected:
            print(f"{name}: found {len(figs)} figures {per_row}, expected {expected}", file=sys.stderr)
            return 1
        # Alpha from darkness; anti-aliased edges kept, paper noise dropped.
        alpha = np.clip((235 - gray) * 255 // 175, 0, 255).astype(np.uint8)
        alpha[text] = 0
        cuts = [_cut(alpha, b) for b in figs]
        if mode == "seq":
            pairs = {art: (cuts[2 * i], cuts[2 * i + 1]) for i, art in enumerate(arts)}
        elif mode == "rows":
            n = len(arts)
            pairs = {art: (cuts[i], cuts[n + i]) for i, art in enumerate(arts)}
        else:  # yn: row r = column r; Yes pair then No pair
            pairs = {}
            for r, art in enumerate(arts):
                row = cuts[4 * r:4 * r + 4]
                pairs[f"{art}-yes"] = (row[0], row[1])
                pairs[f"{art}-no"] = (row[2], row[3])
        for art, (m, f) in pairs.items():
            img = _pair(m, f)
            img.save(OUT / f"{art}.png", optimize=True)
            report.append(f"{art}.png {img.size[0]}x{img.size[1]} <- {name}")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
