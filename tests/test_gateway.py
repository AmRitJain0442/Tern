import asyncio
import io
import json
from contextlib import aclosing

import httpx
import pytest
from fastapi.testclient import TestClient

from model_router.adapters.compatible import OpenAICompatibleClient
from model_router.adapters.types import ChatRequest
from model_router.app import create_app
from model_router.cli import main, make_console
from model_router.gateway import ClosingStream
from model_router.providers import ProviderPool, ProviderSettings, read_settings


class FakeBackend:
    revision = "fixture"

    def predict(self, prompt):
        return 0.95, 1.0, 20


def settings():
    return ProviderSettings.model_validate(
        {
            "providers": {
                "fast": {"base_url": "https://fast.example/custom/v1", "api_key_env": "FAST_KEY"},
                "strong": {
                    "type": "openrouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key_env": "STRONG_KEY",
                },
            },
            "models": [
                {
                    "id": tier,
                    "provider": provider,
                    "upstream_model": f"upstream/{tier}",
                    "tier": tier,
                    "context_length": 32768,
                    "max_output_tokens": 4096,
                    "supported_parameters": [
                        "max_tokens",
                        "tools",
                        "tool_choice",
                        "response_format",
                        "structured_outputs",
                        "temperature",
                    ],
                }
                for tier, provider in [("economy", "fast"), ("strong", "strong")]
            ],
            "experimental_thresholds": {"chat": 0.7},
        }
    )


def payload(**updates):
    return {
        "model": "tern/auto",
        "messages": [{"role": "user", "content": "Rewrite hello"}],
        "routing": {"input_tokens": 256, "language": "en"},
        **updates,
    }


def answer(model="test"):
    return {
        "id": "completion-test",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }


def app_for(monkeypatch, handler, config=None):
    monkeypatch.setenv("FAST_KEY", "fast-secret")
    monkeypatch.setenv("STRONG_KEY", "strong-secret")
    monkeypatch.delenv("TERN_API_KEY", raising=False)
    config = config or settings()
    return create_app(
        FakeBackend,
        provider_pool_factory=lambda: ProviderPool(
            config,
            transport_factory=lambda provider: httpx.MockTransport(
                lambda req: handler(provider, req)
            ),
        ),
    )


def test_api_cross_provider_fallback_isolates_credentials_and_preserves_payload(monkeypatch):
    calls = []

    def handler(provider, request):
        body = json.loads(request.content)
        calls.append((provider, body))
        assert "routing" not in body
        assert request.headers["authorization"] == f"Bearer {provider}-secret"
        if provider == "fast":
            assert request.url.path == "/custom/v1/chat/completions"
            assert "provider" not in body
            assert body["model"] == "upstream/economy"
            return httpx.Response(503, json={"error": "secret-upstream-body"})
        assert body["provider"]["require_parameters"] is True
        assert body["model"] == "upstream/strong"
        return httpx.Response(200, json=answer(body["model"]))

    with TestClient(app_for(monkeypatch, handler)) as client:
        response = client.post("/v1/chat/completions", json=payload())
        assert response.status_code == 200
        assert response.headers["x-tern-tier"] == "strong"
        result = response.json()
        assert result["choices"] == answer()["choices"]
        assert result["usage"] == answer()["usage"]
        assert result["tern"]["attempted_models"] == ["economy", "strong"]
        assert result["tern"]["routing"]["reason"] == "provider_fallback"
        assert "secret" not in response.text
    assert [p for p, _ in calls] == ["fast", "strong"]


def test_tools_go_to_capable_strong_provider_without_classifier(monkeypatch):
    received = []

    def handler(provider, request):
        assert provider == "strong"
        received.append(json.loads(request.content))
        return httpx.Response(200, json=answer())

    body = payload(
        tools=[
            {"type": "function", "function": {"name": "weather", "parameters": {"type": "object"}}}
        ],
        tool_choice="auto",
        response_format={"type": "json_object"},
    )
    app = app_for(monkeypatch, handler)
    with TestClient(app) as client:

        def forbidden(prompt):
            raise AssertionError("Tools must bypass classification")

        app.state.backend.predict = forbidden
        result = client.post("/v1/chat/completions", json=body)
        assert result.status_code == 200
        assert result.headers["x-tern-reason"] == "capability_or_risk_constraint"
    for name in ("messages", "tools", "tool_choice", "response_format"):
        assert received[0][name] == body[name]


class EventStream(httpx.AsyncByteStream):
    def __init__(self, *, fail=False):
        self.closed, self.fail = False, fail

    async def __aiter__(self):
        yield b'data: {"id":"s","choices":[{"delta":{"content":"Hello"}}]}\n\n'
        if self.fail:
            raise httpx.ReadError("secret-upstream-body")
        yield b'data: {"choices":[],"usage":{"total_tokens":12}}\n\ndata: [DONE]\n\n'

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("fail", [False, True])
def test_streaming_usage_cleanup_and_no_replay_after_output(monkeypatch, fail):
    stream = EventStream(fail=fail)
    calls = []

    def handler(provider, request):
        calls.append(provider)
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        assert "provider" not in body
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    with TestClient(app_for(monkeypatch, handler)) as client:
        result = client.post(
            "/v1/chat/completions",
            json=payload(stream=True, stream_options={"include_usage": True}),
        )
    assert result.status_code == 200
    assert result.headers["x-tern-tier"] == "economy"
    assert "Hello" in result.text
    assert "secret" not in result.text
    assert ("[DONE]" in result.text) is not fail
    assert ("upstream_error" in result.text) is fail
    assert calls == ["fast"]
    assert stream.closed


