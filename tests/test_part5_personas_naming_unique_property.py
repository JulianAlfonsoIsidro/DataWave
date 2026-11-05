# Feature: persona-segmentation, Property 7: Persona names are unique within a set
"""Property-based test for persona name uniqueness within a Persona_Set.

Covers Property 7 of the persona-segmentation spec: for any Persona_Set, the
:class:`~part5_personas.naming.RuleBasedNamer` produces persona names that are all
distinct, so no two personas in the same set share a name (Requirement 4.9).

Requirement 4.9's uniqueness contract is a collaboration between the namer and its
caller: personas are named in ascending ``cluster_label`` order while a ``taken``
set of already-assigned names is threaded through, and each returned name is added
to ``taken`` before the next persona is named. ``RuleBasedNamer.name`` appends a
deterministic suffix whenever the derived base name is already in ``taken``, so the
final names are guaranteed distinct. This test drives exactly that protocol over a
generated set of :class:`~part5_personas.profile.PersonaProfile` values.

To exercise the disambiguation-suffix path (not just the trivial already-unique
case), the generator deliberately makes many profiles collide on their base name:
the base name is derived from a profile's ``distinguishing`` attributes, so sets
are built where numerous profiles share the same ``distinguishing`` list. If
uniqueness still holds across such colliding sets, the suffixing logic is doing its
job.

These are pure in-memory checks over ``RuleBasedNamer`` (no k-prototypes fit), so
they run fast. Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from part5_personas.naming import RuleBasedNamer
from part5_personas.profile import PersonaProfile

# A tiny pool of attribute names the generator draws ``distinguishing`` lists from.
# Keeping the pool small makes base-name collisions between personas common, which
# is what forces the disambiguation-suffix path to be exercised.
_ATTRS = [
    "owns_investment",
    "monthly_inflow",
    "total_spend",
    "outflow_other_banks",
    "best_channel",
    "digital_app_user",
]

# A small category vocabulary for the optional top_categories entries.
_CATEGORY_VALUES = ["0", "1", "In-app", "Email", "SMS", "X", "Y"]


@st.composite
def _persona_profile(draw, cluster_label: int) -> PersonaProfile:
    """Draw one :class:`PersonaProfile` for a given ``cluster_label``.

    The ``distinguishing`` list is drawn from the small shared ``_ATTRS`` pool so
    that different personas frequently share a base name, and the remaining fields
    (numeric means, top categories, percentage) are populated with plausible values
    the namer reads. The profile is constructed directly as the frozen dataclass.
    """
    distinguishing = draw(
        st.lists(st.sampled_from(_ATTRS), min_size=0, max_size=3, unique=True)
    )

    numeric_mean = {
        attr: draw(
            st.floats(
                min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
            )
        )
        for attr in distinguishing
    }
    numeric_median = dict(numeric_mean)

    # Optionally give some attributes a dominant top category so the namer's
    # categorical branches (channel selection, offer angle) get exercised too.
    top_categories: dict[str, list[tuple[str, int]]] = {}
    for attr in distinguishing:
        if draw(st.booleans()):
            category = draw(st.sampled_from(_CATEGORY_VALUES))
            count = draw(st.integers(min_value=1, max_value=100))
            top_categories[attr] = [(category, count)]

    pct = draw(
        st.floats(
            min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
        )
    )

    return PersonaProfile(
        cluster_label=cluster_label,
        size=draw(st.integers(min_value=1, max_value=1000)),
        pct_of_leads=round(pct, 1),
        numeric_mean=numeric_mean,
        numeric_median=numeric_median,
        top_categories=top_categories,
        distinguishing=distinguishing,
    )


@st.composite
def _persona_set(draw) -> list[PersonaProfile]:
    """Draw a list of :class:`PersonaProfile` representing one Persona_Set.

    Cluster labels are distinct and the returned list is ordered by ascending
    ``cluster_label`` (the order the caller must name in, per Requirement 4.9). The
    size is kept modest so each example stays fast while still producing many
    base-name collisions.
    """
    n = draw(st.integers(min_value=1, max_value=8))
    labels = draw(
        st.lists(
            st.integers(min_value=0, max_value=20),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )
    labels.sort()
    return [draw(_persona_profile(label)) for label in labels]


@settings(max_examples=200, deadline=1000)
@given(profiles=_persona_set())
def test_persona_names_are_unique_within_a_set(profiles):
    """Persona names are unique within a set.

    **Validates: Requirements 4.9**

    Naming every persona in ascending cluster-label order while threading the
    ``taken`` set — adding each returned name to ``taken`` before naming the next —
    yields names that are all distinct, even when many profiles collide on their
    base name. The deterministic disambiguation suffix guarantees no two personas in
    the set share a name.
    """
    namer = RuleBasedNamer()
    taken: set[str] = set()
    names: list[str] = []

    for profile in profiles:
        naming = namer.name(profile, taken)
        name = naming["name"]
        names.append(name)
        taken.add(name)

    # All names produced across the set are distinct (Requirement 4.9).
    assert len(set(names)) == len(names)
