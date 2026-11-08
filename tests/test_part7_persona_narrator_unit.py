"""Unit tests for the persona narrator (src/ai/persona_narrator.py, src/ai/mocks.py).

Covers valid JSON acceptance, each validation rule rejected individually,
per-persona fallback in ``BedrockNamer`` (fake client only, no network), and
Mock output hygiene and stability.

Validates: Requirements 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.12, 10.4, 10.5
"""

from __future__ import annotations

import copy
import json

import pytest

from ai.mocks import MockPersonaNamer, mock_persona_narration
from ai.persona_narrator import (
    BedrockNamer,
    PersonaAggregate,
    Trait,
    validate_narration,
)
from part5_personas.profile import PersonaProfile

FAKE_ENV = {
    "AWS_ACCESS_KEY_ID": "AKIAFAKEKEYID",
    "AWS_SECRET_ACCESS_KEY": "fake-secret",
    "AWS_REGION": "us-east-1",
    "BEDROCK_MODEL_ID": "fake.model",
}
BANNED = ("campaign hook", "led by", "(avg")

AGG = PersonaAggregate(
    size=120,
    share_pct=12.5,
    traits=(
        Trait("Retail Spending", "high", "1,200", "High Retail Spending"),
        Trait("Income", "high", "50", "High Income"),
    ),
    top_categories=(("Region", "North"),),
    response_rate_pct=None,
    channel_reach=(("In-app", 40.0), ("Email", 30.0)),
)

VALID = {
    "name": "Busy Everyday Spenders",
    "description": "About 12.5% of the audience. They spend often.",
    "difference": "They spend more than other groups.",
    "actions": [
        {"channel": "In-app", "angle": "Rewards", "message": "Show rewards on spending."},
        {"channel": "Email", "angle": "Savings", "message": "Share a savings bundle."},
    ],
}


def _with(**changes):
    obj = copy.deepcopy(VALID)
    obj.update(changes)
    return obj


def _without(key):
    obj = copy.deepcopy(VALID)
    del obj[key]
    return obj


def _action(**changes):
    action = {"channel": "SMS", "angle": "Reminder", "message": "Send a short reminder."}
    action.update(changes)
    return action


# ---------------------------------------------------------------------------
# validate_narration
# ---------------------------------------------------------------------------


def test_valid_json_accepted():
    result = validate_narration(copy.deepcopy(VALID), AGG, set())
    assert result is not None
    assert result["name"] == "Busy Everyday Spenders"
    assert result["difference"] == VALID["difference"]
    assert result["actions"][0] == "In-app: Rewards. Show rewards on spending."
    assert len(result["actions"]) == 2


def test_numbers_present_in_aggregate_accepted():
    obj = _with(description="Covers 120 customers, about 12.5% of leads. Income near 50.")
    assert validate_narration(obj, AGG, set()) is not None


def test_non_mapping_rejected():
    assert validate_narration(["not", "a", "dict"], AGG, set()) is None
    assert validate_narration(None, AGG, set()) is None


@pytest.mark.parametrize(
    "obj",
    [
        _with(name="Spenders"),                                  # 1 word
        _with(name="One Two Three Four Five"),                   # 5 words
        _with(name="Averyveryveryverylongword Anotherlongword Third"),  # > 40 chars
        _with(description="First. Second. Third."),              # 3 sentences
        _with(description="Word " * 70),                         # > 300 chars
        _with(difference="x " * 101),                            # > 200 chars
        _with(actions=[_action(message="m" * 161), _action()]),  # message > 160
        _with(actions=[_action(angle="a" * 161), _action()]),    # angle > 160
    ],
    ids=[
        "name_one_word", "name_five_words", "name_too_long",
        "description_three_sentences", "description_too_long",
        "difference_too_long", "message_too_long", "angle_too_long",
    ],
)
def test_length_violations_rejected(obj):
    assert validate_narration(obj, AGG, set()) is None


