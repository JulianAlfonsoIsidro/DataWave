"""Property test for campaign extraction validity (src/ai/extractor.py).

Feature: part7-AI-and-finishing, Property 2: Extraction output is always
valid and tagged.

No network: a fake Bedrock client and an explicit env mapping are injected,
and the Demo path is exercised with an empty env.
"""

from __future__ import annotations

import json

from hypothesis import given, settings, strategies as st

from ai import extractor
from webapp_core.threshold import THRESHOLD_SPECS, ThresholdType

FAKE_ENV = {
    "AWS_ACCESS_KEY_ID": "AKIAFAKE",
    "AWS_SECRET_ACCESS_KEY": "fake-secret",
    "AWS_REGION": "us-east-1",
    "BEDROCK_MODEL_ID": "fake.model",
}


class _FakeClient:
    def __init__(self, text: str) -> None:
        self._text = text

    def converse(self, **_kwargs):
        return {"output": {"message": {"content": [{"text": self._text}]}}}


_json_leaf = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(-10**9, 10**9),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=30),
)
_json_any = st.recursive(
    _json_leaf,
    lambda kids: st.one_of(
        st.lists(kids, max_size=4),
        st.dictionaries(st.text(max_size=12), kids, max_size=4),
    ),
    max_leaves=10,
)

# Values biased toward both valid and invalid choices for each field.
_text_or_json = st.one_of(_json_any, st.sampled_from(["Savings", "Time Deposit", "TOP_UP", "bogus"]))
_fields = st.fixed_dictionaries(
    {},
    optional={
        "product_type": st.one_of(st.sampled_from(extractor.PRODUCT_TYPE_OPTIONS), _text_or_json),
        "mechanic": st.one_of(st.sampled_from(extractor.MECHANIC_OPTIONS), _text_or_json),
        "threshold_type": st.one_of(
            st.sampled_from([t.value for t in ThresholdType]), _text_or_json
        ),
        "threshold_value": st.one_of(
            st.integers(-10**7, 10**7), st.floats(allow_nan=True, allow_infinity=True), _json_any
        ),
        "reward": st.one_of(st.text(max_size=300), _json_any),
        "eligible_segments": st.one_of(
            st.lists(st.sampled_from(list(extractor.KNOWN_SEGMENTS) + ["nope", " x "])),
            _json_any,
        ),
        "min_adb": st.one_of(
            st.integers(-10**7, 10**7), st.floats(allow_nan=True, allow_infinity=True), _json_any
        ),
        "channels": st.one_of(
            st.lists(st.sampled_from(["In-app", "Email", "SMS", "sms", "EMAIL", "Fax", "push"])),
            _json_any,
        ),
    },
)
_model_output = st.one_of(
    st.builds(lambda f, c: json.dumps({"fields": f, "context": c}), _fields, _json_any),
    st.builds(json.dumps, _fields),  # flat object
    st.builds(json.dumps, _json_any),  # wrong shape
    st.text(max_size=80),  # arbitrary (usually unparseable) text
)


@settings(max_examples=100, deadline=None)
@given(
    output=_model_output,
    document=st.text(max_size=200),
    use_bedrock=st.booleans(),
)
def test_extraction_output_is_always_valid_and_tagged(output, document, use_bedrock):
    """**Validates: Requirements 2.5, 2.6, 2.7, 2.9, 2.11**"""
    if use_bedrock:
        result = extractor.extract_campaign(
            document, client=_FakeClient(output), env=FAKE_ENV
        )
    else:
        result = extractor.extract_campaign(document, env={})  # Demo path

    assert result.mode in ("Bedrock", "Demo")
    if not use_bedrock:
        assert result.mode == "Demo"

    fields, tags = result.fields, result.tags

    # Every Campaign_Field has exactly one tag, consistent with presence.
    assert set(tags) == set(extractor.CAMPAIGN_FIELDS)
    assert set(fields) <= set(extractor.CAMPAIGN_FIELDS)
    for name in extractor.CAMPAIGN_FIELDS:
        expected = extractor.FOUND if name in fields else extractor.NEEDS_INPUT
        assert tags[name] == expected

    # Every present value is valid.
    if "product_type" in fields:
        assert fields["product_type"] in extractor.PRODUCT_TYPE_OPTIONS
    if "mechanic" in fields:
        assert fields["mechanic"] in extractor.MECHANIC_OPTIONS
    if "threshold_type" in fields:
        ttype = ThresholdType(fields["threshold_type"])
        if "threshold_value" in fields:
            spec = THRESHOLD_SPECS[ttype]
            assert spec.minimum <= fields["threshold_value"] <= spec.maximum
    else:
        assert "threshold_value" not in fields
    if "reward" in fields:
        assert 0 < len(fields["reward"]) <= extractor.MAX_REWARD_CHARS
    if "eligible_segments" in fields:
        segs = fields["eligible_segments"]
        assert segs and len(segs) == len(set(segs))
        assert set(segs) <= set(extractor.KNOWN_SEGMENTS)
    if "min_adb" in fields:
        assert fields["min_adb"] >= 0
    if "channels" in fields:
        chans = fields["channels"]
        assert chans and len(chans) == len(set(chans))
        assert set(chans) <= {"In-app", "Email", "SMS"}

    assert set(result.context) == set(extractor.CONTEXT_KEYS)
