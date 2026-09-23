import asyncio
import json

import httpx
import pytest

from model_router.adapters.laya import LOCAL_ENDPOINT, LayaGPUClient
from model_router.backend import MODEL_REVISION
from model_router.connection import connection_settings
from model_router.policy import RouteRequest


def test_local_client_never_authenticates_or_follows_redirects(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:9999")

    def auth(*args):
        raise AssertionError("Local classification tried Google auth")

    monkeypatch.setattr("model_router.adapters.laya.GoogleIDTokenProvider", auth)
    calls = []

    def handler(request):
        assert "authorization" not in request.headers
        calls.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(200, json={"ready": True, "model_revision": MODEL_REVISION})
        return httpx.Response(
            200,
            json={
                "selected_tier": "strong",
                "proposed_tier": "economy",
                "mode": "shadow",
                "reason": "shadow_proposal",
                "probability_economy": 0.8,
                "model_revision": MODEL_REVISION,
            },
        )

    async def run():
        async with LayaGPUClient(
            LOCAL_ENDPOINT, local=True, transport=httpx.MockTransport(handler)
        ) as client:
            await client.warmup()
            result = await client.decide(RouteRequest(prompt="Rewrite hello", language="en"))
            assert result.probability_economy == 0.8

    asyncio.run(run())
    assert calls == ["/health", "/v1/route"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.com",
        "http://127.0.0.1.example.com",
        "http://0.0.0.0:8080",
        "http://127.0.0.1@evil.example",
        "http://user:password@localhost:8080",
        "http://localhost:8080/path",
        "http://localhost:8080?token=secret",
        "http://localhost:99999",
        "http://localhost:0",
        "http://localhost:8080#fragment",
    ],
)
def test_unauthenticated_local_mode_rejects_non_loopback_and_ambiguous_urls(endpoint):
    with pytest.raises(ValueError):
        LayaGPUClient(endpoint, local=True)


def test_local_auth_does_not_leak_a_supplied_token():
    with pytest.raises(ValueError, match="token provider"):
        LayaGPUClient(LOCAL_ENDPOINT, local=True, token_provider=lambda: "secret")


def test_cli_defaults_to_local_but_preserves_remote_configuration(monkeypatch):
    for name in ("LAYA_ENDPOINT", "LAYA_AUTH", "LAYA_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    endpoint, auth, settings = connection_settings()
    assert endpoint == LOCAL_ENDPOINT and auth == "local"
    assert settings == {"local": True, "timeout": 30.0, "token_provider": None}
    monkeypatch.setenv("LAYA_ENDPOINT", "https://private.run.app")
    endpoint, auth, settings = connection_settings()
    assert auth == "gcloud" and settings["local"] is False
    assert settings["timeout"] == 0.75
    assert connection_settings("google")[1] == "google"
    with pytest.raises(ValueError):
        connection_settings("local")


def test_route_cli_needs_neither_google_nor_openrouter(tmp_path, monkeypatch):
    import io

    from model_router import cli
    from model_router.policy import RouteResponse

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    class LocalClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def warmup(self):
            pass

        async def decide(self, request):
            assert request.prompt == "hello"
            return RouteResponse(
                selected_tier="strong",
                proposed_tier="economy",
                reason="shadow_proposal",
                mode="shadow",
                probability_economy=0.8,
            )

    def no_provider(*args):
        raise AssertionError("Classification contacted OpenRouter")

    monkeypatch.setattr(cli, "make_laya", lambda args: LocalClient())
    monkeypatch.setattr(cli, "OpenRouterClient", no_provider)
    output = io.StringIO()
    code = cli.main(
        ["--env-file", str(tmp_path / "missing"), "route", "hello"],
        console=cli.make_console(file=output),
    )
    assert code == 0
    assert json.loads(output.getvalue())["probability_economy"] == 0.8


def test_model_download_resumes_and_cached_restart_needs_no_network(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from model_router.local_service import prepare_model

    base = tmp_path / "weights"
    calls = []

    def download(model, *, revision, local_dir, allow_patterns):
        assert revision == MODEL_REVISION
        assert "*.py" not in allow_patterns
        calls.append(model)
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "model.safetensors").write_bytes(b"synthetic-test-weight")
        if len(calls) == 1:
            raise OSError("interrupted download")
        for name in (
            "rl_agent_config.json",
            "encoder/config.json",
            "tokenizer/tokenizer.json",
            "mlx_config.json",
        ):
            path = local_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}")

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    monkeypatch.setenv("MODEL_PATH", str(base))
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    with pytest.raises(OSError):
        prepare_model()
    assert not (base / MODEL_REVISION / ".tern-download-complete").exists()
    prepare_model()
    import os

    assert os.environ["MODEL_PATH"] == str(base / MODEL_REVISION)
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    # Restart resets the environment to the base directory specified in the image.
    monkeypatch.setenv("MODEL_PATH", str(base))
    prepare_model()
    assert len(calls) == 2
