"""Persona naming for the Persona_Pipeline (design D5).

Turns a :class:`~part5_personas.profile.PersonaProfile` into a human-facing
``name``, a one-line ``description``, and 2-3 recommended campaign ``actions``.
Each action reads as campaign guidance a planner can act on and, where the
profile supports it, names a suggested channel (one of "In-app", "Email", "SMS")
together with an offer angle — for example "Best reached by SMS with a
savings-bundle offer" (Requirement 4.5). All derivation is a pure, deterministic
function of the profile's fields so an identical profile always yields identical
output (Requirement 4.6); the module holds no Streamlit imports and no
modelling.

Design D5 — the pipeline depends only on the narrow :class:`PersonaNamer`
Protocol, never on a concrete namer type, so a future ``BedrockNamer`` living in
its own module can implement the same ``name(profile, taken) -> PersonaNaming``
signature and be swapped in at the call site with no pipeline or page changes
(Requirement 4.8). :class:`RuleBasedNamer` is the default implementation.

Uniqueness contract (Requirement 4.9): :meth:`RuleBasedNamer.name` takes a
``taken`` set of names already assigned within the current Persona_Set. If the
derived base name is already in ``taken``, a deterministic suffix is appended
until the name is unique. The *caller* is responsible for adding each returned
name to ``taken`` before naming the next persona, and personas must be named in
ascending cluster-label order, so disambiguation is fully deterministic.
"""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable

from part5_personas.profile import PersonaProfile


class PersonaNaming(TypedDict):
    """The naming output for one persona (design D5).

    Attributes:
        name: A unique, human-facing persona name within its Persona_Set.
        description: A single-line description derived from the profile.
        actions: Between 2 and 3 recommended campaign actions (never fewer than
            2, never more than 3) derived from the profile (Requirement 4.5).
    """

    name: str
    description: str
    actions: list[str]


@runtime_checkable
class PersonaNamer(Protocol):
    """The naming interface the Persona_Pipeline depends on (Requirement 4.8).

    A concrete namer maps a :class:`PersonaProfile` (plus the set of names
    already taken in the current Persona_Set) to a :class:`PersonaNaming`. The
    pipeline references only this Protocol, so an alternative implementation
    (for example a future Bedrock-backed namer) that honours the same signature
    substitutes without any caller change (design D5).
    """

    def name(self, profile: PersonaProfile, taken: set[str]) -> PersonaNaming:
        """Return the naming for ``profile``, unique against ``taken``."""
        ...


# Human-readable fallbacks for the raw ownership flag columns the join stage
# produces (``owns_<product_type>``). Kept tiny and data-independent so the
# namer stays a pure function of the profile.
def _prettify_attribute(attr: str) -> str:
    """Turn a raw attribute column name into a short human-readable phrase.

    Pure string formatting (Requirement 4.6): ``owns_investment`` becomes
    ``investment ownership`` and a snake/space name like ``monthly_income``
    becomes ``monthly income``. No external state is consulted.
    """
    if attr.startswith("owns_"):
        product = attr[len("owns_") :].replace("_", " ").strip()
        return f"{product} ownership" if product else "product ownership"
    return attr.replace("_", " ").strip().lower()


def _title_phrase(attr: str) -> str:
    """Title-case a prettified attribute for use inside a persona name."""
    return _prettify_attribute(attr).title()


# The domain's only valid channel labels (must match these spellings exactly, or
# leads become unreachable downstream). The namer never emits anything outside
# this set (Requirement 4.5).
_VALID_CHANNELS = ("In-app", "Email", "SMS")

# Deterministic default channel used when the profile carries no channel signal
# at all. Email is the cheapest, most broadly reachable domain channel, so it is
# the safe default (Requirement 4.5 "WHERE the Persona_Profile supports it").
_DEFAULT_CHANNEL = "Email"

# Fixed precedence for mapping an ownership/validity flag attribute to a channel
# when that flag's dominant category is the "on" value ("1"). Earlier entries win
# so the selection is a pure, documented function of the profile (Requirement 4.6).
# (attribute-name substring, channel) — evaluated in this order.
_FLAG_CHANNEL_PRECEDENCE: tuple[tuple[str, str], ...] = (
    ("digital_app_user", "In-app"),
    ("email_valid", "Email"),
    ("mobile_valid", "SMS"),
)


