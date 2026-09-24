# One Tern API, configurable providers

Tern exposes a Chat Completions API alongside local Laya inference. Your app calls `tern/auto`; Tern selects an eligible economy or strong model and sends the request to that model's configured provider. Each provider has its own URL and credentials. GCP is optional.

## Start with OpenRouter

Add `OPENROUTER_API_KEY=your-key` to the ignored `.env` file, then run:

```sh
docker compose up --build --wait
```

The same command installs the runtime, downloads the pinned Laya weights on first use, and starts the API. See [local setup](quickstart.md) for Docker prerequisites and native Metal/NVIDIA options. This downloads the classifier; downstream generative models run at your chosen provider.

| App setting | Value |
|---|---|
| Base URL | `http://127.0.0.1:8080/v1` |
| Model | `tern/auto` |
| API key | Your `TERN_API_KEY`, if set; a placeholder is sufficient for loopback development without authentication |
| Model discovery | `GET /v1/models` |
| Generate or stream | `POST /v1/chat/completions` |

From the repository root, with curl installed:

```sh
curl http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" --data-binary @examples/chat-request.json
```

In Windows PowerShell use `curl.exe` for that command. The [example request](../examples/chat-request.json) contains:

```json
{
  "model": "tern/auto",
  "messages": [{"role": "user", "content": "Rewrite politely: send the report."}],
  "max_tokens": 2048,
  "routing": {"input_tokens": 256, "language": "en", "workload": "chat"}
}
```

Generation may be billed by the provider. The default shadow policy selects the strong model and includes the classifier's proposal in the `tern.routing` response field. CPU classification can take tens of seconds; allow sufficient client timeout. The HTTP API calls Laya in the same process, avoiding another classifier HTTP request.

Set `TERN_API_KEY` in the server's `.env` to require `Authorization: Bearer <your-tern-key>` on the two Chat Completions API endpoints. This is a separate key for callers of Tern; it is never forwarded to a model provider. Apply environment changes with `docker compose up --wait` or restart the native server. `/health` and `/v1/route` remain under the existing loopback/Cloud Run IAM boundary.

## Choose providers

Copy one of these files to `config/providers.json`, then edit the provider URL, upstream model IDs and capabilities:

| Starting point | Intended use |
|---|---|
| [openrouter.example.json](../config/openrouter.example.json) | Explicit OpenRouter model aliases and policy configuration |
| [mixed.example.json](../config/mixed.example.json) | A compatible economy endpoint with OpenRouter for strong requests |
| [local.example.json](../config/local.example.json) | Two already-installed models behind a local compatible server |

Add the following to `.env`, alongside the environment variables named by each provider's `api_key_env`:

```dotenv
TERN_CONFIG=config/providers.json
```

Then apply and check it:

```sh
docker compose up --force-recreate --wait
docker compose exec laya tern doctor --live
docker compose exec laya tern chat "Explain idempotency in two sentences." --input-tokens 256 --max-tokens 512 --stream
```

Compose mounts `config/` read-only and passes `.env` variables at runtime. The optional environment-file syntax requires [Compose 2.24 or later](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/). The native CLI and `tern serve` also read `.env`. Neither path rewrites your existing configuration. Provider JSON changes require restarting the server; `--force-recreate` ensures they are reloaded. `config/providers.json` is ignored by Git.

`TERN_CONFIG` applies to the HTTP API, `tern chat`, and the 100-request `tern demo --live`. Without it, the existing OpenRouter environment settings still work. `doctor --live` checks Laya readiness and configured credential presence; a custom provider is only verified remotely by making a completion. It does not claim every provider exposes an equivalent key-validation or capability endpoint.

### Configuration contract

Each `providers` entry accepts:

| Field | Meaning |
|---|---|
| `type` | `openai_compatible` (default), or `openrouter` for OpenRouter-specific parameter enforcement |
| `base_url` | URL prefix before `/chat/completions`, including any `/v1` path |
| `api_key_env` | Environment variable holding this provider's key; omit for an unauthenticated local server |
| `auth_header` | `Authorization` (Bearer, default), or `api-key` (raw key) |
| `token_parameter` | `max_tokens` (default), or `max_completion_tokens` for endpoints requiring it |
| `timeout` | Per-attempt HTTP timeout in seconds, default 120, maximum 600 |
| `allow_http` | Default false; explicitly opt in for HTTP on a trusted private network |

Keys belong in the environment, never in JSON. URL credentials, query strings, redirects and arbitrary headers are not supported. Remote endpoints require HTTPS unless explicitly configured for private HTTP. Callers cannot supply provider URLs or provider credentials in a completion request.

Each `models` entry supplies a unique local `id`, `provider`, `upstream_model`, `tier`, `context_length`, `max_output_tokens`, and supported parameters/modalities. Local IDs appear in routing results; upstream model names are sent to providers. Capabilities are explicit configuration, not inferred from model names. Set conservative limits from your provider's documentation and verify them with real requests. `max_tokens` remains the canonical capability name even when the transport sends `max_completion_tokens`. JSON-schema output requires both `response_format` and `structured_outputs` capabilities.

Model order is priority order within each tier: Tern uses the first eligible candidate. An eligible strong fallback is required. Additional entries offer capability alternatives, not round-robin balancing or a general multi-hop retry chain. Economy and strong candidates may use different providers, or different models on the same provider.

