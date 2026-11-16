"""Results, Personas and loading polish (Part 8): example tests.

Category pictures (one transparent image per value), the count-up markup,
the single tooltip, the loader status line and the generation-keyed reveal.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import theme  # noqa: E402
from webapp_core.group_picker_items import (  # noqa: E402
    VALUE_ART,
    YES_NO_ART,
    image_for,
    plan_picker,
)

IMG = ROOT / "app" / "static" / "group_picker" / "img"


# --- category pictures -------------------------------------------------------

def test_image_for_maps_values_and_yes_no_columns():
    assert image_for("segment", "Mass") == "segment-mass"
    assert image_for("age_band", "55+") == "age-55-plus"
    assert image_for("owns_Credit Card", "1", yes_no=True) == "yn-card-yes"
    assert image_for("owns_Credit Card", "0.0", yes_no=True) == "yn-card-no"
    assert image_for("segment", "Unknown value") == ""
    assert image_for("no_such_column", "1", yes_no=True) == ""


def test_every_mapped_value_has_one_transparent_picture():
    ids = [a for col in VALUE_ART.values() for a in col.values()]
    ids += [f"{a}-{v}" for a in YES_NO_ART.values() for v in ("yes", "no")]
    for art in ids:
        path = IMG / f"{art}.png"
        assert path.is_file(), art
        im = Image.open(path)
        assert im.mode == "RGBA", art
        alpha = np.asarray(im.getchannel("A"))
        # Transparent background (corners clear) with a drawn figure.
        assert alpha[0, 0] == 0 and alpha[-1, -1] == 0, art
        assert alpha.max() == 255, art


def test_plan_items_carry_their_picture():
    car = plan_picker(["segment"], ["Mass", "Mid-Market", "Affluent-Gold"], {})
    assert [i.image for i in car.items] == ["segment-mass", "segment-mid", "segment-gold"]
    tog = plan_picker(["digital_app_user"], ["0", "1"], {"0": 3, "1": 5})
    assert [i.image for i in tog.items] == ["yn-app-yes", "yn-app-no"]


# --- count-up ------------------------------------------------------------------

def test_count_up_rolls_digits_and_keeps_separators_fixed():
    html, n = theme.count_up_html("Expected Value: ₱12,345", el=0.25)
    assert n == 1
    assert '<span class="p8-sr">Expected Value: ₱12,345</span>' in html
    assert 'aria-hidden="true"' in html
    assert html.count('class="p8-cd"') == 5          # one column per digit
    assert '<span class="p8-cc">,</span>' in html     # comma does not roll
    assert "Expected Value: ₱" in html                # words and peso sign fixed
    # Ones place spins two extra cycles (20 + 5), tens one (10 + 4).
    assert "--d:25" in html and "--d:14" in html and "--d:3\"" in html
    assert "--p8-el:0.250s" in html


def test_count_up_staggers_numbers_and_skips_text_without_digits():
    html, n = theme.count_up_html("Likely Range: 10 To 20", el=0.0, start=2)
    assert n == 4 and "--n:2" in html and "--n:3" in html
    plain, m = theme.count_up_html("No numbers & here", el=0.0)
    assert m == 0 and plain == "No numbers &amp; here"


def test_counting_context_only_inside_the_window():
    assert theme.count_text_html("204") == "204"
    with theme.counting(None):
        assert theme.count_text_html("204") == "204"
    with theme.counting(0.1, "analysis-3-1"):
        out = theme.count_text_html("204")
        assert "p8-count" in out and "p8-g-analysis-3-1" in out
    assert theme.counting_el() is None


# --- tooltip and loader -------------------------------------------------------

def test_tooltip_has_no_native_title_and_stays_keyboard_accessible():
    out = theme.tooltip_html("About 76 Likely To Join", "Our best estimate.")
    assert "title=" not in out
    assert 'tabindex="0"' in out and "Our best estimate." in out


def test_loader_has_live_status_line_and_trace():
    out = theme.loader_html("analysis", "Scoring...", status="Running analysis for NEW-001...")
    assert re.search(r'class="pan-loading-status" role="status" aria-live="polite">'
                     r"Running analysis for NEW-001\.\.\.<", out)
    assert "pan-trace--running" in out
    fin = theme.finishing_overlay_html("personas", phase=0.25)
    assert "pan-trace--done" in fin and "--p8-phase:0.2500" in fin and "Personas Built" in fin
    assert "Promo Analyzed" in theme.finishing_overlay_html("analysis") and fin.count("pan-fin-spark") >= 14
