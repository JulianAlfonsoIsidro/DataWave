"""Example/edge-case unit tests for the Validation_Reporter.

These are concrete-example tests (not Hypothesis) for the quartile / join-rate
reporting in ``part2_network.validation`` against Requirement 9 -- in
particular the structured report (9.6, 9.8), the printed report ordering
(9.7), the zero-treated-leads path (9.9), and the client_id tie-break (9.5).

Every frame is hand-built with values whose quartile assignment and Join_Rate
are worked out by hand in the test, so the asserted numbers are independent of
the implementation.
"""

import pandas as pd

from part2_network.validation import (
    assign_quartiles,
    compute_report,
    print_report,
)


def _treated_leads(client_ids: list[str], joined_flags: list[int]) -> pd.DataFrame:
    """Build a P001 treated-leads frame carrying ``client_id`` and ``joined``.

    Mirrors the columns ``select_treated_leads`` would have produced for P001
    control-group-0 rows -- only the columns the reporter consumes downstream
    (``client_id`` for the join and ``joined`` for the Join_Rate) matter here.
    """
    return pd.DataFrame(
        {
            "promo_id": ["P001"] * len(client_ids),
            "client_id": client_ids,
            "control_group": [0] * len(client_ids),
            "joined": joined_flags,
        }
    )


def _features(client_ids: list[str], ratios: list[float]) -> pd.DataFrame:
    """Build a features frame with ``client_id`` and ``ext_outflow_ratio``."""
    return pd.DataFrame(
        {
            "client_id": client_ids,
            "ext_outflow_ratio": ratios,
        }
    )


def test_worked_example_eight_leads_four_quartiles() -> None:
    """Eight fully matched leads bin into four pairs with hand-computed rates.

    Eight treated P001 leads sorted by ascending ``ext_outflow_ratio`` split
    into four equal-count bins of two (``array_split`` over 8 positions). With
    distinct ratios 0.10..0.80 the sorted order is exactly client_id order, so
    the pairs are:

      - Q1: C001 (0.10), C002 (0.20)
      - Q2: C003 (0.30), C004 (0.40)
      - Q3: C005 (0.50), C006 (0.60)
      - Q4: C007 (0.70), C008 (0.80)

    The ``joined`` flags are chosen so each quartile's Join_Rate is obvious by
    hand: Q1 both joined (1.0), Q2 one joined (0.5), Q3 both joined (1.0), Q4
    none joined (0.0). All eight match the features frame, so matched == 8 and
    the overall inner-join rate is 1.0. (Req 9.4, 9.6, 9.7, 9.8)
    """
    client_ids = [f"C00{i}" for i in range(1, 9)]
    ratios = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    #          Q1    Q1    Q2    Q2    Q3    Q3    Q4    Q4
    joined = [1, 1, 1, 0, 1, 1, 0, 0]

    treated = _treated_leads(client_ids, joined)
    features = _features(client_ids, ratios)

    report = compute_report(treated, features)

    assert report["total_treated"] == 8
    assert report["matched"] == 8
    assert report["overall_join_rate"] == 1.0

    # All four quartiles are non-empty and appear in Q1..Q4 order.
    labels = [q["label"] for q in report["quartiles"]]
    assert labels == ["Q1", "Q2", "Q3", "Q4"]

    # Each quartile holds exactly two leads.
    assert [q["count"] for q in report["quartiles"]] == [2, 2, 2, 2]

    # Hand-computed per-quartile Join_Rates.
    rates = {q["label"]: q["join_rate"] for q in report["quartiles"]}
    assert rates["Q1"] == 1.0  # C001, C002 both joined
    assert rates["Q2"] == 0.5  # C003 joined, C004 not
    assert rates["Q3"] == 1.0  # C005, C006 both joined
    assert rates["Q4"] == 0.0  # C007, C008 neither joined


def test_partial_match_overall_rate_is_matched_over_total() -> None:
    """When some leads miss the features frame, overall rate == matched/total.

    Five treated leads are selected but only three of their client_ids appear
    in the features frame (C001, C002, C003 present; C004, C005 absent). The
    inner join keeps three, so matched == 3 against total_treated == 5 and the
    overall inner-join rate is 3/5 == 0.6, independent of the ``joined`` flags.
    (Req 9.3, 9.8)
    """
    treated = _treated_leads(
        ["C001", "C002", "C003", "C004", "C005"],
        [1, 0, 1, 1, 0],
    )
    # C004 and C005 are deliberately absent from the features frame.
    features = _features(["C001", "C002", "C003"], [0.2, 0.4, 0.6])

    report = compute_report(treated, features)

    assert report["total_treated"] == 5
    assert report["matched"] == 3
    assert report["overall_join_rate"] == 3 / 5
    assert report["overall_join_rate"] == report["matched"] / report["total_treated"]