To experiment with economy selection, add a top-level field such as `"experimental_thresholds": {"chat": 0.7}`. Thresholds are uncalibrated and should be evaluated for your model pair. CLI `--experimental-threshold` overrides configured thresholds for that invocation. Constraints, classifier errors and unsupported requests retain conservative behavior.

## Platform coverage

The integration boundary is the Chat Completions protocol. These are connection paths, **not a claim that every vendor or model feature has been live-tested**:

| Platform | Connection path |
|---|---|
| OpenRouter | Built-in default transport, or explicit `type: openrouter` |
| Groq | Compatible transport; [`https://api.groq.com/openai/v1`](https://console.groq.com/docs/openai) |
| Gemini API | Compatible transport; [`https://generativelanguage.googleapis.com/v1beta/openai`](https://ai.google.dev/gemini-api/docs/openai) |
| Ollama | Compatible transport; [`http://127.0.0.1:11434/v1`](https://docs.ollama.com/api/openai-compatibility), with models installed separately |
| Other hosted or self-hosted compatible endpoints | Compatible transport with the deployment's documented base URL, auth and capabilities |
| Native APIs, including Anthropic, Bedrock and Vertex AI | Connect through a translation gateway such as [LiteLLM](https://docs.litellm.ai/docs/providers), subject to its supported models and features |

For LiteLLM, follow its [gateway setup](https://docs.litellm.ai/docs/proxy/docker_quick_start) in a separate directory. Configure provider-specific credentials there. In Tern, use its compatible URL (for example `http://127.0.0.1:4000/v1`), an environment variable holding a gateway virtual key, and the gateway's model aliases as `upstream_model`. Tern supplies classification and tier selection; the gateway handles native API/auth translation. This avoids embedding every vendor SDK in Tern. LiteLLM is an optional separate service, not installed automatically by Tern setup.

For a model server or gateway running on your Docker Desktop host, container loopback points to the container itself. Use `http://host.docker.internal:PORT/v1` and set `allow_http: true` for that trusted connection. Linux Docker hosts may require an `extra_hosts: ["host.docker.internal:host-gateway"]` Compose override. The upstream server must listen on an address reachable from the container.

## Request and streaming behavior

Supported fields are `model`, `messages`, `max_tokens` (or `max_completion_tokens`, but not both), `temperature`, `tools`, `tool_choice`, `response_format`, `seed`, `stop`, `stream`, `stream_options.include_usage`, and the optional Tern `routing` object. Unknown top-level fields are rejected. This is a Chat Completions subset; it does not expose Responses, embeddings, image generation, audio generation, native vendor APIs or arbitrary vendor extensions.

`routing.input_tokens` is a conservative upper bound for the full input across candidate tokenizers, including formatting, tools and any multimodal input. For small text-only payloads without `routing`, Tern reserves 8,192 input tokens. Long or multimodal payloads require an explicit bound. The default language is unknown, which conservatively bypasses classification. Supply `routing.language` per request, or set config `default_language` / environment `TERN_DEFAULT_LANGUAGE` only when that assumption is true for your traffic. The config value takes precedence when a config file is loaded.

Messages, history, tool calls and structured output settings are preserved. History, tools, multimodal input, high-stakes requests and unsupported languages bypass Laya and select an eligible strong model. Private-processing and region-bound requests remain rejected by this integration.

For streaming, set `"stream": true`; optionally add `"stream_options": {"include_usage": true}` if your provider supports usage chunks. Tern forwards SSE chunks and `[DONE]`, including tool deltas and usage. The `X-Tern-Tier`, `X-Tern-Model` and `X-Tern-Reason` headers identify the final selected route; model/reason values are URL-encoded. Non-streaming responses also contain `tern.routing` and `tern.attempted_models`.

An explicit retryable economy failure can trigger one strong attempt, including across providers. Timeouts are not blindly replayed. Once output starts, a stream failure emits a sanitized error event, closes the upstream connection and omits `[DONE]`; it never retries generated output. Failures before streaming begins return an HTTP error response.

Tests cover cross-provider credential isolation, fallback, payload preservation, streaming errors/disconnects, custom provider CLI/live-demo use, and key/header/token-parameter configuration using mock transports. Those checks establish transport behavior, not downstream model quality or universal vendor compatibility.

## Recorded live API check

The [recorded API smoke run](../artifacts/gateway-smoke.json) used real Laya on the local Docker CPU runtime and OpenRouter for two generations: a text completion and a streamed, forced weather tool call. It verified model discovery, bearer-key rejection, actual Laya probability output, routing headers, tool arguments, usage chunks and stream completion. The tool was not executed. Provider-reported cost was **$0.0176525**, excluding local compute; this is an integration check, not a quality or latency benchmark. Other vendor integrations have not been live-verified.

To repeat the paid check against your running server, install the CLI dependencies with `uv sync --extra cli`, then use a new output filename:

```sh
uv run --no-sync python scripts/smoke_gateway.py --output artifacts/my-api-smoke.json
```

The script reads `TERN_API_KEY` from the environment or `.env`, caps each generation at 2,048 output tokens, checkpoints responses, and refuses to overwrite an existing report. It expects English text classification and a strong model supporting forced tools and streamed usage; use the OpenRouter example configuration for the recorded setup.
