"""Model configuration loading from the environment (.env via python-dotenv)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from assistant.models import ModelConfig


def load_model_config() -> ModelConfig:
    """Read AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, and
    BEDROCK_MODEL_ID from .env via python-dotenv, falling back to the process
    environment. Never hardcodes credentials (Requirement 3.2)."""
    load_dotenv()
    return ModelConfig(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_region=os.getenv("AWS_REGION"),
        bedrock_model_id=os.getenv("BEDROCK_MODEL_ID"),
    )
