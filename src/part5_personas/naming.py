"""Persona naming for the Persona_Pipeline (design D5).

Turns a :class:`~part5_personas.profile.PersonaProfile` into a human-facing
``name``, a one-line ``description``, and 2-3 recommended campaign ``actions``.
Each action reads as campaign guidance a planner can act on and, where the
profile supports it, names a suggested channel (one of "In-app", "Email", "SMS")
together with an offer angle â€” for example "Best reached by SMS with a
savings-bundle offer" (Requirement 4.5). All derivation is a pure, deterministic
function of the profile's fields so an identical profile always yields identical
output (Requirement 4.6); the module holds no Streamlit imports and no
modelling.

Data-driven channel (task 8.1e, Requirement 4.5): when
``PersonaProfile.channel_reach`` is present, a channel *stands out* if the
persona's reach exceeds the group's by >= 3 pp and z >= 2; the strongest (highest
z, ties In-app/Email/SMS) is "Best reached by {channel}". Otherwise the first
action reads "Reachable on every channel about equally; lead with {channel}
(widest reach). Offer angle: a {angle}." (task 8.1f). With empty ``channel_reach`` the previous
category/flag/default precedence applies unchanged.

Design D5 â€” the pipeline depends only on the narrow :class:`PersonaNamer`
Protocol, never on a concrete namer type, so a future ``BedrockNamer`` living in
its own module can implement the same ``name(profile, taken) -> PersonaNaming``
signature and be swapped in at the call site with no pipeline or page changes
(Requirement 4.8). :class:`RuleBasedNamer` is the default implementation.

Direction-aware names (design D5 / Requirement 4.4): the base name composes the
persona's top distinguishing attributes rendered in shared plain-language labels
(from :mod:`part5_personas.labels`, so this module never imports ``app/``) plus a
direction word â€” High/Low for numeric attributes, More/Fewer for categorical or
flag attributes â€” read from ``PersonaProfile.distinguishing_directions``. Two
personas sharing the same top attributes but differing in direction therefore get
different names.

Uniqueness contract (Requirement 4.9): :meth:`RuleBasedNamer.name` takes a
``taken`` set of names already assigned within the current Persona_Set. If the
derived base name is already in ``taken``, the name is first extended with the
persona's third distinguishing attribute and, only if that still collides, a
letter suffix (" (A)", " (B)", ...) is appended until the name is unique. The
*caller* is responsible for adding each returned name to ``taken`` before naming
the next persona, and personas must be named in ascending cluster-label order, so
disambiguation is fully deterministic.
"""

from __future__ import annotations

import math
from typing import Protocol, TypedDict, runtime_checkable

from part5_personas.labels import (
    attribute_label,
    category_phrase,
    is_flag_attribute,
    is_text_category,
)
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


def _prettify_attribute(attr: str) -> str:
    """Business label for a raw attribute column (task 8.1h, Requirement 4.11).

    Delegates to the shared :func:`part5_personas.labels.attribute_label` so
    descriptions and actions never show raw column wording ("total_out",
    "inflow share payroll"). Pure and deterministic (Requirement 4.6).
    """
    return attribute_label(attr)


def _is_share_attribute(attr: str) -> bool:
    """True for 0-1 share/ratio columns, which read better as a percentage."""
    return "share" in attr or attr.endswith("_ratio")


def _format_mean(attr: str, value: float) -> str:
    """Readable average: percent for shares, thousands-separated otherwise."""
    if _is_share_attribute(attr):
        return f"{value * 100:.0f}%"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _flag_word(category: str) -> str:
    """Yes/no wording for a 0/1 flag category; other values pass through."""
    return {"1": "yes", "0": "no"}.get(category, category)

def _title_phrase(attr: str) -> str:
    """Title-case a prettified attribute for use inside a persona name."""
    return _prettify_attribute(attr).title()


# Direction word -> the human-facing prefix used inside a persona name
# (design D5 / Requirement 4.4). Numeric contrasts read "High"/"Low"; categorical
# or flag contrasts read "More"/"Fewer"; a "flat" (no-contrast) direction omits
# the prefix entirely so the label stands alone.
_DIRECTION_WORDS: dict[str, str] = {
    "high": "High",
    "low": "Low",
    "more": "More",
    "fewer": "Fewer",
    "flat": "",
}


# For flag attributes, numeric-style directions are remapped to More/Fewer.
_FLAG_DIRECTION_MAP: dict[str, str] = {"high": "more", "low": "fewer"}