def test_auth_private_requests_and_invalid_payloads_never_reach_providers(monkeypatch):
    calls = []
    app = app_for(monkeypatch, lambda p, r: calls.append(p))
    monkeypatch.setenv("TERN_API_KEY", "gateway-secret")
    with TestClient(app) as client:
        assert client.get("/v1/models").status_code == 401
        assert client.post("/v1/chat/completions", json=payload()).status_code == 401
        headers = {"Authorization": "Bearer gateway-secret"}
        assert client.get("/v1/models", headers=headers).json()["data"][0]["id"] == "tern/auto"
        for updates in [
            {"routing": {"input_tokens": 256, "requires_private_processing": True}},
            {"routing": {"input_tokens": 256, "required_region": "EU"}},
            {"routing": None, "messages": [{"role": "user", "content": "x" * 5000}]},
            {"stream_options": {"include_usage": True}},
        ]:
            assert (
                client.post(
                    "/v1/chat/completions", json=payload(**updates), headers=headers
                ).status_code
                == 400
            )
        for updates in [
            {"model": "arbitrary/model"},
            {"provider_url": "https://evil.example"},
            {"api_key": "secret"},
        ]:
            assert (
                client.post(
                    "/v1/chat/completions", json=payload(**updates), headers=headers
                ).status_code
                == 422
            )
    assert calls == []


def test_provider_error_is_sanitized_before_stream_headers(monkeypatch):
    def handler(provider, request):
        return httpx.Response(401, json={"error": "secret-upstream-body"})

    with TestClient(app_for(monkeypatch, handler)) as client:
        response = client.post("/v1/chat/completions", json=payload(stream=True))
    assert response.status_code == 502
    assert "secret" not in response.text
    assert response.json()["error"]["code"] == "upstream_error"


def test_compatible_client_token_parameter_and_api_key_header():
    def handler(request):
        assert request.url.path == "/openai/v1/chat/completions"
        assert request.headers["api-key"] == "key-sentinel"
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["max_completion_tokens"] == 32
        assert "max_tokens" not in body and "provider" not in body
        return httpx.Response(200, json=answer())

    async def run():
        async with OpenAICompatibleClient(
            "https://example.azure.com/openai/v1",
            "key-sentinel",
            auth_header="api-key",
            token_parameter="max_completion_tokens",
            transport=httpx.MockTransport(handler),
        ) as provider:
            await provider.complete(
                "deployment",
                ChatRequest(messages=[{"role": "user", "content": "hi"}], max_tokens=32),
            )

    asyncio.run(run())


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example/v1",
        "https://key@provider.example/v1",
        "https://provider.example/v1?api_key=secret",
        "https://provider.example:99999/v1",
    ],
)
def test_provider_url_validation(url):
    with pytest.raises(ValueError):
        OpenAICompatibleClient(url, "key")


def test_bad_config_errors_do_not_echo_credentials(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"providers":{"secret-sentinel":"invalid"}}')
    with pytest.raises(ValueError) as exc:
        read_settings(path)
    assert "secret-sentinel" not in str(exc.value)


def test_cli_uses_custom_provider_config_without_openrouter_key(monkeypatch):
    import model_router.cli as cli
    from model_router.policy import RouteResponse

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("FAST_KEY", "fast-secret")
    monkeypatch.setenv("STRONG_KEY", "strong-secret")
    monkeypatch.setattr(cli, "read_settings", settings)
    received = []

    def handler(request):
        received.append(json.loads(request.content)["model"])
        return httpx.Response(200, json=answer())

    monkeypatch.setattr(
        cli,
        "ProviderPool",
        lambda s: ProviderPool(s, transport_factory=lambda name: httpx.MockTransport(handler)),
    )

    class Classifier:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def warmup(self):
            pass

        async def decide(self, request):
            return RouteResponse(
                selected_tier="strong",
                proposed_tier="economy",
                probability_economy=0.95,
                mode="shadow",
                reason="shadow_proposal",
            )

    monkeypatch.setattr(cli, "make_laya", lambda args: Classifier())
    output = io.StringIO()
    assert main(["chat", "hello", "--json"], console=make_console(file=output)) == 0
    assert received == ["upstream/economy"]


def test_disconnect_closes_prefetched_stream():
    async def run():
        stream = EventStream()
        async with OpenAICompatibleClient(
            "http://localhost:1234/v1",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, headers={"content-type": "text/event-stream"}, stream=stream
                )
            ),
        ) as provider:
            upstream = provider.stream(
                "local", ChatRequest(messages=[{"role": "user", "content": "hello"}])
            )
            await anext(upstream)

            async def content():
                async with aclosing(upstream):
                    yield "data: first\n\n"

            response = ClosingStream(content(), upstream, media_type="text/event-stream")

            async def send(message):
                raise OSError("client disconnected before first body chunk")

            async def receive():
                return {"type": "http.disconnect"}

            with pytest.raises(Exception):
                await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
            assert stream.closed

    asyncio.run(run())
