"""Property-based tests for category-name normalization.

Covers Property 10 (category-name normalization is well-formed and
deterministic) of the part2-network spec, exercising
``part2_network.features.spend_share_column`` against Requirement 7.3.
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from part2_network.config import SPEND_SHARE_PREFIX
from part2_network.features import spend_share_column


# Feature: part2-network, Property: normalization well-formedness

# A well-formed suffix is either empty (all-non-alphanumeric category) or a
# run-separated sequence of lowercase-ascii-alphanumeric tokens joined by single
# underscores: no uppercase, no other characters, and no leading, trailing, or
# doubled underscores.
_WELL_FORMED_SUFFIX = re.compile(r"^(?:[0-9a-z]+(?:_[0-9a-z]+)*)?$")

# Categories drawn from the full text space: letters, digits, spaces,
# punctuation, mixed case, and unicode all appear. The mixed_case/punctuation
# alphabets bias generation toward the interesting normalization paths while
# the bare st.text() keeps the full unicode space in play.
_CATEGORY = st.one_of(
    st.text(),
    st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd", "Zs", "Po", "Ps", "Pe", "Pd"),
        ),
    ),
    st.text(
        alphabet="AaBbZz09 -&!/.,_()" + "\t\n",
    ),
)


@settings(max_examples=400)
@given(category=_CATEGORY)
def test_spend_share_column_is_well_formed(category: str) -> None:
    name = spend_share_column(category)

    # Always starts with the configured prefix.
    assert SPEND_SHARE_PREFIX == "spend_share_"
    assert name.startswith(SPEND_SHARE_PREFIX)

    suffix = name[len(SPEND_SHARE_PREFIX):]

    # The suffix contains only lowercase ascii letters, digits, and underscores
    # -- no uppercase, no whitespace, no punctuation, no unicode.
    assert re.match(r"^[0-9a-z_]*$", suffix), suffix

    # No run of two or more consecutive underscores: every non-alnum run
    # collapses to exactly one underscore.
    assert "__" not in suffix, suffix

    # No leading or trailing underscore (vacuously true for the empty suffix).
    assert not suffix.startswith("_"), suffix
    assert not suffix.endswith("_"), suffix

    # The full well-formedness invariant, empty suffix allowed.
    assert _WELL_FORMED_SUFFIX.match(suffix), suffix


@settings(max_examples=400)
@given(category=_CATEGORY)
def test_spend_share_column_is_idempotent(category: str) -> None:
    # Normalizing an already-normalized suffix yields the same suffix: feeding
    # the suffix back through the column builder reproduces the same name.
    name = spend_share_column(category)
    suffix = name[len(SPEND_SHARE_PREFIX):]

    renormalized = spend_share_column(suffix)
    assert renormalized == name


@settings(max_examples=400)
@given(category=_CATEGORY)
def test_spend_share_column_is_deterministic(category: str) -> None:
    # Same input always produces the same output.
    assert spend_share_column(category) == spend_share_column(category)
