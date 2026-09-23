import asyncio
import json
from contextlib import aclosing, asynccontextmanager

import httpx
import pytest

from model_router.adapters import (
    ChatRequest,
    LayaGPUClient,
    ModelSpec,
    NoEligibleModel,
    OpenRouterAdapter,
    OpenRouterClient,
    ProviderError,
    RoutingContext,
)
from model_router.adapters.auth import GoogleIDTokenProvider
from model_router.adapters.types import DecisionUnavailable
from model_router.backend import MODEL_REVISION
from model_router.policy import RouteRequest

REQUEST = ChatRequest(messages=[{"role": "user", "content": "Rewrite: hello"}], max_tokens=32)
CONTEXT = RoutingContext(input_tokens=100, language="en")
RESPONSE = {
    "choices": [{"message": {"role": "assistant", "content": "Hello!"}}],
    "usage": {"total_tokens": 12, "cost": 0.00001},
    "model": "actual-provider-model",
}


def decision(**updates):
    return {
        "selected_tier": "strong",
        "proposed_tier": "economy",
        "mode": "shadow",
        "reason": "shadow_proposal",
        "probability_economy": 0.8,
        "model_revision": MODEL_REVISION,
        **updates,
    }


@asynccontextmanager
async def setup(provider_handler=None, route_payload=None, thresholds=None, models=None):
    calls = []

    async def token():
        return "synthetic-identity"

    def route_handler(request):
        assert request.headers["Authorization"] == "Bearer synthetic-identity"
        calls.append(("laya", json.loads(request.content)))
        return httpx.Response(200, json=route_payload or decision())

    def provider(request):
        assert request.headers["Authorization"] == "Bearer synthetic-api-key"
        calls.append(("provider", json.loads(request.content)))
        return provider_handler(request) if provider_handler else httpx.Response(200, json=RESPONSE)

    specs = models or [
        ModelSpec(
            id=tier,
            tier=tier,
            context_length=4096,
            max_output_tokens=2048,
            input_modalities={"text", "image"},
            supported_parameters={
                "max_tokens",
                "tools",
                "tool_choice",
                "response_format",
                "structured_outputs",
            },
        )
        for tier in ("economy", "strong")
    ]
    async with LayaGPUClient(
        "https://laya.example", token_provider=token, transport=httpx.MockTransport(route_handler)
    ) as laya:
        async with OpenRouterClient(
            "synthetic-api-key", transport=httpx.MockTransport(provider)
        ) as api:
            yield OpenRouterAdapter(specs, laya, api, experimental_thresholds=thresholds), calls


def test_shadow_and_explicit_workload_threshold():
    async def run():
        async with setup() as (adapter, calls):
            result = await adapter.complete(REQUEST, CONTEXT)
            assert result.routing.tier == "strong"
            assert result.response == RESPONSE
            assert result.attempted_models == ("strong",)
            assert calls[1][1]["provider"]["require_parameters"] is True
        async with setup(thresholds={"chat": 0.7}) as (adapter, _):
            result = await adapter.complete(REQUEST, CONTEXT)
            assert result.routing.tier == "economy"
            assert result.routing.experimental_threshold == 0.7
            coding = await adapter.route(REQUEST, CONTEXT.model_copy(update={"workload": "coding"}))
            assert coding.tier == "strong"

    asyncio.run(run())


@pytest.mark.parametrize("reason", ["router_busy", "router_context_overflow", "router_error"])
def test_threshold_never_overrides_constraints(reason):
    async def run():
        async with setup(route_payload=decision(reason=reason), thresholds={"chat": 0.7}) as (a, _):
            assert (await a.route(REQUEST, CONTEXT)).tier == "strong"

    asyncio.run(run())


@pytest.mark.parametrize(
    "context",
    [
        {"requires_private_processing": True},
        {"required_region": "EU"},
        {"eligible_model_ids": frozenset({"economy"})},
        {"input_tokens": 4090},
    ],
)
def test_ineligible_requests_never_leave_process(context):
    async def run():
        async with setup() as (a, calls):
            with pytest.raises(NoEligibleModel):
                await a.complete(REQUEST, CONTEXT.model_copy(update=context))
            assert calls == []

    asyncio.run(run())


@pytest.mark.parametrize(
    "messages,extra",
    [
        ([{"role": "system", "content": "Be brief"}, *REQUEST.messages], {}),
        (
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}}
                    ],
                }
            ],
            {},
        ),
        (
            REQUEST.messages,
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {"name": "lookup", "parameters": {"type": "object"}},
                    }
                ],
                "tool_choice": "auto",
            },
        ),
        (
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "a",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "a", "content": "found"},
            ],
            {},
        ),
    ],
)
def test_history_tools_images_preserved_and_bypass_classifier(messages, extra):
    async def run():
        request = ChatRequest(messages=messages, **extra)
        async with setup(thresholds={"chat": 0.7}) as (a, calls):
            result = await a.complete(request, CONTEXT)
            assert result.routing.tier == "strong"
            assert len(calls) == 1 and calls[0][0] == "provider"
            body = calls[0][1]
            for key, value in request.model_dump(exclude_none=True).items():
                assert body[key] == value

    asyncio.run(run())