@pytest.mark.parametrize(
    "channel", ["Push", "email", "IN-APP", "Sms", "", None, 3]
)
def test_invalid_channel_rejected(channel):
    obj = _with(actions=[_action(channel=channel), _action(channel="Email")])
    assert validate_narration(obj, AGG, set()) is None


@pytest.mark.parametrize(
    "field,text",
    [
        ("name", "Spender 999 Group"),
        ("description", "About 77% of the audience. They spend."),
        ("difference", "They spend 4242 more."),
    ],
)
def test_number_not_in_aggregate_rejected(field, text):
    assert validate_narration(_with(**{field: text}), AGG, set()) is None


@pytest.mark.parametrize("key", ["name", "description", "difference", "actions"])
def test_missing_field_rejected(key):
    assert validate_narration(_without(key), AGG, set()) is None


@pytest.mark.parametrize("key", ["name", "description", "difference"])
@pytest.mark.parametrize("empty", ["", "   ", None])
def test_empty_field_rejected(key, empty):
    assert validate_narration(_with(**{key: empty}), AGG, set()) is None


@pytest.mark.parametrize("missing", ["channel", "angle", "message"])
def test_action_missing_part_rejected(missing):
    bad = _action()
    del bad[missing]
    assert validate_narration(_with(actions=[bad, _action(channel="Email")]), AGG, set()) is None


@pytest.mark.parametrize("empty_key", ["angle", "message"])
def test_action_empty_part_rejected(empty_key):
    bad = _action(**{empty_key: "  "})
    assert validate_narration(_with(actions=[bad, _action(channel="Email")]), AGG, set()) is None


def test_action_count_bounds():
    assert validate_narration(_with(actions=[_action()]), AGG, set()) is None
    assert validate_narration(_with(actions=[]), AGG, set()) is None
    four = [_action(), _action(channel="Email"), _action(channel="In-app"), _action()]
    assert validate_narration(_with(actions=four), AGG, set()) is None
    three = four[:3]
    assert validate_narration(_with(actions=three), AGG, set()) is not None


def test_actions_not_a_list_rejected():
    assert validate_narration(_with(actions="In-app: do it"), AGG, set()) is None
    assert validate_narration(_with(actions=["In-app: do it", "Email: do it"]), AGG, set()) is None


def test_duplicate_name_rejected_case_insensitive():
    assert validate_narration(copy.deepcopy(VALID), AGG, {"busy everyday spenders"}) is None
    assert validate_narration(copy.deepcopy(VALID), AGG, {"Other Name"}) is not None


@pytest.mark.parametrize(
    "obj",
    [
        _with(name="Retail_Spend Fans"),
        _with(description="They show high_income. Often."),
        _with(difference="Driven by ext_outflow_ratio."),
        _with(actions=[_action(angle="Win_back"), _action(channel="Email")]),
        _with(actions=[_action(message="Use pay_roll offers."), _action(channel="Email")]),
    ],
    ids=["name", "description", "difference", "angle", "message"],
)
def test_underscores_rejected(obj):
    assert validate_narration(obj, AGG, set()) is None


@pytest.mark.parametrize(
    "phrase",
    ["Campaign Hook", "led by savings", "Led By income", "(avg 40)"],
)
def test_banned_phrases_rejected(phrase):
    assert validate_narration(_with(difference=f"This group is {phrase} here."), AGG, set()) is None
    obj = _with(actions=[_action(message=f"Try {phrase} now."), _action(channel="Email")])
    assert validate_narration(obj, AGG, set()) is None


# ---------------------------------------------------------------------------
# BedrockNamer with a fake client
# ---------------------------------------------------------------------------


def _profile(size: int, pct: float, label: int) -> PersonaProfile:
    return PersonaProfile(
        cluster_label=label,
        size=size,
        pct_of_leads=pct,
        numeric_mean={"retail_spend": 1200.0},
        numeric_median={"retail_spend": 1100.0},
        top_categories={},
        distinguishing=["retail_spend"],
        distinguishing_directions={"retail_spend": "high"},
        channel_reach={"Email": {"share": 0.4, "overall": 0.3, "n": float(size)}},
    )