def test_zero_treated_leads_returns_empty_report() -> None:
    """An empty treated-leads frame yields a zeroed, quartile-free report (9.9).

    No treated leads means nothing to join: total_treated and matched are 0,
    the overall inner-join rate is 0.0 (not a division by zero), and the
    quartile list is empty because quartile computation is skipped.
    """
    treated = _treated_leads([], [])
    features = _features(["C001", "C002"], [0.3, 0.7])

    report = compute_report(treated, features)

    assert report["total_treated"] == 0
    assert report["matched"] == 0
    assert report["overall_join_rate"] == 0.0
    assert report["quartiles"] == []


def test_print_report_zero_leads_prints_no_match_message(capsys) -> None:
    """print_report with no treated leads prints the no-match message only (9.9).

    The no-matching-leads message is printed and no quartile line (anything
    starting with "Q" and a digit) nor an overall-rate line appears, confirming
    the quartile computation was skipped entirely.
    """
    treated = _treated_leads([], [])
    features = _features(["C001", "C002"], [0.3, 0.7])

    report = print_report(treated, features)

    captured = capsys.readouterr().out
    lowered = captured.lower()
    # A message indicating no matching leads were found.
    assert "no matching" in lowered
    # No quartile lines were printed.
    for label in ("Q1", "Q2", "Q3", "Q4"):
        assert label not in captured
    # No overall-rate line was printed.
    assert "overall" not in lowered
    # The returned report mirrors the zero-treated-leads structure.
    assert report["total_treated"] == 0
    assert report["quartiles"] == []


def test_print_report_prints_quartiles_in_order_and_overall(capsys) -> None:
    """print_report prints Q1..Q4 lines in order plus an overall-rate line (9.7).

    Uses the eight-lead worked example. The four quartile lines must appear in
    the order Q1, Q2, Q3, Q4 (each with its label, count, and rate), followed
    by a final overall inner-join rate line. We assert both the presence of
    each piece and the relative ordering of the Q* lines.
    """
    client_ids = [f"C00{i}" for i in range(1, 9)]
    ratios = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    joined = [1, 1, 1, 0, 1, 1, 0, 0]

    treated = _treated_leads(client_ids, joined)
    features = _features(client_ids, ratios)

    print_report(treated, features)

    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]

    # Find the printed position of each quartile label.
    positions = {}
    for label in ("Q1", "Q2", "Q3", "Q4"):
        matching = [i for i, line in enumerate(lines) if line.startswith(label)]
        assert matching, f"expected a line starting with {label}"
        positions[label] = matching[0]

    # Quartile lines appear in strict Q1 < Q2 < Q3 < Q4 order.
    assert (
        positions["Q1"]
        < positions["Q2"]
        < positions["Q3"]
        < positions["Q4"]
    )

    # Each quartile line carries its count (2) and its hand-computed rate.
    q_lines = {label: lines[positions[label]] for label in positions}
    assert "2" in q_lines["Q1"]
    assert "1.0000" in q_lines["Q1"]
    assert "0.5000" in q_lines["Q2"]
    assert "1.0000" in q_lines["Q3"]
    assert "0.0000" in q_lines["Q4"]

    # An overall inner-join rate line follows the quartile lines.
    overall_lines = [i for i, line in enumerate(lines) if "overall" in line.lower()]
    assert overall_lines, "expected an overall inner-join rate line"
    assert overall_lines[0] > positions["Q4"]
    assert "1.0000" in lines[overall_lines[0]]


def test_boundary_tie_break_lower_client_id_in_earlier_quartile() -> None:
    """At a bin boundary, the lower client_id lands in the earlier quartile (9.5).

    Four joined leads split into four singleton bins (``array_split`` over 4
    positions gives one lead per bin). Two leads share the same boundary ratio
    0.50; the tie must be broken by ascending ``client_id``, so C002 (lower)
    sorts before C009 (higher). Full sorted order by (ratio, client_id):

      - 0.10 -> C001  -> Q1
      - 0.50 -> C002  -> Q2  (lower client_id of the tie, earlier bin)
      - 0.50 -> C009  -> Q3  (higher client_id of the tie, later bin)
      - 0.90 -> C003  -> Q4

    So the lower-id tied lead C002 must carry an earlier quartile label than
    the higher-id tied lead C009.
    """
    client_ids = ["C001", "C002", "C009", "C003"]
    ratios = [0.10, 0.50, 0.50, 0.90]
    joined = [1, 1, 1, 1]

    treated = _treated_leads(client_ids, joined)
    features = _features(client_ids, ratios)

    # Reproduce the reporter's own inner join so the index/order matches what
    # assign_quartiles operates on.
    joined_leads = treated.merge(features, on="client_id", how="inner")
    labels = assign_quartiles(joined_leads)
    label_by_client = dict(zip(joined_leads["client_id"], labels))

    order = ["Q1", "Q2", "Q3", "Q4"]
    # The lower client_id of the tie sits in a strictly earlier quartile.
    assert order.index(label_by_client["C002"]) < order.index(
        label_by_client["C009"]
    )
    # And the exact assignment the hand-worked sort produces.
    assert label_by_client["C001"] == "Q1"
    assert label_by_client["C002"] == "Q2"
    assert label_by_client["C009"] == "Q3"
    assert label_by_client["C003"] == "Q4"