def _name_fragment(attr: str, direction: str | None) -> str:
    """Compose one "<Direction> <label>" fragment for a persona name (design D5).

    Renders a single distinguishing attribute as a plain-language fragment: the
    shared business label from :func:`part5_personas.labels.attribute_label`
    (title-cased for the name) prefixed by the direction word mapped from
    ``direction`` (``high``/``low`` -> "High"/"Low", ``more``/``fewer`` ->
    "More"/"Fewer"). A ``"flat"``, unknown, or missing direction drops the prefix
    so the label stands on its own. Pure and deterministic (Requirement 4.6).
    """
    label = attribute_label(attr).title()
    if is_flag_attribute(attr):
        # Flag attributes read More/Fewer, never High/Low.
        direction = _FLAG_DIRECTION_MAP.get(direction or "", direction)
    prefix = _DIRECTION_WORDS.get(direction or "", "")
    return f"{prefix} {label}".strip()


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
# (attribute-name substring, channel) â€” evaluated in this order.
_FLAG_CHANNEL_PRECEDENCE: tuple[tuple[str, str], ...] = (
    ("digital_app_user", "In-app"),
    ("email_valid", "Email"),
    ("mobile_valid", "SMS"),
)


# Data-driven channel rule thresholds (task 8.1e, Requirement 4.5).
CHANNEL_MIN_GAP_PP = 3.0
CHANNEL_MIN_Z = 2.0
_CHANNEL_ORDER = ("In-app", "Email", "SMS")


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
        ``taken``, the name is first *extended* with the persona's third
        distinguishing attribute (direction + label) and, only if that too
        collides, a letter suffix (``" (A)"``, ``" (B)"``, ...) is appended until
        the name is unique. The caller must add the returned name to ``taken``
        before naming the next persona, and must name personas in ascending
        cluster-label order, so the disambiguation is deterministic.

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
        unique_name = self._disambiguate(base_name, profile, taken)
        description = self._description(profile)
        actions = self._actions(profile)
        return PersonaNaming(
            name=unique_name,
            description=description,
            actions=actions,
        )

    # -- name -------------------------------------------------------------

    def _base_name(self, profile: PersonaProfile) -> str:
        """Compose a direction-aware base name from distinguishing attributes (D5).

        Reads the first two entries of ``profile.distinguishing`` (already ranked
        and tie-broken by the profiling stage) and renders each as a
        ``"<Direction> <plain label>"`` fragment â€” High/Low for numeric
        attributes, More/Fewer for categorical/flag attributes â€” using the
        direction word stored on ``profile.distinguishing_directions`` and the
        shared business label from :func:`part5_personas.labels.attribute_label`.
        The two fragments are joined with " / " (e.g.
        ``"High Total Outflows / Fewer App Users"``); the redundant trailing
        "Persona" is dropped (Requirement 4.4). Two personas sharing the same top
        attributes but differing in direction therefore get different names.

        Falls back to a cluster-indexed label (``"Persona N"``) when no
        distinguishing attributes are available, keeping the result total and a
        pure deterministic function of the profile (Requirement 4.6).
        """
        distinguishing = list(profile.distinguishing)
        if not distinguishing:
            return f"Persona {profile.cluster_label + 1}"

        fragments = [self._fragment(profile, attr) for attr in distinguishing[:2]]
        return " / ".join(fragment for fragment in fragments if fragment)

    def _disambiguate(
        self, base_name: str, profile: PersonaProfile, taken: set[str]
    ) -> str:
        """Return ``base_name`` made unique against ``taken`` deterministically (D5).

        When ``base_name`` is free it is returned unchanged. Otherwise, in order
        (Requirement 4.9):

        1. **Extend** the name with the persona's *third* distinguishing attribute
           rendered as a direction + label fragment (``"<base> / <third>"``) and
           retry â€” two personas that share their top two distinguishing attributes
           often differ on the third.
        2. **Letter suffix.** If the extended name is still taken (or there is no
           usable third attribute), append an ascending letter suffix
           (``" (A)"``, ``" (B)"``, ..., then ``" (AA)"`` and onward) to whichever
           name was built until a free name is found â€” never a ``"(cluster N)"``
           suffix.

        The procedure depends only on ``base_name``, ``profile``, and ``taken``,
        so it is deterministic (Requirement 4.6).
        """
        if base_name not in taken:
            return base_name

        # 1. Extend with the third distinguishing attribute, if any.
        distinguishing = list(profile.distinguishing)
        candidate = base_name
        if len(distinguishing) >= 3:
            third = self._fragment(profile, distinguishing[2])
            if third:
                extended = f"{base_name} / {third}"
                if extended not in taken:
                    return extended
                candidate = extended

        # 2. Letter suffix on whichever name we built (base or extended).
        index = 0
        while True:
            suffix = self._letter_suffix(index)
            lettered = f"{candidate} ({suffix})"
            if lettered not in taken:
                return lettered
            index += 1

    def _shown_category(self, profile: PersonaProfile, attr: str) -> str:
        """Category shown in the description/action: focus, else most common."""
        focus = self._focus_category(profile, attr)
        return focus if focus is not None else str(profile.top_categories[attr][0][0])

    @staticmethod
    def _focus_category(profile: PersonaProfile, attr: str) -> str | None:
        """Focus category of a non-flag text attribute, or None (task 8.1g).

        Uses ``profile.focus_categories[attr]``; when absent (hand-built profiles)
        falls back to the most common category. Returns None for flags, numerics
        and attributes with no recorded categories.
        """
        categories = profile.top_categories.get(attr)
        if not categories:
            return None
        if not is_text_category(attr, [str(c) for c, _n in categories]):
            return None
        focus = profile.focus_categories.get(attr)
        return str(focus) if focus is not None else str(categories[0][0])

    def _fragment(self, profile: PersonaProfile, attr: str) -> str:
        """One name fragment: focus-category wording for text, else unchanged.

        Text categoricals read "<c> Age Band" etc. (more dropped, a rare fewer
        reads "Fewer <phrase>"); flags and numerics use :func:`_name_fragment`.
        """
        direction = profile.distinguishing_directions.get(attr)
        focus = self._focus_category(profile, attr)
        if focus is None:
            return _name_fragment(attr, direction)
        phrase = category_phrase(attr, focus)
        return f"Fewer {phrase}" if direction == "fewer" else phrase

    @staticmethod
    def _letter_suffix(index: int) -> str:
        """Map ``0, 1, 2, ...`` to ``"A", "B", ..., "Z", "AA", "AB", ...``.

        A deterministic bijective base-26 letter sequence used for the
        last-resort disambiguation suffix (Requirement 4.9), so an unbounded number
        of collisions still resolves to a unique, letter-based name.
        """
        letters = ""
        n = index
        while True:
            letters = chr(ord("A") + n % 26) + letters
            n = n // 26 - 1
            if n < 0:
                break
        return letters

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
            top_category = self._shown_category(profile, attr)
            return f"led by {pretty} = {_flag_word(top_category)}"

        if attr in profile.numeric_mean:
            mean_value = profile.numeric_mean[attr]
            return f"led by {pretty} (avg {_format_mean(attr, mean_value)})"

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
        angle = self._offer_angle(profile)

        if profile.channel_reach:
            # Data-driven rule (task 8.1e); see :meth:`_reach_channel`.
            channel, stands_out = self._reach_channel(profile)
            if stands_out:
                first = f"Best reached by {channel} with a {angle}"
            else:
                first = (
                    "Reachable on every channel about equally; lead with "
                    f"{channel} (widest reach). Offer angle: a {angle}."
                )
        else:
            channel = self._suggested_channel(profile)
            first = f"Best reached by {channel} with a {angle}"

        actions: list[str] = [first]

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

    def _reach_channel(self, profile: PersonaProfile) -> tuple[str, bool]:
        """Choose the channel from ``profile.channel_reach`` (task 8.1e, Req 4.5).

        For each channel (order In-app, Email, SMS) with ``gap = (share - overall)``
        in percentage points and ``z = (share - overall) / sqrt(overall *
        (1 - overall) / n)`` (``z = 0`` when the standard error is 0), the channel
        *stands out* when ``gap >= CHANNEL_MIN_GAP_PP`` and ``z >= CHANNEL_MIN_Z``.
        Returns ``(channel, True)`` for the highest-z stand-out (ties by channel
        order), else ``(widest-reach channel, False)`` (highest persona share, ties
        by channel order). Pure and deterministic.
        """
        stand_outs: list[tuple[float, int, str]] = []
        widest: list[tuple[float, int, str]] = []
        for order, channel in enumerate(_CHANNEL_ORDER):
            entry = profile.channel_reach.get(channel)
            if not entry:
                continue
            share = float(entry["share"])
            overall = float(entry["overall"])
            n = float(entry["n"])
            variance = overall * (1.0 - overall) / n if n > 0 else 0.0
            se = math.sqrt(variance) if variance > 0 else 0.0
            z = (share - overall) / se if se > 0 else 0.0
            gap_pp = (share - overall) * 100.0
            widest.append((-share, order, channel))
            if gap_pp >= CHANNEL_MIN_GAP_PP and z >= CHANNEL_MIN_Z:
                stand_outs.append((-z, order, channel))
        if stand_outs:
            return min(stand_outs)[2], True
        if widest:
            return min(widest)[2], False
        return _DEFAULT_CHANNEL, False

    def _suggested_channel(self, profile: PersonaProfile) -> str:
        """Pick one channel from {In-app, Email, SMS} deterministically (Req 4.5).

        Used only when ``profile.channel_reach`` is empty; otherwise the
        data-driven :meth:`_reach_channel` applies.

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
            top_category = self._shown_category(profile, attr)
            return f"Lead the message on {pretty} = {_flag_word(top_category)}"
        if attr in profile.numeric_mean:
            return f"Highlight {pretty} as the campaign hook"
        return f"Highlight {pretty} as the campaign hook"
