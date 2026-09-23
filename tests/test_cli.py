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
    def prohibit_network(*args, **kwargs):
        raise AssertionError("Offline demo attempted a network connection")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", prohibit_network)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    code, output = invoke(["demo", "--json"])
    assert code == 0
    data = json.loads(output)
    assert data["synthetic"] is True
    assert data["network_requests"] == 0
    assert [row["tier"] for row in data["rows"]] == ["economy", "strong", "strong", "strong"]
    assert data["rows"][-1]["reason"] == "router_http_503"


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
