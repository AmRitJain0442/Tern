"""Four bounded synthetic GPU -> OpenRouter requests; requires real credentials.

Run: uv run --env-file .env --extra adapter python scripts/smoke_adapter.py
Only synthetic fixture content and provider results are written, never credentials.
"""

import argparse
import asyncio
import json
import os
from contextlib import aclosing
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from model_router.adapters import (
    ChatRequest,
    LayaGPUClient,
    OpenRouterAdapter,
    OpenRouterClient,
    RoutingContext,
)
from model_router.connection import connection_settings
from model_router.policy import RouteRequest


async def main(args):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("Set OPENROUTER_API_KEY in the environment or ignored .env file")
    assignments = {
        os.environ.get("OPENROUTER_ECONOMY_MODEL", "google/gemini-2.5-flash-lite"): "economy",
        os.environ.get("OPENROUTER_STRONG_MODEL", "google/gemini-2.5-pro"): "strong",
    }
    if len(assignments) != 2:
        raise SystemExit("Economy and strong model IDs must differ")
    endpoint, _, options = connection_settings()
    options["timeout"] = args.router_timeout
    result = {
        "kind": "synthetic_adapter_smoke_not_quality_evaluation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "experimental_threshold": 0.7,
        "rows": [],
    }
    async with (
        LayaGPUClient(endpoint, **options) as laya,
        OpenRouterClient(api_key, timeout=90) as provider,
    ):
        started = perf_counter()
        result["health"] = await laya.warmup()
        result["warmup_ms"] = (perf_counter() - started) * 1000
        print("GPU service ready", flush=True)
        models = await provider.models(assignments)
        result["models"] = [m.model_dump(mode="json") for m in models]
        shadow = OpenRouterAdapter(models, laya, provider)
        experiment = OpenRouterAdapter(
            models, laya, provider, experimental_thresholds={"chat": 0.7, "coding": 0.7}
        )
        rewrite = ChatRequest(
            messages=[
                {"role": "user", "content": "Rewrite this politely: Send me the report today."}
            ],
            max_tokens=1024,
        )
        coding = ChatRequest(
            messages=[
                {
                    "role": "user",
                    "content": "In Python, write a thread-safe bounded LRU cache. Explain how you prevent races between lookup, eviction and updates. Keep the answer concise.",
                }
            ],
            max_tokens=1024,
        )
        tool = ChatRequest(
            messages=[
                {"role": "user", "content": "Get the weather in Paris using the provided tool."}
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get city weather",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": "get_weather"}},
            max_tokens=1024,
        )
        for name, adapter, request, workload, streaming in [
            ("shadow_completion", shadow, rewrite, "chat", False),
            ("experimental_stream", experiment, rewrite, "chat", True),
            ("experimental_coding", experiment, coding, "coding", False),
            ("tool_bypass", experiment, tool, "business", False),
        ]:
            # Generous fixture-only bound; applications must provide their own token bound,
            # including chat wrappers, tool schemas, history and any multimodal tokens.
            context = RoutingContext(input_tokens=4096, language="en", workload=workload)
            row = {"case": name, "request": request.model_dump(exclude_none=True)}
            started = perf_counter()
            if streaming:
                chunks = []
                async with aclosing(adapter.stream(request, context)) as stream:
                    async for chunk in stream:
                        if not chunks:
                            row["first_chunk_ms"] = (perf_counter() - started) * 1000
                        chunks.append(chunk.chunk)
                        row["routing"] = chunk.routing.model_dump()
                        row["attempted_models"] = list(chunk.attempted_models)
                row["chunks"] = chunks
                row["nonempty_output"] = any(
                    choice.get("delta", {}).get("content")
                    for chunk in chunks
                    for choice in chunk.get("choices", [])
                )
                row["usage"] = next((c["usage"] for c in reversed(chunks) if c.get("usage")), {})
            else:
                completion = await adapter.complete(request, context)
                row.update(completion.model_dump(mode="json"))
                row["usage"] = completion.response.get("usage", {})
                row["nonempty_output"] = any(
                    c.get("message", {}).get("content") or c.get("message", {}).get("tool_calls")
                    for c in completion.response["choices"]
                )
                if name == "tool_bypass":
                    row["tool_call_received"] = any(
                        c.get("message", {}).get("tool_calls")
                        for c in completion.response["choices"]
                    )
            row["elapsed_ms"] = (perf_counter() - started) * 1000
            result["rows"].append(row)
            # Save each completed request so later failures do not discard paid evidence.
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(
                json.dumps(
                    {
                        "case": name,
                        "routing": row["routing"],
                        "nonempty_output": row["nonempty_output"],
                        "usage": row["usage"],
                    }
                ),
                flush=True,
            )
        # Decision-only check after the live workload: verify default shadow semantics
        # without purchasing another completion, even if the first route timed out.
        result["final_shadow_probe"] = (
            await shadow.route(
                rewrite, RoutingContext(input_tokens=4096, language="en", workload="chat")
            )
        ).model_dump()
        result["raw_gpu_probe"] = (
            await laya.decide(RouteRequest(prompt=rewrite.messages[0]["content"], language="en"))
        ).model_dump()
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if result["final_shadow_probe"]["source"] != "laya":
            raise SystemExit("Final classifier probe did not succeed")
    if not all(row["nonempty_output"] for row in result["rows"]):
        raise SystemExit("One or more providers returned no visible output; inspect the artifact")
    if not result["rows"][-1].get("tool_call_received"):
        raise SystemExit("Tool fixture did not return a tool call")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/openrouter-adapter-smoke.json")
    )
    parser.add_argument("--router-timeout", type=float, default=0.75)
    asyncio.run(main(parser.parse_args()))
