# From clone to first route

The fastest first run is local and free. Cloud access is only needed for live routing.

## 1. Try the offline demo

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git, then:

```sh
git clone https://github.com/AmRitJain0442/tern.git
cd tern
uv sync --extra cli --python 3.12
uv run tern demo
```

These commands work in PowerShell, bash and zsh. The repository is private, so your GitHub account needs collaborator access. `uv` can install Python 3.12 if it is missing. You do not need CUDA, MLX, Docker, Google Cloud or an API key on your laptop for this demo.

Upgrading from Model Router? Run `uv sync --extra cli` to install the new `tern` command. The `model-router` command remains an alias, and existing `model_router` Python imports continue to work.

The demo sends **100 distinct synthetic requests** through the actual adapter using in-process HTTP transports: 25 polite rewrites, 25 coding tasks, 25 weather tool requests, and 25 classifier-outage cases. They demonstrate economy selection, strong selection, tool bypass and classifier failure fallback. The outages are interleaved with successful classifier calls so each demonstrates an isolated failure. These are not live inferences or quality benchmarks.

```sh
uv run tern demo          # Compact summary: 25 economy, 75 strong
uv run tern demo --all    # Show all 100 requests and their routing reasons
uv run tern demo --json   # Export summary and every request/response as JSON
```

All three modes execute the same 100 requests. Their scores and responses are synthetic; the counts describe this demo's fixtures, not expected routing proportions for real traffic.

## 2. Add local configuration

```sh
uv run tern init
```

Open `.env` in your editor and fill in:

```dotenv
OPENROUTER_API_KEY=your-key-here
OPENROUTER_ECONOMY_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_STRONG_MODEL=google/gemini-2.5-pro
LAYA_ENDPOINT=https://your-private-service.run.app
```

`init` uses this project's current private GPU endpoint as the default. Keep it if you have access, or replace it with your own deployment's origin (without `/v1/route`). Existing `.env` files are never overwritten. The CLI loads `.env` from your current directory, while existing environment variables take precedence. This repository ignores `.env` in Git and excludes it from Docker builds.

For another file, put the global flag before the command:

```sh
uv run tern --env-file .env.staging doctor
```

## 3. Check access

Install the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install) and sign in to an account with `roles/run.invoker` on your Laya service:

```sh
gcloud auth login
uv run tern doctor
uv run tern doctor --live
```

The local doctor checks configuration without displaying credential values. `--live` validates the key using OpenRouter's [current-key endpoint](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key), resolves your selected models in the catalog, and checks private GPU readiness. It does not purchase an LLM completion, but waking the Cloud Run GPU can incur charges. A first startup may take about a minute.