class RuleBasedNamer:
    """Default rule-based :class:`PersonaNamer` (design D5, Requirement 4.6).

    Derives the name, description, and actions purely from the
    :class:`PersonaProfile`, leaning on ``profile.distinguishing`` (the top
    distinguishing attributes) together with ``top_categories`` and
    ``numeric_mean`` so the output is both meaningful and fully determined by the
    profile. Because every step is a deterministic function of the profile
    fields, an identical profile always produces identical output
    (Requirement 4.6).

    Instances are stateless; the same instance may name an entire Persona_Set.
    """

    def name(self, profile: PersonaProfile, taken: set[str]) -> PersonaNaming:
        """Name, describe, and recommend actions for one persona.

        Derives a base name from the persona's top distinguishing attributes,
        a one-line description summarising its leading numeric and categorical
        traits, and 2-3 recommended actions (Requirements 4.4, 4.5). The result
        is a pure function of ``profile`` (Requirement 4.6).

        Uniqueness (Requirement 4.9): if the derived base name already appears in
        ``taken``, a deterministic suffix is appended — first the cluster index
        (``" (cluster N)"``) and, only if that too collides, an ascending integer
        — until the name is unique. The caller must add the returned name to
        ``taken`` before naming the next persona, and must name personas in
        ascending cluster-label order, so the disambiguation is deterministic.

        Args:
            profile: The persona's computed profile (raw-scale stats plus
                distinguishing attributes).
            taken: Names already assigned to earlier personas in this
                Persona_Set. Not mutated by this method.

        Returns:
            A :class:`PersonaNaming` with a unique ``name``, a one-line
            ``description``, and 2 or 3 ``actions``.
        """
        base_name = self._base_name(profile)
        unique_name = self._disambiguate(base_name, profile.cluster_label, taken)
        description = self._description(profile)
        actions = self._actions(profile)
        return PersonaNaming(
            name=unique_name,
            description=description,
            actions=actions,
        )

    # -- name -------------------------------------------------------------

    def _base_name(self, profile: PersonaProfile) -> str:
        """Derive a base persona name from the top distinguishing attributes.

        Uses the first one or two entries of ``profile.distinguishing`` (already
        ranked and tie-broken deterministically by the profiling stage) to form
        a readable label such as ``"Monthly Income & Investment Ownership
        Persona"``. Falls back to a cluster-indexed label when no distinguishing
        attributes are available, keeping the result total and deterministic.
        """
        distinguishing = list(profile.distinguishing)
        if not distinguishing:
            return f"Persona {profile.cluster_label + 1}"

        lead = [_title_phrase(attr) for attr in distinguishing[:2]]
        joined = " & ".join(lead)
        return f"{joined} Persona"

    def _disambiguate(
        self, base_name: str, cluster_label: int, taken: set[str]
    ) -> str:
        """Return ``base_name`` made unique against ``taken`` deterministically.

        When ``base_name`` is free it is returned unchanged. Otherwise the
        cluster index is appended (``"<base> (cluster N)"``); if that is also
        taken, an ascending integer suffix is tried until a free name is found.
        The procedure depends only on ``base_name``, ``cluster_label``, and
        ``taken`` (Requirement 4.9).
        """
        if base_name not in taken:
            return base_name

        candidate = f"{base_name} (cluster {cluster_label})"
        if candidate not in taken:
            return candidate

        suffix = 2
        while True:
            numbered = f"{base_name} (cluster {cluster_label}) {suffix}"
            if numbered not in taken:
                return numbered
            suffix += 1

    # -- description ------------------------------------------------------

    def _description(self, profile: PersonaProfile) -> str:
        """Build a one-line description from the profile (Requirement 4.4).

        Opens with the persona's share of the clustered leads, then names its
        leading distinguishing trait together with the dominant category or mean
        value backing it. Purely derived from the profile fields.
        """
        parts: list[str] = [
            f"{profile.pct_of_leads:.1f}% of clustered leads"
        ]

        trait = self._lead_trait_phrase(profile)
        if trait:
            parts.append(trait)

        return "; ".join(parts) + "."

    def _lead_trait_phrase(self, profile: PersonaProfile) -> str:
        """Phrase describing the persona's single most distinguishing trait.

        Prefers the top distinguishing attribute; if it is categorical with a
        recorded top category, reports the dominant category, otherwise reports
        the numeric mean. Returns an empty string when nothing is available.
        """
        if not profile.distinguishing:
            return ""

        attr = profile.distinguishing[0]
        pretty = _prettify_attribute(attr)

        categories = profile.top_categories.get(attr)
        if categories:
            top_category, _count = categories[0]
            return f"led by {pretty} = {top_category}"

        if attr in profile.numeric_mean:
            mean_value = profile.numeric_mean[attr]
            return f"led by {pretty} (avg {mean_value:.2f})"

        return f"led by {pretty}"

    # -- actions ----------------------------------------------------------

    def _actions(self, profile: PersonaProfile) -> list[str]:
        """Derive 2-3 recommended campaign actions as campaign guidance (Req 4.5).

        Each returned action reads as guidance a campaign planner can act on. The
        first action is a channel-plus-offer-angle recommendation
        (for example "Best reached by SMS with a savings-bundle offer") whenever
        the profile supports naming both; the remaining actions turn the
        persona's leading distinguishing attributes into concrete messaging
        guidance. The result is always length 2 or 3 and is a pure, deterministic
        function of the profile (Requirement 4.6).

        Construction, in order:

        1. A combined channel + offer-angle action. The channel is chosen by
           :meth:`_suggested_channel` (deterministic precedence, documented
           there) and the offer angle by :meth:`_offer_angle` (deterministic
           signal ranking, documented there). Because a channel always resolves
           (falling back to a default) and the offer angle always resolves
           (falling back to a generic angle), this action is always produced and
           always names a channel from ``{In-app, Email, SMS}`` plus an angle.
        2. One guidance action per leading distinguishing attribute (up to two
           more), skipping any that would merely restate the offer angle already
           covered.
        3. Deterministic padding with a monitoring action so there are never
           fewer than 2 actions.

        The list is capped at 3 (Requirement 4.5).
        """
        channel = self._suggested_channel(profile)
        angle = self._offer_angle(profile)

        actions: list[str] = [
            f"Best reached by {channel} with a {angle}"
        ]

        for attr in profile.distinguishing[:3]:
            if len(actions) >= 3:
                break
            guidance = self._action_for_attribute(attr, profile)
            if guidance not in actions:
                actions.append(guidance)

        # Deterministic padding so there are never fewer than 2 actions.
        generic = [
            "Monitor join rate and refine the offer angle on the next send",
            "Hold back a small control group to measure incremental lift",
        ]
        for action in generic:
            if len(actions) >= 2:
                break
            if action not in actions:
                actions.append(action)

        # Never more than 3 actions (Requirement 4.5).
        return actions[:3]

    def _suggested_channel(self, profile: PersonaProfile) -> str:
        """Pick one channel from {In-app, Email, SMS} deterministically (Req 4.5).

        The channel is a pure function of the profile, chosen by a fixed,
        documented precedence so an identical profile always yields the same
        channel (Requirement 4.6):

        1. **Explicit channel category.** If any categorical attribute whose name
           contains "channel" (for example ``best_channel`` or ``channel``) has a
           dominant top category that already equals one of the three valid
           channel labels, that label is used directly. Such attributes are
           scanned in ascending attribute-name order and the first match wins.
        2. **Ownership / validity flags.** Otherwise the flag attributes in
           :data:`_FLAG_CHANNEL_PRECEDENCE` are tried in that fixed order
           (``digital_app_user`` -> In-app, then ``email_valid`` -> Email, then
           ``mobile_valid`` -> SMS); the first whose dominant top category is the
           "on" value (``"1"``) selects its channel.
        3. **Default.** If no channel signal is present, fall back to
           :data:`_DEFAULT_CHANNEL` ("Email").

        Only labels in :data:`_VALID_CHANNELS` are ever returned.
        """
        # 1. Explicit channel-like categorical attribute whose dominant value is
        #    already a valid channel label. Scan deterministically by name.
        for attr in sorted(profile.top_categories):
            if "channel" not in attr.lower():
                continue
            categories = profile.top_categories.get(attr)
            if not categories:
                continue
            dominant = categories[0][0]
            if dominant in _VALID_CHANNELS:
                return dominant

        # 2. Ownership / validity flags, in the fixed precedence order.
        for flag_name, channel in _FLAG_CHANNEL_PRECEDENCE:
            categories = profile.top_categories.get(flag_name)
            if not categories:
                continue
            dominant = categories[0][0]
            if dominant == "1":
                return channel

        # 3. Deterministic default.
        return _DEFAULT_CHANNEL

    def _offer_angle(self, profile: PersonaProfile) -> str:
        """Pick a short offer-angle phrase deterministically from the profile.

        The angle is derived from the persona's top distinguishing attributes in
        their existing (deterministic) ranked order, so the choice is a pure
        function of the profile (Requirement 4.6). The first distinguishing
        attribute that matches a known signal wins:

        - an inflow / deposit / balance signal -> a "savings-bundle offer";
        - a spend signal -> a "rewards offer";
        - an outflow signal (money leaving for other banks) -> a
          "win-back offer";
        - an investment / wealth signal -> a "wealth-building offer";
        - an ownership flag whose dominant value is "not owned" (``"0"``) -> a
          "cross-sell bundle offer".

        When no distinguishing attribute matches a known signal, the angle falls
        back to a generic "tailored offer".
        """
        for attr in profile.distinguishing:
            lowered = attr.lower()
            if any(token in lowered for token in ("inflow", "deposit", "balance")):
                return "savings-bundle offer"
            if "spend" in lowered:
                return "rewards offer"
            if "outflow" in lowered:
                return "win-back offer"
            if any(token in lowered for token in ("invest", "wealth")):
                return "wealth-building offer"
            if lowered.startswith("owns_"):
                categories = profile.top_categories.get(attr)
                if categories and categories[0][0] == "0":
                    return "cross-sell bundle offer"

        return "tailored offer"

    def _action_for_attribute(self, attr: str, profile: PersonaProfile) -> str:
        """Build campaign guidance anchored on one distinguishing attribute.

        For a categorical attribute the dominant category is referenced; for a
        numeric attribute the mean is referenced. Phrased as guidance a planner
        can act on, and deterministic given the profile (Requirement 4.6).
        """
        pretty = _prettify_attribute(attr)
        categories = profile.top_categories.get(attr)
        if categories:
            top_category, _count = categories[0]
            return f"Lead the message on {pretty} = {top_category}"
        if attr in profile.numeric_mean:
            return f"Highlight {pretty} as the campaign hook"
        return f"Highlight {pretty} as the campaign hook"
