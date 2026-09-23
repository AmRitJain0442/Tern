# Laya GPU → OpenRouter adapter

The Python adapter calls the existing private Cloud Run L4 service for a routing decision, maps its tier to a configured OpenRouter model, and returns a completion or an asynchronous stream. MLX inference stays on GCP; the calling application does not need MLX or a GPU installed.

## Run the live smoke test

```powershell
uv sync --extra dev --extra adapter --python 3.12
# Put OPENROUTER_API_KEY in the ignored .env file; see .env.example.
gcloud auth login
uv run --no-sync --env-file .env python scripts/smoke_adapter.py
```

This sends four synthetic generation requests, each capped at 1,024 output tokens: a shadow completion, an experimental stream, a coding completion, and a forced tool call. It writes results after each request to `artifacts/openrouter-adapter-smoke.json`. It can incur GCP and OpenRouter charges. An explicit retryable economy failure permits one strong-model attempt, so four fixtures can produce more than four generation attempts. Provider usage includes reasoning tokens when reported; output limits can leave reasoning models without visible text.

The default candidates are `google/gemini-2.5-flash-lite` and `google/gemini-2.5-pro`. These are configurable smoke-test candidates, not a demonstrated optimal pair. The script resolves their capabilities from the current OpenRouter catalog before sending completions.

## Integrate in an application

```python
import os
from model_router.adapters import (
    ChatRequest, LayaGPUClient, OpenRouterAdapter, OpenRouterClient, RoutingContext,
)

async def answer():
    async with LayaGPUClient() as laya, OpenRouterClient(
        os.environ["OPENROUTER_API_KEY"]
    ) as provider:
        await laya.warmup()  # Startup only; may take tens of seconds after scale-to-zero.
        models = await provider.models({
            "google/gemini-2.5-flash-lite": "economy",
            "google/gemini-2.5-pro": "strong",
        })
        adapter = OpenRouterAdapter(models, laya, provider)
        result = await adapter.complete(
            ChatRequest(messages=[{"role": "user", "content": "What is 17 times 23?"}]),
            RoutingContext(input_tokens=256, language="en", workload="chat"),
        )
        return result
```

For an application server, create both clients and the adapter once in its startup lifespan, reuse them across requests, and close them on shutdown. `RoutingContext.input_tokens` must be a conservative upper bound across candidate tokenizers, including all messages, chat formatting, tool schemas and multimodal tokens. The example's bound applies only to that tiny fixed prompt. A character-count heuristic is not a general multimodal token estimator. Underestimating this value can result in a provider context-limit error; the adapter never truncates messages.

`LayaGPUClient` uses audience-bound Google ID tokens from service-account credentials or GCP metadata. Grant the application's service account `roles/run.invoker` on `model-router-laya-gpu`; the audience is the service origin. Ordinary user ADC is not a substitute for this production identity. Local scripts explicitly use `GcloudIDTokenProvider`, with the logged-in account that already has invoker permission. Tokens are cached and concurrent refreshes coalesced; credentials and provider bodies are excluded from error messages.

On GCP the OpenRouter credential should come from the application's secret environment, such as Secret Manager. The GPU decision service itself does not need the OpenRouter key. The local `.env` is ignored by Git and excluded from the container build context.

## Selection and fallback behavior

An eligible strong fallback is required. Candidate checks cover enabled status, caller allowlists, input modalities, requested parameters, output limits and context length. OpenRouter receives `provider.require_parameters=true` and a fixed model ID; its provider fallback stays within that model. The catalog is a model-level capability summary, not a guarantee that every provider is available or accepts every parameter value. The adapter preserves provider errors when no suitable endpoint is available.

| Request | Behavior |
|---|---|
| One short English user message | Ask Laya; respect its selected tier |
| History/system messages, tools, images/audio, high-stakes, unknown/non-English language | Eligible strong model without a classifier call |
| No eligible economy model | Eligible strong model without a classifier call |
| Private-processing or region-bound requirement | Reject locally; corresponding OpenRouter restrictions are not configured |
| No eligible strong model | Reject locally before either network call |
| Classifier timeout, invalid result, revision mismatch, failure or open circuit | Eligible strong model |
| Economy gets explicit 429/502/503/504 before output | One strong-model attempt |
| Network timeout, authentication/payment/input errors, strong-model failure | Surface sanitized error; no adapter retry |
| Failure after any streamed chunk | Surface error; no replay |

