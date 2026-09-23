import asyncio
import io
import json

import httpx
import pytest

from model_router.cli import main, make_console


def invoke(args):
    output = io.StringIO()
    code = main(args, console=make_console(file=output, width=110, color_system=None))
    return code, output.getvalue()


def test_demo_is_offline_and_exercises_real_policy(monkeypatch):
    from model_router.adapters import OpenRouterClient

    dispatched = []
    original_complete = OpenRouterClient.complete

    async def record_complete(self, model, request):
        dispatched.append((model, request.messages[0]["content"]))
        return await original_complete(self, model, request)

    def prohibit_network(*args, **kwargs):
        raise AssertionError("Offline demo attempted a network connection")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", prohibit_network)
    monkeypatch.setattr(OpenRouterClient, "complete", record_complete)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    code, output = invoke(["demo", "--json"])
    assert code == 0
    data = json.loads(output)
    assert data["synthetic"] is True
    assert data["network_requests"] == 0
    assert len(data["rows"]) == len(dispatched) == 100
    assert len({prompt for _, prompt in dispatched}) == 100
    assert [row["id"] for row in data["rows"]] == list(range(1, 101))
    assert data["summary"] == {
        "total_requests": 100,
        "routes": {"economy": 25, "strong": 75},
        "categories": {"rewrites": 25, "coding": 25, "tools": 25, "outages": 25},
    }
    assert sum(model == "demo/economy" for model, _ in dispatched) == 25
    assert sum(row["reason"] == "router_http_503" for row in data["rows"]) == 25
    assert sum(row["reason"] == "capability_or_risk_constraint" for row in data["rows"]) == 25
    assert not any(row["reason"] == "router_circuit_open" for row in data["rows"])


def test_demo_summary_and_full_output():
    code, summary = invoke(["demo"])
    assert code == 0
    assert "100 requests completed" in summary
    assert "25 economy" in summary and "75 strong" in summary
    assert "tern demo --all" in summary
    assert "TRUE_TAG" in summary and "OUTPUT_TAG" in summary
    code, full = invoke(["demo", "--all"])
    assert code == 0
    assert "Rewrite this politely: send the report." in full
    assert "Summarize the delivery plan" in full
    assert "100 requests completed" in full


def test_init_never_overwrites_existing_configuration(tmp_path):
    path = tmp_path / ".env"
    code, _ = invoke(["--env-file", str(path), "init"])
    assert code == 0
    assert "OPENROUTER_API_KEY=" in path.read_text()
    path.write_text("OPENROUTER_API_KEY=secret-sentinel\n")
    code, output = invoke(["--env-file", str(path), "init"])
    assert code == 0
    assert "secret-sentinel" in path.read_text()
    assert "secret-sentinel" not in output


def test_doctor_hides_credentials_and_honors_environment(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("OPENROUTER_API_KEY=file-sentinel\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "environment-sentinel")
    code, output = invoke(["--env-file", str(path), "doctor", "--auth", "google"])
    assert code == 0
    assert "sentinel" not in output
    assert "Local checks only" in output
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "environment-sentinel"


def test_doctor_missing_key_is_actionable(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    code, output = invoke(["--env-file", str(tmp_path / ".env"), "doctor", "--auth", "google"])
    assert code == 1
    assert "add OPENROUTER_API_KEY" in output


@pytest.mark.parametrize(
    "arguments",
    [
        ["chat", "hello", "--max-tokens", "0"],
        ["chat", "hello", "--experimental-threshold", "nan"],
        ["chat", "hello", "--experimental-threshold", "0.5"],
        ["chat", "hello", "--stream", "--json"],
        ["demo", "--all", "--json"],
    ],
)
def test_cli_rejects_invalid_settings(arguments):
    with pytest.raises(SystemExit) as exc:
        invoke(arguments)
    assert exc.value.code == 2


def test_connection_error_does_not_leak_upstream_content(monkeypatch):
    import model_router.cli as cli

    async def failure(args, console):
        raise httpx.ConnectError("secret-sentinel")

    monkeypatch.setattr(cli, "chat", failure)
    code, output = invoke(["chat", "hello"])
    assert code == 1
    assert "secret-sentinel" not in output
    assert "Connection failed" in output


def test_long_prompt_requires_explicit_bound(monkeypatch):
    from model_router.cli import chat, parser

    monkeypatch.setenv("OPENROUTER_API_KEY", "not-used")
    args = parser().parse_args(["chat", "x" * 4097])
    with pytest.raises(ValueError, match="--input-tokens"):
        asyncio.run(chat(args, make_console(file=io.StringIO())))


def test_json_is_machine_readable_even_in_narrow_terminal():
    from model_router.cli import emit_json

    output = io.StringIO()
    console = make_console(file=output, width=20, color_system=None)
    payload = {"content": "a long answer " * 100, "markup": "[red]literal[/]"}
    emit_json(console, payload)
    assert json.loads(output.getvalue()) == payload


def test_saved_results_preserve_missing_labels_and_show_mismatches(tmp_path, monkeypatch):
    def prohibit_network(*args, **kwargs):
        raise AssertionError("Saved results attempted a network connection")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", prohibit_network)
    path = tmp_path / "results.json"
    payload = {
        "rows": [
            {
                "id": 1,
                "category": "coding",
                "true_tag": "strong",
                "routing": {"tier": "economy"},
                "status": "completed",
            },
            {"id": 2, "category": "rewrites", "routing": {"tier": "strong"}, "status": "completed"},
        ]
    }
    original = json.dumps(payload)
    path.write_text(original)
    code, output = invoke(["results", str(path)])
    assert code == 0
    assert "TRUE_TAG" in output and "OUTPUT_TAG" in output
    lines = output.splitlines()
    assert any("coding" in line and "strong" in line and "economy" in line for line in lines)
    assert any("rewrites" in line and "unknown" in line and "strong" in line for line in lines)
    assert path.read_text() == original
