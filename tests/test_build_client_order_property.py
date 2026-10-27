# Feature: part2-network, Property: ascending client_id ordering
"""Property-based test for ascending client_id ordering (Property 12).

Covers the row-ordering guarantee of ``part2_network.features.build``
(Requirement 8.5): the Features_File rows are ordered by ascending
``client_id``.

For any valid transactions frame the assembled output must satisfy:

- the ``client_id`` column is already in ascending order --
  ``list(output.client_id) == sorted(output.client_id)``; and
- that ordered sequence is exactly the sorted distinct client universe --
  ``list(output.client_id) == sorted(set(txns.client_id))``.

As a light cross-check on the one-row-per-client guarantee (Requirement 8.2,
whose dedicated property test is Property 11), the ``client_id`` values are
also asserted unique and equal as a set to the distinct clients seen in the
input. The focus here remains ordering.

**Validates: Requirements 8.5**
"""

from hypothesis import given, settings

from part2_network.features import build
from tests.strategies import transactions_frames


@settings(max_examples=200)
@given(transactions_frames())
def test_build_rows_ordered_by_ascending_client_id(txns):
    output = build(txns)

    emitted = list(output.client_id)
    expected = sorted(set(txns.client_id))

    # Rows are ordered by ascending client_id (Requirement 8.5): the emitted
    # sequence equals its own sort and equals the sorted distinct universe.
    assert emitted == sorted(emitted)
    assert emitted == expected

    # Light cross-check on Requirement 8.2: client_id values are unique and
    # match the distinct clients present in the input.
    assert len(emitted) == len(set(emitted))
    assert set(emitted) == set(txns.client_id)
