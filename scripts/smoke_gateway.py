"""Two explicit live API requests; may incur generation charges. No model/provider keys here."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import httpx
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(override=False)
    key = os.environ.get("TERN_API_KEY", "").strip()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    report = {
        "kind": "live_tern_api_integration_not_quality_evaluation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "starting",
        "output_token_cap_per_attempt": 2048,
        "rows": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    def save():
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    try:
        with httpx.Client(
            base_url=args.endpoint,
            headers=headers,
            timeout=180,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            health = client.get("/health")
            health.raise_for_status()
            report["health"] = health.json()
            models = client.get("/v1/models")
            models.raise_for_status()
            assert models.json()["data"][0]["id"] == "tern/auto"
            if key:
                unauthenticated = client.get("/v1/models", headers={"Authorization": ""})
                assert unauthenticated.status_code == 401
                report["unauthenticated_models_status"] = 401

            request = {
                "model": "tern/auto",
                "messages": [{"role": "user", "content": "Rewrite politely: send the report."}],
                "max_tokens": 2048,
                "routing": {"input_tokens": 256, "language": "en"},
            }
            started = perf_counter()
            response = client.post("/v1/chat/completions", json=request)
            response.raise_for_status()
            body = response.json()
            report["rows"].append(
                {
                    "case": "text_completion",
                    "request": request,
                    "response": body,
                    "elapsed_ms": (perf_counter() - started) * 1000,
                }
            )
            save()
            assert body["choices"][0]["message"]["content"]
            assert body["tern"]["routing"]["source"] == "laya"
            assert body["tern"]["routing"]["probability_economy"] is not None

            request = {
                "model": "tern/auto",
                "messages": [{"role": "user", "content": "Look up the weather in Denver."}],
                "max_tokens": 2048,
                "routing": {"input_tokens": 512, "language": "en"},
                "stream": True,
                "stream_options": {"include_usage": True},
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "Get weather for a city",
                            "parameters": {
                                "type": "object",
                                "properties": {"city": {"type": "string"}},
                                "required": ["city"],
                            },
                        },
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
            }
            started = perf_counter()
            chunks, done = [], False
            with client.stream("POST", "/v1/chat/completions", json=request) as response:
                response.raise_for_status()
                routing = {k: v for k, v in response.headers.items() if k.startswith("x-tern-")}
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        done = True
                        break
                    chunk = json.loads(data)
                    assert "error" not in chunk
                    chunks.append(chunk)
            report["rows"].append(
                {
                    "case": "streamed_tool_call_not_executed",
                    "request": request,
                    "routing_headers": routing,
                    "chunks": chunks,
                    "done_received": done,
                    "elapsed_ms": (perf_counter() - started) * 1000,
                }
            )
            save()
            assert done and routing["x-tern-tier"] == "strong"
            assert any(c.get("usage") for c in chunks)
            calls = [
                call
                for chunk in chunks
                for choice in chunk.get("choices", [])
                for call in choice.get("delta", {}).get("tool_calls", [])
            ]
            assert any(call.get("function", {}).get("name") == "get_weather" for call in calls)
            arguments = "".join(call.get("function", {}).get("arguments", "") for call in calls)
            assert json.loads(arguments)["city"] == "Denver"
        report["status"] = "passed"
    except BaseException as exc:
        report["status"] = "failed"
        report["error_kind"] = type(exc).__name__
        raise RuntimeError("API smoke failed; inspect the saved checkpoint") from None
    finally:
        save()
    print(f"Two live API checks passed; saved {args.output}")


if __name__ == "__main__":
    main()
