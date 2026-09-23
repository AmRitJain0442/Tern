"""Map GPU decisions to eligible OpenRouter models and dispatch bounded completions."""

import math
from contextlib import aclosing
from time import perf_counter

from model_router.adapters.laya import LayaGPUClient
from model_router.adapters.openrouter import OpenRouterClient
from model_router.adapters.types import (
    ChatRequest,
    DecisionUnavailable,
    ModelDecision,
    ModelSpec,
    NoEligibleModel,
    ProviderError,
    RoutedChunk,
    RoutedCompletion,
    RoutingContext,
)
from model_router.policy import RouteRequest


def inspect_request(request: ChatRequest):
    modalities = {"text"}
    tools = bool(request.tools) or request.tool_choice is not None
    for message in request.messages:
        if message.get("role") not in {"system", "developer", "user", "assistant", "tool"}:
            raise ValueError("Unsupported message role")
        tools |= message["role"] == "tool" or bool(message.get("tool_calls"))
        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    raise ValueError("Malformed content part")
                kind = part.get("type")
                if kind == "image_url":
                    modalities.add("image")
                elif kind == "input_audio":
                    modalities.add("audio")
                elif kind != "text" or not isinstance(part.get("text"), str):
                    raise ValueError("Unsupported content part")
        elif content is not None and not isinstance(content, str):
            raise ValueError("Unsupported message content")
        elif content is None and not message.get("tool_calls"):
            raise ValueError("Message content is required except for tool calls")
    parameters = set(request.model_dump(exclude_none=True)) - {"messages"}
    if tools:
        parameters.add("tools")
    if request.response_format and request.response_format.get("type") == "json_schema":
        parameters.add("structured_outputs")
    return modalities, parameters, tools


class OpenRouterAdapter:
    """Async adapter; caller owns and closes the shared Laya and OpenRouter clients."""

    def __init__(
        self,
        models: list[ModelSpec],
        laya: LayaGPUClient,
        provider: OpenRouterClient,
        *,
        experimental_thresholds: dict[str, float] | None = None,
    ):
        if not models or len({m.id for m in models}) != len(models):
            raise ValueError("Supply a nonempty catalog with unique model IDs")
        self.models = tuple(models)
        self.laya, self.provider = laya, provider
        self.thresholds = dict(experimental_thresholds or {})
        for family, value in self.thresholds.items():
            if (
                family not in {"chat", "coding", "business"}
                or not math.isfinite(value)
                or not 0.5 < value <= 1
            ):
                raise ValueError("Invalid experimental workload threshold")

    def _eligible(self, request, context):
        if context.requires_private_processing or context.required_region:
            raise NoEligibleModel("Private or region-bound OpenRouter routing is not configured")
        modalities, parameters, tools = inspect_request(request)
        models = [
            m
            for m in self.models
            if m.enabled
            and (context.eligible_model_ids is None or m.id in context.eligible_model_ids)
            and modalities <= m.input_modalities
            and parameters <= m.supported_parameters
            and request.max_tokens <= m.max_output_tokens
            and context.input_tokens + request.max_tokens <= m.context_length
        ]
        # A guaranteed eligible strong fallback is required even for experimental routing.
        strong = next((m for m in models if m.tier == "strong"), None)
        if strong is None:
            raise NoEligibleModel("No eligible strong fallback in configured model catalog")
        economy = next((m for m in models if m.tier == "economy"), None)
        return strong, economy, modalities, tools

    async def route(self, request: ChatRequest, context: RoutingContext) -> ModelDecision:
        start = perf_counter()
        strong, economy, modalities, tools = self._eligible(request, context)

        def decision(model=strong, reason="", source="local", **kwargs):
            return ModelDecision(
                model=model.id,
                tier=model.tier,
                reason=reason,
                source=source,
                workload=context.workload,
                router_ms=(perf_counter() - start) * 1000,
                **kwargs,
            )

        # Bypass before the network; never truncate history or classify a detached latest turn.
        if economy is None:
            return decision(reason="economy_ineligible")
        if tools or modalities != {"text"} or context.high_stakes:
            return decision(reason="capability_or_risk_constraint")
        if context.language.lower().replace("_", "-").split("-")[0] != "en":
            return decision(reason="unsupported_or_unknown_language")
        if len(request.messages) != 1 or request.messages[0]["role"] != "user":
            return decision(reason="full_conversation_required")
        prompt = request.messages[0].get("content")
        if not isinstance(prompt, str):
            return decision(reason="structured_content")
        if not prompt.strip() or len(prompt) > 16000:
            return decision(reason="empty_or_long_prompt")
        try:
            result = await self.laya.decide(RouteRequest(prompt=prompt, language="en"))
        except DecisionUnavailable as exc:
            return decision(reason=str(exc), source="fallback")
        if result.selected_tier is None:
            raise NoEligibleModel("Decision service returned no acceptable route")
        tier = result.selected_tier
        threshold = self.thresholds.get(context.workload)
        reason = result.reason
        # Explicit local experimentation may use probabilities from shadow inference, but
        # must never turn a service constraint/error/overflow result into an economy route.
        if threshold is not None and result.reason in {"shadow_proposal", "experimental_threshold"}:
            if result.probability_economy is None:
                return decision(reason="router_missing_probability", source="fallback")
            tier = "economy" if result.probability_economy >= threshold else "strong"
            reason = "adapter_experimental_threshold"
        model = economy if tier == "economy" else strong
        return decision(
            model,
            reason,
            "laya",
            proposed_tier=result.proposed_tier,
            probability_economy=result.probability_economy,
            service_mode=result.mode,
            policy_version=result.policy_version,
            experimental_threshold=threshold
            if reason == "adapter_experimental_threshold"
            else None,
        )

    def _fallback(self, decision, request, context):
        strong, _, _, _ = self._eligible(request, context)
        return decision.model_copy(
            update={
                "model": strong.id,
                "tier": "strong",
                "reason": "provider_fallback",
                "source": "fallback",
            }
        )

    async def complete(self, request: ChatRequest, context: RoutingContext) -> RoutedCompletion:
        # Snapshot nested payloads so caller mutation cannot change eligibility after the await.
        request = request.model_copy(deep=True)
        decision = await self.route(request, context)
        attempts = [decision.model]
        try:
            response = await self.provider.complete(decision.model, request)
        except ProviderError as exc:
            if decision.tier != "economy" or not exc.retryable:
                raise
            decision = self._fallback(decision, request, context)
            attempts.append(decision.model)
            response = await self.provider.complete(decision.model, request)
        return RoutedCompletion(
            routing=decision, response=response, attempted_models=tuple(attempts)
        )

    async def stream(self, request: ChatRequest, context: RoutingContext):
        request = request.model_copy(deep=True)
        decision = await self.route(request, context)
        attempts, emitted = [decision.model], False
        for attempt in range(2):
            try:
                async with aclosing(self.provider.stream(decision.model, request)) as chunks:
                    async for chunk in chunks:
                        emitted = True
                        yield RoutedChunk(
                            routing=decision, chunk=chunk, attempted_models=tuple(attempts)
                        )
                return
            except ProviderError as exc:
                if emitted or attempt or decision.tier != "economy" or not exc.retryable:
                    raise
                decision = self._fallback(decision, request, context)
                attempts.append(decision.model)
