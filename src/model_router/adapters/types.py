"""Validated caller metadata and provider-independent routing results."""

from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from model_router.policy import RouteRequest, RouteResponse, Tier

Workload = Literal["chat", "coding", "business"]


class StreamOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include_usage: bool = False


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    messages: list[dict[str, Any]] = Field(min_length=1)
    max_tokens: int = Field(
        default=512, gt=0, validation_alias=AliasChoices("max_tokens", "max_completion_tokens")
    )
    temperature: float | None = Field(default=None, ge=0, le=2)
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    seed: int | None = None
    stop: str | list[str] | None = None
    stream_options: StreamOptions | None = None


class DecisionClient(Protocol):
    async def decide(self, request: RouteRequest) -> RouteResponse: ...


class CompletionProvider(Protocol):
    async def complete(self, model: str, request: ChatRequest) -> dict: ...

    def stream(self, model: str, request: ChatRequest) -> AsyncIterator[dict]: ...


class RoutingContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    # A conservative bound INCLUDING history, tools, and multimodal inputs, for every candidate.
    # The adapter does not pretend that a character count is a provider tokenizer.
    input_tokens: int = Field(ge=1)
    language: str = "unknown"
    workload: Workload = "chat"
    high_stakes: bool = False
    requires_private_processing: bool = False
    required_region: str | None = None
    eligible_model_ids: frozenset[str] | None = None


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1)
    tier: Tier
    context_length: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    input_modalities: frozenset[str] = frozenset({"text"})
    supported_parameters: frozenset[str] = frozenset({"max_tokens"})
    enabled: bool = True


class ModelDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    model: str
    tier: Tier
    reason: str
    source: Literal["local", "laya", "fallback"]
    workload: Workload
    proposed_tier: Tier | None = None
    probability_economy: float | None = None
    service_mode: str | None = None
    policy_version: str | None = None
    experimental_threshold: float | None = None
    router_ms: float = 0


class RoutedCompletion(BaseModel):
    routing: ModelDecision
    response: dict[str, Any]
    attempted_models: tuple[str, ...]


class RoutedChunk(BaseModel):
    routing: ModelDecision
    chunk: dict[str, Any]
    attempted_models: tuple[str, ...]


class NoEligibleModel(ValueError):
    """No permitted conservative route exists; nothing should be sent externally."""


class DecisionUnavailable(RuntimeError):
    """Sanitized classifier failure, safe to use as a fallback reason."""


class ProviderError(RuntimeError):
    def __init__(self, status: int | None, *, retryable: bool = False, kind="provider_error"):
        super().__init__(f"Provider {kind} (status={status})")
        self.status = status
        self.retryable = retryable
        self.kind = kind
