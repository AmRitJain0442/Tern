"""Public MLX GPU → OpenRouter adapter API."""

from .auth import GcloudIDTokenProvider, GoogleIDTokenProvider
from .compatible import OpenAICompatibleClient
from .laya import LayaGPUClient
from .openrouter import OpenRouterClient
from .router import OpenRouterAdapter
from .types import (
    ChatRequest,
    ModelDecision,
    ModelSpec,
    NoEligibleModel,
    ProviderError,
    RoutedChunk,
    RoutedCompletion,
    RoutingContext,
)

__all__ = [
    "ChatRequest",
    "GcloudIDTokenProvider",
    "GoogleIDTokenProvider",
    "LayaGPUClient",
    "ModelDecision",
    "ModelSpec",
    "NoEligibleModel",
    "OpenRouterAdapter",
    "OpenAICompatibleClient",
    "OpenRouterClient",
    "ProviderError",
    "RoutedChunk",
    "RoutedCompletion",
    "RoutingContext",
]
