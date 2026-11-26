"""Property test for the decision-card view (Part 7, Property 3).

Feature: part7-AI-and-finishing, Property 3: No raw codes reach decision-card text
"""
from __future__ import annotations

import copy
import re

from hypothesis import given, settings

from labels import HIDDEN_DRIVER_CODES
from tests.strategies_part7 import card_dicts
from webapp_core.card_view import build_card_view


@settings(max_examples=100, deadline=None)
@given(card=card_dicts())
def test_card_view_has_no_raw_codes(card):
    """**Validates: Requirements 4.3, 4.4, 4.5, 4.6, 4.8, 4.11, 4.12**"""
    before = copy.deepcopy(card)
    view = build_card_view(card)

    # 4.11: the input card dict is not mutated.
    assert card == before

    # 4.4 / 4.5: hidden drivers dropped, at most 3 drivers, each <= 60 chars.
    visible = [c for c in card["top_drivers"] if c not in HIDDEN_DRIVER_CODES]
    assert len(view.drivers) == min(3, len(visible))
    for phrase in view.drivers:
        assert len(phrase) <= 60

    # 4.6: "<Plain Reason>: N", N >= 1, count desc then reason alphabetical.
    assert len(view.exclusions) == sum(1 for n in card["excluded_by_reason"].values() if n >= 1)
    parsed = []
    for line in view.exclusions:
        reason, _, count = line.rpartition(": ")
        assert reason and count.isdigit() and int(count) >= 1
        parsed.append((reason, int(count)))
    assert parsed == sorted(parsed, key=lambda p: (-p[1], p[0]))

    # 4.8: whole-number stats with L <= N <= H.
    likely = int(re.search(r"About ([\d,]+) Expected Joiners", view.stats[0].label).group(1).replace(",", ""))
    low, high = (
        int(x.replace(",", ""))
        for x in re.search(r"Range: ([\d,]+) To ([\d,]+)", view.stats[1].label).groups()
    )
    assert low <= likely <= high

    # 4.3 / 4.12: no underscore anywhere in the card text.
    texts = [
        view.title, view.action, view.channel, view.angle,
        view.why_heading, view.not_contacted_heading,
        *view.drivers, *view.exclusions,
        *(s.label for s in view.stats), *(s.tooltip for s in view.stats),
    ]
    for text in texts:
        assert "_" not in text
