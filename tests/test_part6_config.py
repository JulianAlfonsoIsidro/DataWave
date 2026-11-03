"""Unit tests for :func:`assistant.config.load_model_config` (Task 2.2).

These cover the credential-driven behavior of the Bedrock config loader
(Requirements 3.2, 3.4, 4.1):

- when all four Bedrock env vars are set, the returned ``ModelConfig`` is
  ``is_usable``,
- when any single one is missing (the other three present), it is not usable,
- when none are set, it is not usable, and
- a source-level check that no credential value is hardcoded in
  ``src/assistant/config.py`` (the secret is only ever read via ``os.getenv``).

``assistant`` is a package under ``src``; the tests run with ``PYTHONPATH=src``.
To keep the on-disk ``.env`` from leaking into these tests, each test
monkeypatches ``assistant.config.load_dotenv`` to a no-op so only the patched
process environment is read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assistant.config import load_model_config
from assistant.models import ModelConfig

# The four Bedrock settings the loader reads via os.getenv.
ENV_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "BEDROCK_MODEL_ID",
)

CONFIG_SOURCE_PATH = (
    Path(__file__).resolve().parent.parent / "src" / "assistant" / "config.py"
)


def _no_op_dotenv(monkeypatch):
    """Neutralize ``.env`` loading so only the patched env is read."""
    monkeypatch.setattr("assistant.config.load_dotenv", lambda *a, **k: False)


def _set_all(monkeypatch):
    """Set all four Bedrock env vars to non-empty placeholder values."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-access-key-id")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret-access-key")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "test.model-id")


def test_all_four_vars_set_is_usable(monkeypatch):
    """All four env vars set yields a ModelConfig with is_usable == True."""
    _no_op_dotenv(monkeypatch)
    _set_all(monkeypatch)

    config = load_model_config()

    assert isinstance(config, ModelConfig)
    assert config.is_usable is True
    assert config.aws_access_key_id == "test-access-key-id"
    assert config.aws_secret_access_key == "test-secret-access-key"
    assert config.aws_region == "us-east-1"
    assert config.bedrock_model_id == "test.model-id"


@pytest.mark.parametrize("missing", ENV_VARS)
def test_any_single_missing_var_is_not_usable(monkeypatch, missing):
    """With any one of the four vars missing, is_usable == False."""
    _no_op_dotenv(monkeypatch)
    _set_all(monkeypatch)
    monkeypatch.delenv(missing, raising=False)

    config = load_model_config()

    assert config.is_usable is False


def test_no_vars_set_is_not_usable(monkeypatch):
    """With none of the four vars set, is_usable == False."""
    _no_op_dotenv(monkeypatch)
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    config = load_model_config()

    assert config.is_usable is False


def test_no_credential_value_is_hardcoded_in_source():
    """No credential literal is hardcoded in config.py.

    The source must contain no ``AKIA`` access-key literal, and the secret key
    name must appear only as an ``os.getenv`` argument, never assigned a literal
    value such as ``AWS_SECRET_ACCESS_KEY = "..."``.
    """
    source = CONFIG_SOURCE_PATH.read_text(encoding="utf-8")

    # No AWS access-key literal anywhere in the source.
    assert "AKIA" not in source

    # The secret key name is referenced only as an os.getenv key, not assigned
    # a hardcoded literal.
    assert 'os.getenv("AWS_SECRET_ACCESS_KEY")' in source
    assert 'AWS_SECRET_ACCESS_KEY =' not in source
    assert 'AWS_SECRET_ACCESS_KEY=' not in source