On a GCP workload with a service account, use `--auth google` instead of local `gcloud` authentication. The workload identity needs invoker access. Ordinary user ADC does not supply the production ID token used by this adapter. [Authentication details](adapter.md#integrate-in-an-application).

## 4. Send a live prompt

```sh
uv run tern chat "Explain idempotency in two sentences."
uv run tern chat "What is a cache?" --stream
uv run tern chat "What is 17 times 23?" --json
```

This uses paid OpenRouter generation and the private GPU service. The CLI warms the GPU at startup; it is meant for interactive use, not a replacement for a long-lived application client. Production applications should reuse the Python adapter's clients.

Shadow mode selects the strong model by default. An explicit experimental threshold enables economy selection for that request's workload:

```sh
uv run tern chat "Rewrite politely: send the report." --experimental-threshold 0.7
uv run tern chat "Explain lock contention." --workload coding --experimental-threshold 0.7
```

The threshold is not calibrated. Capability checks and failure fallback still apply.

## Run 100 live requests

```sh
uv run tern demo --live --experimental-threshold 0.7
```

This runs 100 real OpenRouter completions: 25 rewrites, 25 coding prompts, 25 tool-call requests, and 25 short summaries. All prompts are synthetic test inputs, but classifier scores and generation responses are real. No model scores, completions or outages are simulated. The weather tool calls are checked for their function name and city; the tools themselves are not executed.

The 75 text requests are eligible for classification on your private GCP GPU. The 25 tool requests use the strong model directly. An explicit `0.7` threshold exercises both tiers; it is not calibrated. Without that flag, the adapter follows the deployed shadow policy and selects the strong model.

Defaults are four concurrent generations, serialized GPU classification, a 750 ms classifier deadline, and 2,048 output tokens per provider attempt (including reasoning). You can change the generation limits and results path:

```sh
uv run tern demo --live --experimental-threshold 0.7 --max-tokens 2048 --concurrency 4 --output artifacts/my-live-run.json
```

Expect GCP and OpenRouter charges. A retryable economy error can cause one additional strong-model attempt. Each attempt has a 120-second generation deadline. The runner records failures and continues through the batch; it does not automatically replay a failed run.

Progress and a JSON checkpoint are written as requests finish. By default, each invocation creates a new timestamped file. An existing `--output` file is never overwritten. An interrupted request may have been billed even if no result was received, so do not assume pending/running rows are safe to replay.

The report includes actual responses, routing decisions, raw successful classifier results, provider attempts, reported usage/cost, end-to-end latency, truncation flags, and basic tool-call validation. Costs exclude GCP and unknown charges on attempts that did not return usage. A completed response is a transport success, not proof of answer quality. Latency includes four-way generation concurrency; this is an integration run rather than a controlled performance benchmark.

`--json` prints the complete report to stdout and progress to stderr. `--all` controls the offline view; live mode always prints a line for each finished request and saves every response in the report.

See the [recorded 100-request run](live-results.md) for actual results, costs and limitations.

## Useful switches

| Switch | Default | Purpose |
|---|---|---|
| `--stream` | Off | Print output as it arrives; Ctrl+C closes the upstream stream |
| `--json` | Off | Full completion, routing decision, attempts and usage as JSON; incompatible with `--stream` |
| `--max-tokens` | `4096` | Output budget, including model reasoning |
| `--input-tokens` | `8192` for short CLI prompts | Declare a conservative bound on input tokens across your models |
| `--language` | `en` | Set the trusted prompt language; unsupported languages use the strong model |
| `--workload` | `chat` | `chat`, `coding` or `business` |
| `--auth` | `gcloud` | Use `google` for service-account credentials or GCP metadata |
| `--experimental-threshold` | Unset | Explicit economy policy in `(0.5, 1]` |

The convenience input budget only applies to a single text prompt of at most 4,096 UTF-8 bytes. Longer prompts require an explicit bound; it is not a universal tokenizer. For history, tools or multimodal input, use the [Python API](adapter.md) and account for the complete payload in your bound.

## Common fixes

| Symptom | What to do |
|---|---|
| Repository not found | Sign in to GitHub with an account granted access to this private repo |
| `tern` not found | Run it as `uv run tern …` after `uv sync --extra cli` |
| Missing OpenRouter key | Add it to `.env` in the directory where you run the command |
| Local doctor passes, live doctor fails | Verify the key, Google login and invoker permission; local checks do not authenticate |
| Cold startup is slow | Allow startup to finish; the service scales to zero when idle |
| Every request uses the strong model | Expected in shadow mode; economy requires an explicit experimental threshold |
| `router_timeout` selects strong | The short classification deadline expired; conservative fallback worked |
| Answer is cut off | Increase `--max-tokens`; reasoning consumes part of that budget |
| A request is ineligible | Check capabilities, model allowlists and input/output budgets; do not silently truncate the prompt |

## Next steps

- [Stream from Python](../examples/stream.py).
- [Understand the adapter contract](adapter.md).
- [Deploy your own GPU endpoint](operations.md#gpu-experiment).
- [Measure quality before enabling economy routing](evaluation-data.md).