@pytest.mark.parametrize(
    "status,retries", [(503, True), (429, True), (401, False), (402, False), (400, False)]
)
def test_bounded_provider_fallback(status, retries):
    def provider(request):
        return httpx.Response(status, json={"error": "secret body must not escape"})

    async def run():
        async with setup(provider, thresholds={"chat": 0.7}) as (a, calls):
            with pytest.raises(ProviderError) as exc:
                await a.complete(REQUEST, CONTEXT)
            assert "secret" not in str(exc.value)
            ids = [body["model"] for kind, body in calls if kind == "provider"]
            assert ids == (["economy", "strong"] if retries else ["economy"])

    asyncio.run(run())


def test_provider_fallback_success_and_timeout_not_replayed():
    def provider(request):
        if json.loads(request.content)["model"] == "economy":
            return httpx.Response(503)
        return httpx.Response(200, json=RESPONSE)

    def timeout(request):
        raise httpx.ReadTimeout("secret diagnostic")

    async def run():
        async with setup(provider, thresholds={"chat": 0.7}) as (a, _):
            result = await a.complete(REQUEST, CONTEXT)
            assert result.attempted_models == ("economy", "strong")
            assert result.routing.reason == "provider_fallback"
        async with setup(timeout, thresholds={"chat": 0.7}) as (a, calls):
            with pytest.raises(ProviderError, match="timeout"):
                await a.complete(REQUEST, CONTEXT)
            assert len(calls) == 2

    asyncio.run(run())


@pytest.mark.parametrize(
    "patch",
    [
        {"model_revision": "other"},
        {"probability_economy": 1.1},
        {"selected_tier": "economy"},
        {"inference_ms": -1},
        {"router_ms": "10"},
    ],
)
def test_invalid_classifier_falls_back(patch):
    async def run():
        async with setup(route_payload=decision(**patch), thresholds={"chat": 0.7}) as (a, _):
            result = await a.complete(REQUEST, CONTEXT)
            assert result.routing.tier == "strong"
            assert result.routing.source == "fallback"

    asyncio.run(run())


def test_auth_deadline_and_circuit_breaker():
    async def run():
        invocations = 0

        async def slow_token():
            nonlocal invocations
            invocations += 1
            await asyncio.sleep(1)
            return "token"

        async with LayaGPUClient(
            "https://laya.example", token_provider=slow_token, timeout=0.01, failure_threshold=2
        ) as laya:
            for _ in range(2):
                with pytest.raises(DecisionUnavailable, match="router_timeout"):
                    await laya.decide(RouteRequest(prompt="hello"))
            with pytest.raises(DecisionUnavailable, match="router_circuit_open"):
                await laya.decide(RouteRequest(prompt="hello"))
            assert invocations == 2

    asyncio.run(run())


def test_shared_refresh_survives_caller_cancellation():
    async def run():
        import threading

        provider = GoogleIDTokenProvider("https://example.com")
        started, release = threading.Event(), threading.Event()
        calls = []

        def refresh():
            calls.append(1)
            started.set()
            release.wait(2)
            return "cached-token"

        provider._refresh = refresh
        first = asyncio.create_task(provider())
        await asyncio.to_thread(started.wait, 1)
        second = asyncio.create_task(provider())
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert await second == "cached-token"
        assert calls == [1]

    asyncio.run(run())


def test_google_token_audience_refresh_and_cache(monkeypatch):
    from google.oauth2 import id_token

    class Credentials:
        valid = False
        token = None

        def refresh(self, request):
            self.valid, self.token = True, "cached-test-token"

    credentials = Credentials()
    audiences = []

    def fetch(audience, request):
        audiences.append(audience)
        return credentials

    monkeypatch.setattr(id_token, "fetch_id_token_credentials", fetch)

    async def run():
        provider = GoogleIDTokenProvider("https://private.example")
        assert await provider() == "cached-test-token"
        assert await provider() == "cached-test-token"
        assert audiences == ["https://private.example"]

    asyncio.run(run())


def test_catalog_resolution_and_parameter_eligibility():
    def catalog(_):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": tier,
                        "context_length": 8192,
                        "top_provider": {"context_length": 4096, "max_completion_tokens": 512},
                        "architecture": {"input_modalities": ["text"]},
                        "supported_parameters": ["max_tokens"],
                    }
                    for tier in ("economy", "strong")
                ]
            },
        )

    async def run():
        async with OpenRouterClient("test", transport=httpx.MockTransport(catalog)) as api:
            specs = await api.models({"economy": "economy", "strong": "strong"})
            assert specs[0].context_length == 4096
            assert specs[0].max_output_tokens == 512
            with pytest.raises(ValueError, match="absent"):
                await api.models({"missing": "strong"})
        async with setup(models=specs) as (adapter, calls):
            with pytest.raises(NoEligibleModel):
                await adapter.complete(REQUEST.model_copy(update={"temperature": 0.5}), CONTEXT)
            with pytest.raises(NoEligibleModel):
                await adapter.complete(REQUEST.model_copy(update={"max_tokens": 513}), CONTEXT)
            assert not calls

    asyncio.run(run())


