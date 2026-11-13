"""Persona Narrator: Bedrock-backed persona naming with a Mock fallback.

``BedrockNamer`` satisfies the ``part5_personas.naming.PersonaNamer`` Protocol,
so ``build_persona_sets(..., namer=BedrockNamer())`` is the only integration
point. Clustering, preprocessing, and assignment are untouched (Requirement 6.1).

Per persona it sends one request holding only that persona's
:class:`PersonaAggregate` in plain-language labels (Requirements 6.2, 6.13),
validates the reply with :func:`validate_narration` (Requirements 6.3 to 6.7),
and falls back to :class:`ai.mocks.MockPersonaNamer` for that persona only
(Requirement 6.8). ``sources`` records Bedrock or Demo for each persona name so
the page can show the Demo badge (Requirement 6.11).

No Streamlit imports. No numeric business logic: every number the model may
mention must already be present in the aggregate (Requirement 6.5).

Part 9 round 3 (Requirements 31, 33): each persona's call is recorded in
``records`` with its mode, token Usage, seconds and fallback reason, and the
reply is capped with ``inferenceConfig.maxTokens``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from ai.bedrock import converse
from ai.mocks import MockPersonaNamer
from labels import plain_label
from part5_personas.labels import (
    category_phrase,
    is_flag_attribute,
    is_text_category,
)
from part5_personas.naming import PersonaNamer, PersonaNaming
from part5_personas.profile import PersonaProfile

VALID_CHANNELS: tuple[str, ...] = ("In-app", "Email", "SMS")
MAX_REPLY_TOKENS = 800   # inferenceConfig.maxTokens; room for reasoning (design "Limits")

NAME_MIN_WORDS, NAME_MAX_WORDS, NAME_MAX_CHARS = 2, 4, 40
DESCRIPTION_MAX_SENTENCES, DESCRIPTION_MAX_CHARS = 2, 300
DIFFERENCE_MAX_CHARS = 200
ACTIONS_MIN, ACTIONS_MAX = 2, 3
MESSAGE_MAX_CHARS = 160

# Phrases Requirement 6.10 bans, matched case-insensitively.
_BANNED_PHRASE = re.compile(r"campaign hook|\bled by\b|\(avg\b", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_DIRECTION_WORDS = {
    "high": "High",
    "low": "Low",
    "more": "More",
    "fewer": "Fewer",
}
_FLAG_DIRECTION_MAP = {"high": "more", "low": "fewer"}

SYSTEM_PROMPT = (
    "You name customer personas for a bank marketing team. You receive one "
    "persona's aggregate facts as JSON. Reply with JSON only, no prose, using "
    'keys: "name" (2 to 4 words, at most 40 characters), "description" (1 to 2 '
    'sentences, at most 300 characters), "difference" (why this persona differs '
    'from others, at most 200 characters), "actions" (2 to 3 objects with '
    '"channel" exactly one of In-app, Email, SMS, an "angle", and a "message" '
    "of at most 160 characters). Use plain English. Use only numbers present in "
    "the input. Never use field codes or underscores."
)


@dataclass(frozen=True)
class Trait:
    """One distinguishing trait in plain language."""

    label: str            # plain Title Case label, e.g. "Retail Spending"
    direction: str        # high / low / more / fewer / flat
    value_text: str       # rounded value or category text, "" when none
    phrase: str           # ready-to-use phrase, e.g. "High Retail Spending"


@dataclass(frozen=True)
class PersonaAggregate:
    """Everything the narrator may see about one persona (Requirement 6.2)."""

    size: int
    share_pct: float
    traits: tuple[Trait, ...]
    top_categories: tuple[tuple[str, str], ...]   # (plain attribute label, category)
    response_rate_pct: float | None = None
    channel_reach: tuple[tuple[str, float], ...] = ()  # (channel, persona share %)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).replace("_", " ")).strip()


def _format_value(attr: str, value: float) -> str:
    if "share" in attr or attr.endswith("_ratio"):
        return f"{value * 100:.0f}%"
    if abs(value) >= 100:
        return f"{value:,.0f}"
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _flag_word(category: str) -> str:
    return {"1": "yes", "0": "no"}.get(category, category)


def _focus_category(profile: PersonaProfile, attr: str) -> str | None:
    categories = profile.top_categories.get(attr)
    if not categories:
        return None
    if not is_text_category(attr, [str(c) for c, _n in categories]):
        return None
    focus = profile.focus_categories.get(attr)
    return str(focus) if focus is not None else str(categories[0][0])


def _build_trait(profile: PersonaProfile, attr: str) -> Trait:
    label = _clean(plain_label(attr))
    direction = profile.distinguishing_directions.get(attr) or "flat"
    focus = _focus_category(profile, attr)
    if focus is not None:
        phrase = _clean(category_phrase(attr, _clean(focus)))
        if direction == "fewer":
            phrase = f"Fewer {phrase}"
        return Trait(label, direction, _clean(focus), phrase)
    if is_flag_attribute(attr):
        direction = _FLAG_DIRECTION_MAP.get(direction, direction)
    word = _DIRECTION_WORDS.get(direction, "")
    phrase = f"{word} {label}".strip()
    value = ""
    categories = profile.top_categories.get(attr)
    if categories:
        value = _flag_word(_clean(categories[0][0]))
    elif attr in profile.numeric_mean:
        value = _format_value(attr, profile.numeric_mean[attr])
    return Trait(label, direction, value, phrase)


def build_aggregate(profile: PersonaProfile) -> PersonaAggregate:
    """Convert a profile to a plain-language, aggregate-only record.

    Raw feature codes become Label_Map labels; no client id or per-client row
    is carried (Requirements 6.2, 6.13). Pure and deterministic.
    """
    traits = tuple(_build_trait(profile, a) for a in profile.distinguishing)
    cats: list[tuple[str, str]] = []
    for attr in sorted(profile.top_categories):
        top = profile.top_categories[attr]
        if not top:
            continue
        focus = _focus_category(profile, attr)
        value = focus if focus is not None else _flag_word(str(top[0][0]))
        cats.append((_clean(plain_label(attr)), _clean(value)))
    reach = tuple(
        (channel, round(float(profile.channel_reach[channel]["share"]) * 100.0, 1))
        for channel in VALID_CHANNELS
        if channel in profile.channel_reach
    )
    return PersonaAggregate(
        size=int(profile.size),
        share_pct=float(profile.pct_of_leads),
        traits=traits,
        top_categories=tuple(cats[:6]),
        response_rate_pct=None,
        channel_reach=reach,
    )


def aggregate_payload(agg: PersonaAggregate) -> dict[str, Any]:
    """JSON-safe request body: this persona's aggregate and nothing else."""
    return {
        "persona": {
            "size": agg.size,
            "share_pct": agg.share_pct,
            "traits": [
                {"label": t.label, "direction": t.direction, "value": t.value_text}
                for t in agg.traits
            ],
            "top_categories": [
                {"attribute": a, "category": c} for a, c in agg.top_categories
            ],
            "response_rate_pct": agg.response_rate_pct,
            "channel_reach_pct": {c: v for c, v in agg.channel_reach},
        }
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def numbers_in(text: str) -> set[float]:
    """All numbers mentioned in ``text`` (thousands commas removed)."""
    return {float(m) for m in _NUMBER.findall(_THOUSANDS.sub("", text))}


def allowed_numbers(agg: PersonaAggregate) -> set[float]:
    """Numbers the narration may mention: those present in the aggregate."""
    allowed: set[float] = set()
    floats = [float(agg.size), agg.share_pct]
    if agg.response_rate_pct is not None:
        floats.append(float(agg.response_rate_pct))
    floats.extend(v for _c, v in agg.channel_reach)
    for value in floats:
        allowed.update({value, float(round(value)), round(value, 1)})
    texts = [t.value_text for t in agg.traits] + [t.phrase for t in agg.traits]
    texts += [c for _a, c in agg.top_categories]
    for text in texts:
        allowed |= numbers_in(text)
    return allowed


def _bad_text(text: str) -> bool:
    return "_" in text or bool(_BANNED_PHRASE.search(text))


def _text(obj: Any, limit: int) -> str | None:
    if not isinstance(obj, str):
        return None
    value = obj.strip()
    if not value or len(value) > limit:
        return None
    return value


def validate_narration(
    obj: Any, agg: PersonaAggregate, taken: set[str]
) -> PersonaNaming | None:
    """Return a ``PersonaNaming`` if ``obj`` meets every rule, else ``None``.

    Rules: Requirements 6.3 (shape and limits), 6.4 (exact channels), 6.5
    (numbers must come from the aggregate), 6.6 (missing/empty/length/action
    count), 6.7 (unique name), 6.10 (no codes or banned phrases).
    """
    if not isinstance(obj, Mapping):
        return None
    name = _text(obj.get("name"), NAME_MAX_CHARS)
    description = _text(obj.get("description"), DESCRIPTION_MAX_CHARS)
    difference = _text(obj.get("difference"), DIFFERENCE_MAX_CHARS)
    raw_actions = obj.get("actions")
    if name is None or description is None or difference is None:
        return None
    if not NAME_MIN_WORDS <= len(name.split()) <= NAME_MAX_WORDS:
        return None
    sentences = [s for s in _SENTENCE_SPLIT.split(description) if s.strip()]
    if not 1 <= len(sentences) <= DESCRIPTION_MAX_SENTENCES:
        return None
    if not isinstance(raw_actions, list) or not ACTIONS_MIN <= len(raw_actions) <= ACTIONS_MAX:
        return None

    actions: list[str] = []
    for item in raw_actions:
        if not isinstance(item, Mapping):
            return None
        channel = item.get("channel")
        if channel not in VALID_CHANNELS:
            return None
        angle = _text(item.get("angle"), MESSAGE_MAX_CHARS)
        message = _text(item.get("message"), MESSAGE_MAX_CHARS)
        if angle is None or message is None:
            return None
        actions.append(f"{channel}: {angle.rstrip('.')}. {message}")

    if any(_bad_text(t) for t in (name, description, difference, *actions)):
        return None
    allowed = allowed_numbers(agg)
    if not numbers_in(" ".join((name, description, difference))) <= allowed:
        return None
    if name.casefold() in {t.casefold() for t in taken}:
        return None
    return PersonaNaming(
        name=name, description=description, actions=actions, difference=difference
    )


# ---------------------------------------------------------------------------
# Namer
# ---------------------------------------------------------------------------


class BedrockNamer:
    """``PersonaNamer`` that asks Bedrock per persona and falls back per persona."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        env: Mapping[str, str] | None = None,
        mock: PersonaNamer | None = None,
    ) -> None:
        self._client = client
        self._env = env
        self._mock: PersonaNamer = mock if mock is not None else MockPersonaNamer()
        self._sources: dict[str, Literal["Bedrock", "Demo"]] = {}
        self._records: list[dict[str, Any]] = []

    @property
    def sources(self) -> dict[str, Literal["Bedrock", "Demo"]]:
        """Persona name -> ``"Bedrock"`` or ``"Demo"`` (Requirement 6.11)."""
        return dict(self._sources)

    @property
    def records(self) -> list[dict[str, Any]]:
        """One entry per persona: name, mode, usage, seconds, reason."""
        return list(self._records)

    def name(self, profile: PersonaProfile, taken: set[str]) -> PersonaNaming:
        agg = build_aggregate(profile)
        result = converse(
            SYSTEM_PROMPT,
            aggregate_payload(agg),
            expect_json=True,
            client=self._client,
            env=self._env,
            max_tokens=MAX_REPLY_TOKENS,
        )
        reason = result.reason
        if result.mode == "Bedrock":
            naming = validate_narration(result.parsed, agg, taken)
            if naming is not None:
                self._sources[naming["name"]] = "Bedrock"
                self._records.append({"name": naming["name"], "mode": "Bedrock",
                                      "usage": result.usage, "seconds": result.seconds,
                                      "reason": ""})
                return naming
            reason = "invalid_reply"
        naming = self._mock.name(profile, taken)
        self._sources[naming["name"]] = "Demo"
        self._records.append({"name": naming["name"], "mode": "Demo", "usage": result.usage,
                              "seconds": result.seconds, "reason": reason})
        return naming


def estimated_tokens_per_persona(profile: PersonaProfile) -> int:
    """Input estimate for one persona's request (labelled an estimate)."""
    from ai.bedrock import estimate_tokens, request_text

    return estimate_tokens(request_text(SYSTEM_PROMPT, aggregate_payload(build_aggregate(profile))))
