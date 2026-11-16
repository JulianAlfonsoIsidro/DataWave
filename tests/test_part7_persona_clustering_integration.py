"""Integration test: AI narration leaves persona clustering unchanged (task 11.4).

With the ``BedrockNamer`` in Demo Mode (no credentials, no network), a persona
run at seed 42 produces the same clusters as the ``RuleBasedNamer``: same group
keys, same ``k``, same cluster labels and sizes, and the same lead membership.
Only the persona name/description text may differ (Requirement 6.1).

No network is attempted: the Bedrock namer is built with ``env={}``, and the
``narration="ai"`` path runs with the AWS variables cleared and ``.env`` loading
disabled. The test is read-only against ``data/`` and ``outputs/``.
"""

from __future__ import annotations

import pytest

from ai.persona_narrator import BedrockNamer
from ai.bedrock import REQUIRED_ENV
from part5_personas.config import Config
from part5_personas.naming import RuleBasedNamer
from webapp_core.personas import (
    NARRATION_AI,
    NARRATION_DEMO,
    NARRATION_RULE,
    PersonaRunResult,
    PersonaRunSpec,
    run_personas,
)

# At least one categorical column so the k-prototypes path is used.
ATTRS = ["age_band", "digital_app_user", "total_out", "inflow_share_payroll"]
K = 3
SEED = 42


def _clustering_view(result: PersonaRunResult) -> dict:
    """Everything about the clustering, excluding persona name/description text."""
    sets = [
        {
            "group_key": ps.group_key,
            "k_used": ps.k_used,
            "too_small": ps.too_small,
            "clusters": [(p.profile.cluster_label, p.profile.size) for p in ps.personas],
        }
        for ps in result.persona_sets
    ]
    # Membership as a partition: persona names differ between namers, so compare
    # the sets of client ids per (group, persona) rather than the names.
    partition = {
        (str(group), frozenset(map(str, ids["client_id"])))
        for (group, _name), ids in result.labels.groupby(["group", "persona_label"])
    }
    sizes = sorted(
        len(ids) for _key, ids in result.labels.groupby(["group", "persona_label"])
    )
    return {"sets": sets, "partition": partition, "sizes": sizes}


@pytest.fixture(scope="module")
def spec() -> PersonaRunSpec:
    return PersonaRunSpec(level="all", clustering_attributes=ATTRS, k=K)


@pytest.fixture(scope="module")
def rule_result(spec: PersonaRunSpec) -> PersonaRunResult:
    return run_personas(spec, RuleBasedNamer(), Config(), narration=NARRATION_RULE)


def test_seed_is_42() -> None:
    assert Config().random_seed == SEED


def test_demo_bedrock_namer_matches_rule_clustering(
    spec: PersonaRunSpec, rule_result: PersonaRunResult
) -> None:
    namer = BedrockNamer(env={})  # empty env: Demo Mode, no network
    demo_result = run_personas(spec, namer, Config())

    assert _clustering_view(demo_result) == _clustering_view(rule_result)
    assert demo_result.labels["client_id"].tolist() == rule_result.labels["client_id"].tolist()
    # Every persona text came from the Demo mock, none from Bedrock.
    assert namer.sources
    assert set(namer.sources.values()) == {"Demo"}
    assert demo_result.narration_source == NARRATION_DEMO


def test_narration_ai_in_demo_mode_matches_rule_clustering(
    spec: PersonaRunSpec,
    rule_result: PersonaRunResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Clear credentials and block .env loading so converse() falls back to Demo.
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)

    ai_result = run_personas(spec, None, Config(), narration=NARRATION_AI)

    assert _clustering_view(ai_result) == _clustering_view(rule_result)
    assert ai_result.narration_source == NARRATION_DEMO