@pytest.mark.parametrize("status", [200, 401])
def test_key_check_validates_auth_without_returning_account_data(status):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(status, json={"data": {"label": "private-key-label"}})

    async def run():
        async with OpenRouterClient("test", transport=httpx.MockTransport(handler)) as api:
            if status == 200:
                assert await api.check_credentials() is None
            else:
                with pytest.raises(ProviderError) as exc:
                    await api.check_credentials()
                assert "private-key-label" not in str(exc.value)
        assert seen == ["/api/v1/key"]

    asyncio.run(run())


def test_request_snapshot_survives_caller_mutation():
    async def run():
        request = REQUEST.model_copy(deep=True)
        async with setup() as (adapter, calls):
            original = adapter.laya.token_provider

            async def token():
                request.messages[0]["content"] = "changed after eligibility"
                return await original()

            adapter.laya.token_provider = token
            await adapter.complete(request, CONTEXT)
            assert calls[1][1]["messages"] == REQUEST.messages

    asyncio.run(run())


def test_redirect_does_not_forward_identity_token():
    async def run():
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://different.example/route"})

        async def token():
            return "test-token"

        async with LayaGPUClient(
            "https://laya.example", token_provider=token, transport=httpx.MockTransport(handler)
        ) as laya:
            with pytest.raises(DecisionUnavailable, match="router_http_302"):
                await laya.decide(RouteRequest(prompt="hello"))
        assert len(seen) == 1

    asyncio.run(run())


def test_sse_multiline_data():
    stream = ByteStream(
        'data: {"choices":\n' + 'data: [{"delta":{"content":"hi"}}]}\n\n' + "data: [DONE]\n\n"
    )

    async def run():
        async with setup(
            lambda _: httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=stream
            )
        ) as (a, _):
            chunks = [c async for c in a.stream(REQUEST, CONTEXT)]
            assert chunks[0].chunk["choices"][0]["delta"]["content"] == "hi"

    asyncio.run(run())


class ByteStream(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data, self.closed = data.encode(), False

    async def __aiter__(self):
        for pos in range(0, len(self.data), 7):
            yield self.data[pos : pos + 7]

    async def aclose(self):
        self.closed = True


def event(payload):
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def test_stream_preserves_tool_deltas_usage_and_closes():
    delta = {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "é"}}]}}]}
    usage = {"choices": [], "usage": {"total_tokens": 17}}
    stream = ByteStream(": keepalive\n\n" + event(delta) + event(usage) + "data: [DONE]\n\n")

    async def run():
        async with setup(
            lambda _: httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=stream
            )
        ) as (a, _):
            chunks = [c async for c in a.stream(REQUEST, CONTEXT)]
            assert [c.chunk for c in chunks] == [delta, usage]
        assert stream.closed

    asyncio.run(run())


@pytest.mark.parametrize(
    "suffix,kind",
    [
        (event({"error": {"code": 503, "message": "private"}}), "response_error"),
        ("", "incomplete_stream"),
    ],
)
def test_partial_stream_never_retried(suffix, kind):
    stream = ByteStream(event({"choices": [{"delta": {"content": "first"}}]}) + suffix)

    async def run():
        async with setup(
            lambda _: httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=stream
            ),
            thresholds={"chat": 0.7},
        ) as (a, calls):
            seen = []
            with pytest.raises(ProviderError, match=kind):
                async for chunk in a.stream(REQUEST, CONTEXT):
                    seen.append(chunk)
            assert len(seen) == 1
            assert len(calls) == 2
            assert stream.closed

    asyncio.run(run())


def test_stream_early_close_and_pre_output_fallback():
    stream = ByteStream(event({"choices": [{"delta": {"content": "one"}}]}) + "data: [DONE]\n\n")

    def provider(request):
        if json.loads(request.content)["model"] == "economy":
            return httpx.Response(503)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    async def run():
        async with setup(provider, thresholds={"chat": 0.7}) as (a, calls):
            async with aclosing(a.stream(REQUEST, CONTEXT)) as chunks:
                chunk = await anext(chunks)
                assert chunk.attempted_models == ("economy", "strong")
            assert stream.closed
            assert len(calls) == 3

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload", [{"choices": None}, {"choices": [None]}, {"error": {"code": 402}}, {"choices": []}]
)
def test_malformed_and_200_error_responses(payload):
    async def run():
        async with setup(lambda _: httpx.Response(200, json=payload)) as (a, _):
            with pytest.raises(ProviderError):
                await a.complete(REQUEST, CONTEXT)

    asyncio.run(run())