class SizeRoutedClient:
    """Replies by persona size: 120 gets valid JSON, 80 gets junk, 60 raises."""

    def __init__(self) -> None:
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        body = json.loads(kwargs["messages"][0]["content"][0]["text"])
        size = body["persona"]["size"]
        if size == 60:
            raise RuntimeError("boom")
        if size == 120:
            reply = json.dumps(VALID)
        else:
            reply = json.dumps(_with(name="Bad_Name Group"))
        return {"output": {"message": {"content": [{"text": reply}]}}}


def test_one_failing_persona_does_not_affect_others():
    client = SizeRoutedClient()
    namer = BedrockNamer(client=client, env=FAKE_ENV)
    taken: set[str] = set()

    good = namer.name(_profile(120, 12.5, 0), taken)
    taken.add(good["name"])
    bad = namer.name(_profile(80, 8.0, 1), taken)
    taken.add(bad["name"])
    raised = namer.name(_profile(60, 6.0, 2), taken)
    taken.add(raised["name"])
    good_again = namer.name(_profile(120, 12.5, 3), taken)  # name now taken -> Demo

    assert client.calls == 4
    assert good["name"] == "Busy Everyday Spenders"
    assert namer.sources[good["name"]] == "Bedrock"
    assert namer.sources[bad["name"]] == "Demo"
    assert namer.sources[raised["name"]] == "Demo"
    assert namer.sources[good_again["name"]] == "Demo"
    names = [good["name"], bad["name"], raised["name"], good_again["name"]]
    assert len({n.casefold() for n in names}) == 4
    for naming in (bad, raised, good_again):
        assert "_" not in naming["name"]


def test_no_credentials_uses_mock_for_every_persona():
    client = SizeRoutedClient()
    namer = BedrockNamer(client=client, env={})
    out = namer.name(_profile(120, 12.5, 0), set())
    assert client.calls == 0
    assert namer.sources[out["name"]] == "Demo"


# ---------------------------------------------------------------------------
# Mock hygiene and stability
# ---------------------------------------------------------------------------


def _all_text(out) -> list[str]:
    return [out["name"], out["description"], out["difference"], *out["actions"]]


def test_mock_free_of_underscores_and_banned_phrases():
    out = mock_persona_narration(AGG, set())
    for text in _all_text(out):
        assert "_" not in text
        assert not any(b in text.lower() for b in BANNED)


def test_mock_output_passes_bedrock_style_validation_limits():
    out = mock_persona_narration(AGG, set())
    assert 2 <= len(out["name"].split()) <= 4 and len(out["name"]) <= 40
    assert len(out["description"]) <= 300
    assert len(out["difference"]) <= 200
    assert 2 <= len(out["actions"]) <= 3
    for action in out["actions"]:
        assert action.split(":", 1)[0] in ("In-app", "Email", "SMS")


def test_mock_stable_on_repeat():
    a = mock_persona_narration(AGG, {"x"})
    b = mock_persona_narration(AGG, {"x"})
    assert a == b


def test_mock_name_unique_against_taken_and_taken_unchanged():
    first = mock_persona_narration(AGG, set())["name"]
    taken = {first.upper()}
    snapshot = set(taken)
    second = mock_persona_narration(AGG, taken)["name"]
    assert second.casefold() != first.casefold()
    assert taken == snapshot


def test_mock_with_no_traits_is_clean():
    bare = PersonaAggregate(size=10, share_pct=5.0, traits=(), top_categories=())
    out = mock_persona_narration(bare, set())
    assert 2 <= len(out["actions"]) <= 3
    for text in _all_text(out):
        assert "_" not in text
        assert not any(b in text.lower() for b in BANNED)


def test_mock_persona_namer_from_profile_is_stable_and_clean():
    namer = MockPersonaNamer()
    p = _profile(120, 12.5, 0)
    a = namer.name(p, set())
    b = namer.name(p, set())
    assert a == b
    for text in [a["name"], a["description"], a["difference"], *a["actions"]]:
        assert "_" not in text
        assert not any(x in text.lower() for x in BANNED)
