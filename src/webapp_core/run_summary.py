"""The current run as an aggregate summary for the assistant (Part 9 round 3).

Pure, no Streamlit (spec part9-layout-fixes, Requirement 30). The owner found
that the assistant could not see the run: its payload held the form and the
document only. This builds the Run_Summary that now goes with every question:
per segment the clients, not contacted, control group, sendable, expected
joiners, action and main channel; the threshold; the Impact Summary; and the
personas' names and sizes. It holds no client id and no per-client row, so
``ai.bedrock.assert_private`` accepts it (the key ``control`` is avoided on
purpose: the guard treats it as a per-client column).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from webapp_core.number_format import share_pct, shown_joiners
from webapp_core.segment_flow import flow_rows, flow_total


def run_summary(
    result: Any,
    *,
    threshold_label: str | None = None,
    impact: Mapping[str, Any] | None = None,
    persona_sets: Sequence[Any] | None = None,
) -> dict[str, Any] | None:
    """The Run_Summary, or None when there is no run with cards."""
    cards = getattr(result, "cards", None)
    if not cards:
        return None
    actions = {str(c.get("segment")): c for c in cards}
    rows = flow_rows(cards)
    total = flow_total(rows)
    segments = []
    for r in rows:
        card = actions.get(r.segment, {})
        segments.append({
            "segment": r.segment,
            "clients": r.clients,
            "not_contacted": r.not_contacted,
            "control_group": r.control,
            "sendable": r.sendable,
            "expected_joiners": round(r.forecast, 1),
            "expected_joiners_rounded": shown_joiners(r.forecast),
            "expected_join_rate": share_pct(r.forecast, r.sendable),
            "action": str(card.get("action", "")),
            "main_channel": str(card.get("dominant_channel", "")),
            "message_angle": str(card.get("message_angle", "")),
        })
    act_first = [s["segment"] for s in segments if s["action"] == "Prioritize"]
    summary: dict[str, Any] = {
        "threshold": threshold_label or "",
        "act_first_segments": act_first,
        "segments": segments,
        "totals": {
            "clients": total.clients,
            "not_contacted": total.not_contacted,
            "control_group": total.control,
            "sendable": total.sendable,
            "expected_joiners": round(total.forecast, 1),
            "expected_joiners_rounded": shown_joiners(total.forecast),
            "expected_join_rate": share_pct(total.forecast, total.sendable),
        },
    }
    if impact:
        summary["impact"] = {str(k): v for k, v in impact.items()}
    if persona_sets:
        personas = []
        for ps in persona_sets:
            for p in getattr(ps, "personas", []) or []:
                personas.append({
                    "group": str(getattr(ps, "group_key", "") or "All leads"),
                    "name": str(p.name),
                    "size": int(p.profile.size),
                    "share_pct": round(float(p.profile.pct_of_leads), 1),
                })
        if personas:
            summary["personas"] = personas
    return summary
