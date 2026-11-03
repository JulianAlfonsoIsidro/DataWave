"""Shared dataclasses and literals for the assistant package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Mode = Literal["bedrock", "mock"]
FieldStatus = Literal["found", "needs_input"]


@dataclass(frozen=True)
class ModelConfig:
    """Bedrock settings read from .env (Requirement 3.2)."""

    aws_access_key_id: str | None
    aws_secret_access_key: str | None
    aws_region: str | None
    bedrock_model_id: str | None

    @property
    def is_usable(self) -> bool:
        """True only when all four Bedrock settings are present (Req 3.1, 4.1)."""
        return all((
            self.aws_access_key_id,
            self.aws_secret_access_key,
            self.aws_region,
            self.bedrock_model_id,
        ))


@dataclass(frozen=True)
class ToolResult:
    """Segment-level result of one tool call, tagged with its source (Req 2.6)."""

    tool_name: str          # "get_card" | "compare_segments" | "what_if" | "past_promo_accuracy"
    ok: bool                # False for not-available / needs-a-run
    data: dict[str, Any]    # segment-level only; never a client_id
    note: str = ""          # e.g. "no card for that segment", "run a promo first"


@dataclass(frozen=True)
class AssistantReply:
    """What the engine returns to the UI for one chat turn."""

    text: str
    mode: Mode
    tool_called: str | None


@dataclass(frozen=True)
class FieldDraft:
    """One pre-filled form field and whether it was found (Requirement 7.7)."""

    value: Any             # validated value, or a safe default when needs_input
    status: FieldStatus    # "found" | "needs_input"


@dataclass(frozen=True)
class FormDraft:
    """The seven Promo_Form_Fields extracted from a Campaign_File, each a
    FieldDraft marked found/needs_input, plus the mode that produced it."""

    product_type: FieldDraft
    mechanic: FieldDraft
    threshold_php: FieldDraft
    reward: FieldDraft
    eligible_segments: FieldDraft  # value is list[str]
    min_adb: FieldDraft
    channels: FieldDraft           # value is list[str] of Allowed_Channel_Label
    mode: Mode
