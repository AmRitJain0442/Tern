"""Server-controlled provider configuration and dispatch across independently keyed endpoints."""

import asyncio
import os
from contextlib import AsyncExitStack, aclosing
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from model_router.adapters.compatible import OpenAICompatibleClient
from model_router.adapters.openrouter import BASE_URL, OpenRouterClient
from model_router.adapters.types import ModelSpec


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    type: Literal["openrouter", "openai_compatible"] = "openai_compatible"
    base_url: str = Field(min_length=1)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    auth_header: Literal["Authorization", "api-key"] = "Authorization"
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    allow_http: bool = False
    timeout: float = Field(default=120, gt=0, le=600)

    @model_validator(mode="after")
    def check_openrouter(self):
        if self.type == "openrouter" and (
            self.base_url.rstrip("/") != BASE_URL
            or self.auth_header != "Authorization"
            or self.token_parameter != "max_tokens"
            or self.allow_http
        ):
            raise ValueError("OpenRouter transport requires the official endpoint and settings")
        return self


class TargetConfig(ModelSpec):
    provider: str = Field(min_length=1)
    upstream_model: str = Field(min_length=1)


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    providers: dict[str, ProviderConfig] = Field(min_length=1)
    models: list[TargetConfig] = Field(min_length=2)
    experimental_thresholds: dict[str, float] = Field(default_factory=dict)
    default_language: str = "unknown"

    @model_validator(mode="after")
    def check_targets(self):
        if len({m.id for m in self.models}) != len(self.models):
            raise ValueError("Model IDs must be unique aliases")
        if not any(m.tier == "strong" and m.enabled for m in self.models):
            raise ValueError("An enabled strong model is required")
        if any(m.provider not in self.providers for m in self.models):
            raise ValueError("Unknown provider in model configuration")
        if any(
            k not in {"chat", "coding", "business"} or not 0.5 < v <= 1
            for k, v in self.experimental_thresholds.items()
        ):
            raise ValueError("Invalid experimental workload threshold")
        return self


def read_settings(path=None):
    path = path or os.environ.get("TERN_CONFIG")
    if not path:
        return None  # Backward-compatible OpenRouter environment configuration.
    try:
        return ProviderSettings.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Validation errors can echo JSON, so never include bodies or credentials.
        raise ValueError("Invalid TERN_CONFIG; check the provider configuration guide") from None


class ProviderPool:
    """Resolve trusted aliases to upstream models. Clients are reused until close."""

    def __init__(self, settings=None, *, transport_factory=None):
        self.settings = settings
        self._transport_factory = transport_factory or (lambda name: None)
        self._stack = AsyncExitStack()
        self._lock = asyncio.Lock()
        self._targets = {}
        self._models = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._stack.aclose()

    async def models(self):
        async with self._lock:
            if self._models is not None:
                return self._models
            async with AsyncExitStack() as pending:
                targets, specs = {}, []
                if self.settings is None:
                    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
                    if not key:
                        raise ValueError("Set OPENROUTER_API_KEY or configure TERN_CONFIG")
                    client = await pending.enter_async_context(
                        OpenRouterClient(
                            key, timeout=120, transport=self._transport_factory("openrouter")
                        )
                    )
                    economy = os.environ.get(
                        "OPENROUTER_ECONOMY_MODEL", "google/gemini-2.5-flash-lite"
                    )
                    strong = os.environ.get("OPENROUTER_STRONG_MODEL", "google/gemini-2.5-pro")
                    if economy == strong:
                        raise ValueError("Economy and strong models must differ")
                    specs = await client.models({economy: "economy", strong: "strong"})
                    targets = {spec.id: (client, spec.id) for spec in specs}
                else:
                    clients = {}
                    for name, config in self.settings.providers.items():
                        key = (
                            os.environ.get(config.api_key_env, "").strip()
                            if config.api_key_env
                            else None
                        )
                        if config.api_key_env and not key:
                            raise ValueError("A configured provider API key is missing")
                        transport = self._transport_factory(name)
                        if config.type == "openrouter":
                            client = OpenRouterClient(
                                key, timeout=config.timeout, transport=transport
                            )
                        else:
                            client = OpenAICompatibleClient(
                                config.base_url,
                                key,
                                timeout=config.timeout,
                                transport=transport,
                                allow_http=config.allow_http,
                                token_parameter=config.token_parameter,
                                auth_header=config.auth_header,
                            )
                        clients[name] = await pending.enter_async_context(client)
                    for target in self.settings.models:
                        specs.append(
                            ModelSpec.model_validate(
                                target.model_dump(exclude={"provider", "upstream_model"})
                            )
                        )
                        targets[target.id] = (clients[target.provider], target.upstream_model)
                self._stack = pending.pop_all()
                self._targets, self._models = targets, specs
                return specs

    async def complete(self, model, request):
        client, upstream = self._targets[model]
        return await client.complete(upstream, request)

    async def stream(self, model, request):
        client, upstream = self._targets[model]
        async with aclosing(client.stream(upstream, request)) as chunks:
            async for chunk in chunks:
                yield chunk
