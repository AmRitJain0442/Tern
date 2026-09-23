import asyncio
import json
from collections import Counter

import httpx
import pytest

from model_router import live_demo
from model_router.backend import MODEL_REVISION


def test_live_fixtures_are_100_unique_prompts_without_offline_answers():
    cases = live_demo.live_cases()
    assert len(cases) == 100
    assert len({c["request"].messages[0]["content"] for c in cases}) == 100
    assert Counter(c["category"] for c in cases) == {
        "rewrites": 25,
        "coding": 25,
        "tools": 25,
        "summaries": 25,
    }
    assert all("answer" not in c and "probability" not in c for c in cases)
    assert all(
        "classifier is unavailable" not in c["request"].messages[0]["content"] for c in cases
    )


def test_live_runner_checkpoints_real_adapter_outcomes_with_mock_transports(tmp_path, monkeypatch):
    original_cases = live_demo.live_cases
    monkeypatch.setattr(live_demo, "live_cases", lambda max_tokens: original_cases(max_tokens)[:4])
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-secret")
    monkeypatch.setenv("OPENROUTER_ECONOMY_MODEL", "economy")
    monkeypatch.setenv("OPENROUTER_STRONG_MODEL", "strong")
    monkeypatch.setenv("LAYA_ENDPOINT", "https://laya.example")

    async def token():
        return "test-only-identity"

    def route(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"ready": True, "model_revision": MODEL_REVISION})
        return httpx.Response(
            200,
            json={
                "selected_tier": "strong",
                "proposed_tier": "strong",
                "mode": "shadow",
                "reason": "shadow_proposal",
                "model_revision": MODEL_REVISION,
                "probability_economy": 0.8,
                "inference_ms": 10.0,
            },
        )

    def provider(request):
        if request.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {}})
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": model,
                            "context_length": 32768,
                            "supported_parameters": ["max_tokens", "tools", "tool_choice"],
                            "architecture": {"input_modalities": ["text"]},
                        }
                        for model in ("economy", "strong")
                    ]
                },
            )
        body = json.loads(request.content)
        if "LRU" in body["messages"][0]["content"]:
            return httpx.Response(401, json={"error": "must-not-escape"})
        message = {"role": "assistant", "content": "Test response"}
        if body.get("tools"):
            message["tool_calls"] = [
                {
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city":"Paris"}',
                    }
                }
            ]
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "choices": [
                    {
                        "message": message,
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"cost": 0.01},
            },
        )

    class TestLaya(live_demo.RecordedLaya):
        def __init__(self, endpoint, **kwargs):
            super().__init__(endpoint, token_provider=token, transport=httpx.MockTransport(route))

    class TestProvider(live_demo.RecordedProvider):
        def __init__(self, key, **kwargs):
            super().__init__(key, transport=httpx.MockTransport(provider))

    monkeypatch.setattr(live_demo, "RecordedLaya", TestLaya)
    monkeypatch.setattr(live_demo, "RecordedProvider", TestProvider)
    path = tmp_path / "run.json"
    updates = []

    def progress(message):
        if "/100" in message:
            updates.append(json.loads(path.read_text())["summary"]["requests_finished"])

    report, output = asyncio.run(
        live_demo.run_live_demo(
            output=path,
            experimental_threshold=0.7,
            progress=progress,
        )
    )
    assert output == path
    assert report["status"] == "finished"
    assert report["summary"]["completed"] == 3
    assert report["summary"]["failed"] == 1
    assert report["summary"]["reported_openrouter_cost_usd"] == 0.03
    assert report["summary"]["attempts_without_cost"] == 1
    assert report["summary"]["tool_calls_valid"] == 1
    assert report["summary"]["successful_classifier_calls"] == 3
    assert [row["true_tag"] for row in report["rows"]] == ["economy", "strong", "strong", "economy"]
    assert [row["output_tag"] for row in report["rows"]] == [
        "economy",
        "economy",
        "strong",
        "economy",
    ]
    assert all(row["true_tag_source"] == "fixture_expectation" for row in report["rows"])
    assert sorted(updates) == [1, 2, 3, 4]
    assert "test-only-secret" not in path.read_text()
    assert "must-not-escape" not in path.read_text()


def test_existing_paid_evidence_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-secret")
    path = tmp_path / "run.json"
    path.write_text("previous evidence")
    with pytest.raises(FileExistsError):
        asyncio.run(live_demo.run_live_demo(output=path))
    assert path.read_text() == "previous evidence"


def test_output_tag_uses_final_attempt_even_if_provider_fallback_fails():
    row = {
        "initial_routing": {"tier": "economy"},
        "provider_attempts": [{"model": "cheap"}, {"model": "expensive"}],
    }
    models = [{"id": "cheap", "tier": "economy"}, {"id": "expensive", "tier": "strong"}]
    assert live_demo.output_tag(row, models) == "strong"
    assert live_demo.output_tag(row) is None
    assert live_demo.output_tag({}) is None
