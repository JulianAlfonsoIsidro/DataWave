"""Property-based tests for ``part2_network.features.ext_outflow_ratio``.

Covers Property 3 (external outflow ratio is a bounded fraction of total
outflow) of the part2-network spec.
"""

import math

from hypothesis import given, settings

from part2_network.features import (
    client_universe,
    ext_outflow_ratio,
    out_other_bank,
    split_by_direction,
    total_out,
)
from tests.strategies import transactions_frames

# Absolute tolerance for the float comparisons below. The ratio is computed as a
# single division of two float64 sums, so a small epsilon absorbs the rounding
# error without masking a real out-of-range or wrong-value result.
_TOL = 1e-9


# Feature: part2-network, Property 3: External outflow ratio is a bounded
# fraction of total outflow
@settings(max_examples=200)
@given(transactions_frames())
def test_ext_outflow_ratio_is_bounded_fraction(txns):
    """Ext_Outflow_Ratio is Out_Other_Bank / Total_Out, bounded to [0, 1], 0
    when Total_Out is 0, and indexed by the sorted client universe.

    Validates: Requirements 4.1, 4.2, 4.3
    """
    clients = client_universe(txns)
    outflows, _inflows, ext_outflows = split_by_direction(txns)

    total = total_out(outflows, clients)
    other = out_other_bank(ext_outflows, clients)
    ratio = ext_outflow_ratio(total, other)

    # Result is indexed by the sorted client universe (Requirements 8.2, 8.5).
    assert list(ratio.index) == clients

    for client in clients:
        total_value = float(total[client])
        other_value = float(other[client])
        ratio_value = float(ratio[client])

        # Every client's ratio is in the inclusive range [0, 1] (Req 4.3),
        # allowing a small float tolerance at the bounds.
        assert ratio_value >= -_TOL
        assert ratio_value <= 1.0 + _TOL

        if total_value == 0:
            # When Total_Out is 0, the ratio is exactly 0 (Req 4.2).
            assert ratio_value == 0
        else:
            # When Total_Out > 0, the ratio equals Out_Other_Bank / Total_Out
            # computed from the unrounded series (Req 4.1).
            expected = other_value / total_value
            assert math.isclose(ratio_value, expected, rel_tol=0, abs_tol=_TOL)
