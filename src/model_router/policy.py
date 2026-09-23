"""Pure routing policy. A Laya label probability is not LLM success probability."""

import math
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["economy", "strong"]
POLICY_VERSION = "binary-shadow-v1"


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=16000)
    # Supplied by an authenticated gateway, not inferred from the prompt itself.
    language: str = Field(default="unknown", max_length=32)
    requires_tools: bool = False
    requires_vision: bool = False
    requires_private_processing: bool = False
    high_stakes: bool = False
    has_conversation_history: bool = False
    eligible_tiers: list[Tier] = Field(
        default_factory=lambda: ["economy", "strong"], min_length=1, max_length=2
    )


class RouteResponse(BaseModel):
    selected_tier: Tier | None
    proposed_tier: Tier | None
    reason: str
    mode: Literal["shadow", "experimental"]
    policy_version: str = POLICY_VERSION
    probability_economy: float | None = None
    inference_ms: float = 0
    router_ms: float = 0
    input_tokens: int | None = None
    model_revision: str | None = None


@dataclass(frozen=True)
class Settings:
    mode: Literal["shadow", "experimental"] = "shadow"
    threshold: float = 0.9  # Experiment parameter; deliberately not called calibrated.
    max_inference_ms: float = 2000

    def __post_init__(self):
        if self.mode not in ("shadow", "experimental"):
            raise ValueError("Invalid mode")
        if not math.isfinite(self.threshold) or not 0.5 < self.threshold <= 1:
            raise ValueError("Threshold must be in (0.5, 1]")
        if not math.isfinite(self.max_inference_ms) or self.max_inference_ms <= 0:
            raise ValueError("Inference budget must be positive")


def conservative(request: RouteRequest, settings: Settings, reason: str) -> RouteResponse:
    # Never silently violate eligibility if the conservative tier is unavailable.
    tier = "strong" if "strong" in request.eligible_tiers else None
    return RouteResponse(selected_tier=tier, proposed_tier=tier, reason=reason, mode=settings.mode)


def preflight(request: RouteRequest, settings: Settings) -> RouteResponse | None:
    if not request.prompt.strip():
        return conservative(request, settings, "empty_text")
    # Private processing needs a separately configured deployment, not a capability guess.
    if request.requires_private_processing:
        result = conservative(request, settings, "private_processing_not_configured")
        result.selected_tier = result.proposed_tier = None
        return result
    if request.language.lower().split("-")[0] != "en":
        return conservative(request, settings, "unsupported_or_unknown_language")
    if request.requires_tools or request.requires_vision or request.high_stakes:
        return conservative(request, settings, "capability_or_risk_constraint")
    if request.has_conversation_history:
        return conservative(request, settings, "full_conversation_required")
    if "economy" not in request.eligible_tiers:
        return conservative(request, settings, "economy_ineligible")
    return None


def decide(
    request: RouteRequest,
    settings: Settings,
    probability: float,
    inference_ms: float,
    input_tokens: int,
) -> RouteResponse:
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        return conservative(request, settings, "invalid_probability")
    if not math.isfinite(inference_ms) or inference_ms > settings.max_inference_ms:
        return conservative(request, settings, "inference_budget_exceeded")
    proposed: Tier = "economy" if probability >= settings.threshold else "strong"
    selected = "strong" if settings.mode == "shadow" else proposed
    reason = "shadow_proposal" if settings.mode == "shadow" else "experimental_threshold"
    if selected not in request.eligible_tiers:
        selected, reason = None, "no_eligible_conservative_tier"
    return RouteResponse(
        selected_tier=selected,
        proposed_tier=proposed,
        reason=reason,
        mode=settings.mode,
        probability_economy=probability,
        inference_ms=inference_ms,
        input_tokens=input_tokens,
    )
