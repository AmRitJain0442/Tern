"""A real, checkpointed 100-request Laya/provider integration run."""

import asyncio
import json
import os
import statistics
from collections import Counter
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from model_router.adapters import (
    ChatRequest,
    LayaGPUClient,
    OpenRouterAdapter,
    OpenRouterClient,
    ProviderError,
    RoutingContext,
)
from model_router.connection import connection_settings
from model_router.demo import EXPECTED_TAGS, demo_cases
from model_router.providers import ProviderPool, read_settings

CURRENT_ROW = ContextVar("live_demo_row", default=None)


def live_cases(max_tokens=2048):
    """Reuse prompts, never offline scores/responses or simulated service failures."""
    cases = []
    for index, fixture in enumerate(demo_cases(), start=1):
        category, prompt = fixture["category"], fixture["prompt"]
        extra = {}
        if category == "outages":
            category = "summaries"
            document = prompt.removeprefix("Summarize the ").split(" while ")[0]
            prompt = (
                f"Summarize this {document} update in one sentence: "
                "The team completed its review on Tuesday. Two issues remain open. "
                "Maya owns both fixes and will deliver them by Friday."
            )
        elif category == "rewrites":
            prompt += " Return only one sentence."
        elif category == "coding":
            prompt += " Give a concise answer in at most 150 words."
        elif category == "tools":
            extra = {
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "Get the weather for a city",
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
        cases.append(
            {
                "id": index,
                "category": category,
                "true_tag": EXPECTED_TAGS[category],
                "true_tag_source": "fixture_expectation",
                "workload": fixture["workload"],
                "request": ChatRequest(
                    messages=[{"role": "user", "content": prompt}], max_tokens=max_tokens, **extra
                ),
            }
        )
    return cases


class RecordedLaya(LayaGPUClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gate = asyncio.Lock()

    async def decide(self, request):
        # The deployed instance admits one inference at a time. Generation still overlaps.
        async with self._gate:
            result = await super().decide(request)
            row = CURRENT_ROW.get()
            if row is not None:
                row["classifier"] = result.model_dump()
            return result


class RecordingProvider:
    def attempt_info(self, model):
        return {"model": model, "provider_type": "openrouter"}

    async def complete(self, model, request):
        row = CURRENT_ROW.get()
        attempt = self.attempt_info(model)
        if row is not None:
            row["provider_attempts"].append(attempt)
        try:
            result = await super().complete(model, request)
            attempt["usage"] = result.get("usage", {})
            attempt["status"] = "completed"
            return result
        except ProviderError as exc:
            attempt.update(status="failed", error_kind=exc.kind, http_status=exc.status)
            raise


class RecordedProvider(RecordingProvider, OpenRouterClient):
    pass


class RecordedPool(RecordingProvider, ProviderPool):
    async def models(self, assignments=None):
        return await super().models()

    def attempt_info(self, model):
        target = next(m for m in self.settings.models if m.id == model)
        return {
            "model": model,
            "upstream_model": target.upstream_model,
            "provider": target.provider,
            "provider_type": self.settings.providers[target.provider].type,
        }


class RecordedAdapter(OpenRouterAdapter):
    async def route(self, request, context):
        result = await super().route(request, context)
        row = CURRENT_ROW.get()
        if row is not None:
            row["initial_routing"] = result.model_dump()
        return result


def output_tag(row, models=()):
    """Final selected tier, including provider fallback; never infer a reference label."""
    if row.get("routing"):
        return row["routing"]["tier"]
    attempts = row.get("provider_attempts", [])
    if attempts:
        tiers = {model["id"]: model["tier"] for model in models}
        return tiers.get(attempts[-1]["model"])
    return row.get("initial_routing", {}).get("tier")


def summarize(rows):
    completed = [row for row in rows if row["status"] == "completed"]
    finished = [row for row in rows if row["status"] in {"completed", "failed"}]
    attempts = [attempt for row in rows for attempt in row["provider_attempts"]]
    costs = [attempt.get("usage", {}).get("cost") for attempt in attempts]
    known_costs = [cost for cost in costs if isinstance(cost, (int, float))]
    latencies = sorted(row["elapsed_ms"] for row in finished)
    classifiers = [row["classifier"] for row in rows if "classifier" in row]
    return {
        "requests_finished": len(finished),
        "completed": len(completed),
        "failed": sum(row["status"] == "failed" for row in rows),
        "nonempty_outputs": sum(row.get("nonempty_output", False) for row in completed),
        "truncated": sum(row.get("truncated", False) for row in completed),
        "routes": dict(Counter(row["routing"]["tier"] for row in completed)),
        "routing_reasons": dict(Counter(row["routing"]["reason"] for row in completed)),
        "successful_classifier_calls": len(classifiers),
        "median_inference_ms": statistics.median(c["inference_ms"] for c in classifiers)
        if classifiers
        else None,
        "tool_calls_valid": sum(row.get("tool_call_valid", False) for row in completed),
        "provider_attempts": len(attempts),
        "reported_provider_cost_usd": round(sum(known_costs), 9),
        "reported_openrouter_cost_usd": round(
            sum(
                a.get("usage", {}).get("cost", 0)
                for a in attempts
                if a.get("provider_type", "openrouter") == "openrouter"
                and isinstance(a.get("usage", {}).get("cost"), (int, float))
            ),
            9,
        ),
        "attempts_without_cost": len(attempts) - len(known_costs),
        "median_request_ms": statistics.median(latencies) if latencies else None,
        "p95_request_ms": latencies[max(0, (95 * len(latencies) + 99) // 100 - 1)]
        if latencies
        else None,
    }


def check_output(row, response):
    choices = response.get("choices", [])
    row["nonempty_output"] = any(
        bool(c.get("message", {}).get("content") or c.get("message", {}).get("tool_calls"))
        for c in choices
    )
    row["truncated"] = any(c.get("finish_reason") == "length" for c in choices)
    if row["category"] == "tools":
        expected_city = (
            row["request"]["messages"][0]["content"]
            .removeprefix("Look up the weather in ")
            .removesuffix(".")
        )
        row["tool_call_valid"] = False
        for choice in choices:
            for call in choice.get("message", {}).get("tool_calls") or []:
                function = call.get("function", {})
                try:
                    arguments = json.loads(function.get("arguments", ""))
                except (ValueError, TypeError):
                    continue
                if (
                    function.get("name") == "get_weather"
                    and isinstance(arguments, dict)
                    and arguments.get("city") == expected_city
                ):
                    row["tool_call_valid"] = True


async def run_live_demo(
    *,
    output=None,
    max_tokens=2048,
    concurrency=4,
    experimental_threshold=None,
    auth="auto",
    progress=print,
):
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    settings = read_settings()
    if not key and settings is None:
        raise ValueError("Set OPENROUTER_API_KEY or TERN_CONFIG before running a live demo")
    if not 1 <= concurrency <= 8 or max_tokens <= 0:
        raise ValueError("Concurrency must be 1..8 and max_tokens must be positive")
    assignments = {
        os.environ.get("OPENROUTER_ECONOMY_MODEL", "google/gemini-2.5-flash-lite"): "economy",
        os.environ.get("OPENROUTER_STRONG_MODEL", "google/gemini-2.5-pro"): "strong",
    }
    if len(assignments) != 2 and settings is None:
        raise ValueError("Economy and strong models must differ")
    cases = live_cases(max_tokens)
    endpoint, _, connection = connection_settings(auth)
    path = (
        Path(output)
        if output
        else Path(
            "artifacts/live-100-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            + ".json"
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "kind": "live_integration_run_with_synthetic_prompts_not_quality_evaluation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "starting",
        "endpoint": endpoint,
        "max_tokens_per_attempt": max_tokens,
        "generation_concurrency": concurrency,
        "classifier_concurrency": 1,
        "experimental_threshold": experimental_threshold,
        "tool_execution": "Tool calls are inspected; weather tools are not executed.",
        "rows": [
            {
                "id": c["id"],
                "category": c["category"],
                "true_tag": c.get("true_tag"),
                "true_tag_source": c.get("true_tag_source", "unlabeled"),
                "output_tag": None,
                "workload": c["workload"],
                "request": c["request"].model_dump(exclude_none=True),
                "status": "pending",
                "provider_attempts": [],
            }
            for c in cases
        ],
    }
    # Refuse to overwrite prior paid evidence or silently replay a partially completed run.
    with path.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    def checkpoint():
        report["summary"] = summarize(report["rows"])
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    progress(f"LIVE: 100 requests; output cap {max_tokens}/attempt; concurrency {concurrency}")
    progress(f"Saving progress to {path}")
    progress(
        "TRUE_TAG = fixture expectation, not measured ground truth; OUTPUT_TAG = selected tier."
    )
    try:
        async with (
            RecordedLaya(
                report["endpoint"],
                **connection,
            ) as laya,
            RecordedPool(settings) if settings else RecordedProvider(key, timeout=120) as provider,
        ):
            if settings is None:
                await provider.check_credentials()
            models = await provider.models(assignments)
            started = perf_counter()
            progress("Checking Laya readiness...")
            report["health"] = await laya.warmup()
            report["warmup_ms"] = (perf_counter() - started) * 1000
            report["models"] = [m.model_dump(mode="json") for m in models]
            thresholds = (
                {w: experimental_threshold for w in ("chat", "coding", "business")}
                if experimental_threshold is not None
                else settings.experimental_thresholds
                if settings
                else None
            )
            adapter = RecordedAdapter(models, laya, provider, experimental_thresholds=thresholds)
            gate = asyncio.Semaphore(concurrency)
            report["status"] = "running"
            checkpoint()
            started = perf_counter()
            progress(
                f"{'DONE':7} {'ID':>3}  {'CATEGORY':9}  {'TRUE_TAG':10} {'OUTPUT_TAG':10} "
                f"{'STATUS':9}  {'TIME':>6}  REPORTED COST"
            )

            async def execute(case, row):
                async with gate:
                    row["status"] = "running"
                    checkpoint()
                    token = CURRENT_ROW.set(row)
                    began = perf_counter()
                    try:
                        result = await adapter.complete(
                            case["request"],
                            RoutingContext(
                                input_tokens=4096, language="en", workload=case["workload"]
                            ),
                        )
                        row.update(result.model_dump(mode="json"))
                        check_output(row, result.response)
                        row["status"] = "completed"
                    except ProviderError as exc:
                        row.update(status="failed", error_kind=exc.kind, http_status=exc.status)
                    except Exception as exc:
                        # Exception bodies can contain credentials or HTTP headers.
                        row.update(status="failed", error_kind=type(exc).__name__)
                    finally:
                        row["elapsed_ms"] = (perf_counter() - began) * 1000
                        row["output_tag"] = output_tag(row, report["models"])
                        CURRENT_ROW.reset(token)
                        checkpoint()
                    summary = report["summary"]
                    progress(
                        f"{summary['requests_finished']:3}/100 {row['id']:3}  {row['category']:9}  "
                        f"{row['true_tag'] or 'unknown':10} {row['output_tag'] or 'unknown':10} "
                        f"{row['status']:9}  {row['elapsed_ms'] / 1000:5.1f}s  "
                        f"reported cost ${summary['reported_provider_cost_usd']:.4f}"
                    )

            await asyncio.gather(
                *(execute(case, row) for case, row in zip(cases, report["rows"], strict=True))
            )
            report["batch_elapsed_ms"] = (perf_counter() - started) * 1000
            report["status"] = "finished"
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
    except BaseException as exc:
        report["status"] = (
            "interrupted"
            if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError))
            else "failed"
        )
        report["error_kind"] = type(exc).__name__
        raise
    finally:
        checkpoint()
    return report, path