Unknown message roles and unsupported content-part types are rejected. The first version accepts text, image URLs and input audio, but does not expose every OpenRouter feature (for example files, video, plugins or provider-specific reasoning controls). “All workloads” means these workloads have a conservative route; it does not imply Laya has been validated for every task.

The classifier deadline is **750 ms total**, including token acquisition and HTTP. Three consecutive failures open its circuit for 15 seconds. The startup warmup has a separate 90-second allowance. A cold classifier can therefore yield strong-model fallback until warm; min instances remains zero on GCP.

Nonstreaming generation has a 60-second total deadline per attempt by default. Streaming uses a 60-second HTTP inactivity timeout, not a total stream duration limit. Applications should enforce their own end-to-end cancellation deadline. OpenRouter may also perform provider retries within its own request. Adapter attempt counts do not describe those internal attempts.

## Explicit experimental economy routing

The deployed decision service remains in shadow mode. By default the adapter therefore dispatches to the strong model even when Laya proposes economy. To test a workload threshold:

```python
adapter = OpenRouterAdapter(
    models, laya, provider,
    experimental_thresholds={"chat": 0.7, "coding": 0.7},
)
```

This allows an eligible economy model when Laya's label probability meets the configured threshold. It never overrides classifier overflow, errors or capability constraints. Workloads without a configured threshold continue to follow the service. The returned decision records the threshold, probability, service policy version and service mode. **0.7 is a smoke-test setting, not a calibrated quality threshold.** Establish quality and savings through paired outcomes before using this policy for real traffic.

## Streaming and observability

```python
from contextlib import aclosing

async with aclosing(adapter.stream(request, context)) as stream:
    async for item in stream:
        send_to_client(item.chunk)  # Your application's transport.
```

Use `aclosing`, especially when a consumer may disconnect or break early. Cancellation or closing the stream closes the upstream HTTP response; it does not guarantee that a provider stops billing. Each item contains the routing decision and attempted model IDs, while its `chunk` preserves OpenRouter content, tool-call deltas, finish reasons and usage. The parser ignores SSE comments, handles split UTF-8 and multiline data events, requires `[DONE]`, and detects errors embedded in HTTP 200 responses.

Completions likewise preserve the full response. Record `routing`, `attempted_models`, actual response `model`, usage/cost and end-to-end latency as appropriate for your data policy. The adapter does not log request content. `routing.router_ms` measures local selection plus the classifier round trip, excluding generation. Stream usage can be unavailable if the stream fails or is cancelled before its final usage chunk.

Transport tests are in `tests/test_adapter.py`; they need no live credentials. The live smoke artifact is separate evidence of connectivity and payload behavior, not a quality or savings benchmark.

## Recorded live results (2026-09-23)

The [recorded run](../artifacts/openrouter-adapter-smoke.json) used the existing MLX FP16 L4 deployment and the model IDs above.

| Fixture | Actual route | Observation |
|---|---|---|
| Default shadow completion | Gemini 2.5 Pro | First classifier call exceeded 750 ms; strong fallback returned text |
| Experimental rewrite stream | Gemini 2.5 Flash Lite | Laya probability 0.7487 exceeded the explicit 0.7 threshold; content and final usage received |
| Experimental coding completion | Gemini 2.5 Pro | Laya probability 0.4800; strong selected |
| Forced tool request | Gemini 2.5 Pro | Classifier bypassed; `get_weather` call returned with `city=Paris` |

Startup health took **44.40 seconds**, without independent proof that this was a cold start. The two successful in-path classifier calls took **264 ms** and **254 ms** including network. A subsequent decision-only probe confirmed normal shadow selection and **12.26 ms** model inference. Startup health does not guarantee every first prompt will meet the short routing deadline.

OpenRouter reported **$0.0222233 total**, excluding GPU/network costs. Both Pro text completions ended with `finish_reason=length`; their 1,024-token limits included 979 reported reasoning tokens. The adapter preserved those finish reasons and partial responses. These are transport successes with truncated answers, not passing quality evaluations. The tool call and Flash Lite stream completed normally. No savings conclusion follows from comparing these four different outcomes.

## Protocol references

- [OpenRouter request and response API](https://openrouter.ai/docs/api_reference/overview)
- [OpenRouter streaming and errors](https://openrouter.ai/docs/api_reference/streaming)
- [OpenRouter provider selection](https://openrouter.ai/docs/guides/routing/provider-selection)
- [Cloud Run service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
- [Google audience-bound ID token credentials](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.id_token.html)
