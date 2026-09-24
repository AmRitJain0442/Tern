# From clone to real local routing

GCP is optional. Local Laya classification needs no API key. For downstream answers, use OpenRouter by default or [configure other providers and call the Tern API](providers.md).

## 1. One-command setup

Clone the repository and enter it (the repository is currently private, so collaborator access is required):

```sh
git clone https://github.com/AmRitJain0442/tern.git
cd tern
```

Install and start [Docker Desktop](https://docs.docker.com/desktop/) or Docker Engine with Compose 2.24 or later. Then run this in PowerShell, bash or zsh:

```sh
docker compose up --build --wait
```

The command builds a Python/MLX runtime, downloads checkpoint `aac6fef/laya-mlx` at the pinned revision, loads it, performs a real forward pass, and waits for the service to become healthy. It runs in the background. You do not need host Python, uv, Google credentials or an API key. Package/model downloads require internet during the first setup; cached model startup and local inference do not.

The default container runs Linux x86_64 CPU inference. Windows uses Docker Desktop's Linux engine (normally WSL2). Allow several GB of disk space and at least 4 GB of available Docker memory; more may be needed with longer inputs. CPU inference can take tens of seconds. Apple Silicon users should use the native Metal command below rather than x86 emulation. This setup does not download downstream generative LLMs.

The service is published only on `127.0.0.1:8080`. Weights and generated reports use persistent Docker volumes, independent of image rebuilds. Repeating setup is safe; it reuses complete weights. Interrupted model downloads resume through Hugging Face's cache. An occupied port produces an error rather than replacing another service.

```sh
docker compose logs -f laya       # Download/startup progress; Ctrl+C leaves the service running
docker compose stop              # Stop; keep weights and results
docker compose up --wait         # Start again with cached weights
```

`docker compose down` also keeps the volumes. Adding `--volumes` would delete downloaded weights and saved results.

## 2. Make a real decision

```sh
docker compose exec laya tern route "Rewrite politely: send the report."
docker compose exec laya tern doctor --live
```

`route` uses actual Laya inference and prints the selected tier, proposed tier, score, reason and timings as JSON. It never calls OpenRouter. The service defaults to **shadow mode**: it reports Laya's proposed tier and probability but selects `strong`. These scores are not demonstrated downstream answer-quality probabilities.

`doctor --live` verifies Laya readiness. In default mode, an OpenRouter key also enables key/catalog validation without purchasing a generation; with no key it checks only Laya. With `TERN_CONFIG`, it checks provider configuration and credential presence instead. Custom provider connectivity is verified by a completion.

## 3. Generate answers (optional)

The server also exposes a Chat Completions API at `http://127.0.0.1:8080/v1` with model `tern/auto`. [HTTP requests, authentication, and provider configuration](providers.md) use the same running service as the CLI.

Create a `.env` file in the repository root with your own key, or add it to your existing file:

```dotenv
OPENROUTER_API_KEY=your-key-here
```

Then apply the configuration and send a prompt:

```sh
docker compose up --wait
docker compose exec laya tern chat "Explain idempotency in two sentences." --stream
```

Compose reads `.env` automatically; shell variables take precedence. The key is passed at runtime, not baked into the image. It is ignored by Git. Existing files are never rewritten by setup. The default models are `google/gemini-2.5-flash-lite` and `google/gemini-2.5-pro`; override them using `OPENROUTER_ECONOMY_MODEL` and `OPENROUTER_STRONG_MODEL`.

Generation uses OpenRouter and is paid. To try both tiers explicitly:

```sh
docker compose exec laya tern chat "Rewrite politely: send the report." --experimental-threshold 0.7
```

The threshold is experimental and uncalibrated; capability checks and conservative fallback still apply.

## Apple Silicon: native Metal

Requires macOS 14+, an Apple Silicon Mac, Git and [uv](https://docs.astral.sh/uv/getting-started/installation/). From the clone, one command installs Python 3.12 if needed, installs the MLX runtime, downloads the pinned model and starts the server:

```sh
uv run --python 3.12 --extra cli --extra mlx-metal tern serve
```

Keep that terminal open; Ctrl+C stops the service. In another terminal in the same directory:

```sh
uv run --no-sync tern route "Rewrite politely: send the report."
uv run --no-sync tern doctor --live
```

For answers, add the OpenRouter key to `.env`, then use `uv run --no-sync tern chat "Hello" --stream`. Use `--no-sync` in the second terminal so uv does not remove inference extras while the server is running. Later starts reuse the Hugging Face cache. `tern serve --port 8081` changes the port; set clients' `LAYA_ENDPOINT` accordingly. This Mac path follows upstream MLX support; the local Docker CPU path is the one validated on the maintainer's Windows machine. [MLX platform requirements](https://ml-explore.github.io/mlx/build/html/install.html).

## Optional NVIDIA acceleration

On Linux/WSL2 with a compatible NVIDIA GPU/driver and Docker GPU support configured:

```sh
docker compose -f compose.yaml -f compose.gpu.yaml up --build --wait
```

This installs the CUDA runtime instead of the CPU runtime and reuses the same weights. Host GPU drivers and the NVIDIA Container Toolkit are prerequisites; setup does not install or change drivers. MLX CUDA 12 requires NVIDIA SM 7.5+ and driver 550.54.14+; see the [upstream requirements](https://ml-explore.github.io/mlx/build/html/install.html#cuda). Local GPU availability varies by host. Metal cannot be used from a Linux container.

## Optional remote/GCP service

The native CLI defaults to local Laya. To use your own private Cloud Run service, put these settings in `.env`:

```dotenv
LAYA_ENDPOINT=https://your-private-service.run.app
LAYA_AUTH=gcloud
```

Install gcloud, sign in with `gcloud auth login`, and grant the account invoker access to that service. On a GCP workload use `LAYA_AUTH=google` for workload identity instead. Remote clients require HTTPS and keep Google authentication; unauthenticated HTTP is accepted only for literal loopback hosts. Local clients ignore proxy environment settings and send no Google token. Compose deliberately fixes its own CLI to the local container service, even if your host `.env` contains a cloud endpoint.

If using only the native client, install it with `uv sync --extra cli --python 3.12`. Use `uv run --no-sync tern doctor --live` to verify access. Cloud hosting and generation can incur charges. [Deployment guide](operations.md).

## Synthetic offline preview

```sh
docker compose exec laya tern demo
docker compose exec laya tern demo --all
docker compose exec laya tern demo --json
```

These commands execute 100 fixture requests through the adapter using synthetic scores and answers. They do not call the running Laya model or OpenRouter. For this preview alone, Docker/model downloads are unnecessary: `uv run --extra cli tern demo` works on Windows, Linux and macOS. Both `TRUE_TAG` and `OUTPUT_TAG` are shown; fixture expectations are not measured ground truth.

## Run 100 live requests

```sh
docker compose exec laya tern demo --live --experimental-threshold 0.7
```

This runs 100 real completions through OpenRouter by default, or through the providers in `TERN_CONFIG`: 25 rewrites, 25 coding prompts, 25 tool-call requests, and 25 short summaries. All prompts are synthetic test inputs, but classifier scores and generation responses are real. No model scores, completions or outages are simulated. The weather tool calls are checked for their function name and city; the tools themselves are not executed. Custom providers need correctly declared tool capabilities to handle those fixtures.

The 75 text requests are eligible for classification by your configured Laya service. The 25 tool requests use the strong model directly. An explicit `0.7` threshold can exercise both tiers; it is not calibrated. Without that flag or configured experimental thresholds, the adapter follows the deployed shadow policy and selects the strong model.

Defaults are four concurrent generations, serialized classification, a 30-second local CPU deadline (750 ms for remote clients by default), and 2,048 output tokens per provider attempt (including reasoning). You can change the generation limits and results path:

```sh
docker compose exec laya tern demo --live --experimental-threshold 0.7 --max-tokens 2048 --concurrency 4 --output artifacts/my-live-run.json
```

Hosted provider generations may be billed; local classification has no API charge. GCP charges apply only if you choose cloud hosting. A retryable economy error can cause one additional strong-model attempt. Each attempt has a 120-second generation deadline by default, configurable per provider. The runner records failures and continues through the batch; it does not automatically replay a failed run. Reported cost totals cover only attempts returning cost information; missing costs are counted separately.

Progress and a JSON checkpoint are written as requests finish. By default, each invocation creates a new timestamped file. An existing `--output` file is never overwritten. An interrupted request may have been billed even if no result was received, so do not assume pending/running rows are safe to replay.

Each progress row shows `ID`, `CATEGORY`, `TRUE_TAG`, `OUTPUT_TAG`, status, time, and cumulative reported cost. `TRUE_TAG` is a **declared fixture expectation**, not measured ground truth: rewrites and summaries expect `economy`; coding and tool requests expect `strong`. These assumptions are set before inference and never copied from predictions. The offline outage scenario expects `strong`. JSON records their provenance as `true_tag_source: "fixture_expectation"`.

`OUTPUT_TAG` is the adapter's final selected tier, including capability bypasses and provider fallbacks, rather than the raw classifier proposal. On a failed provider request it identifies the last attempted tier when known. A mismatch is a disagreement with the fixture expectation, **not evidence of incorrect answer quality**. Raw classifier scores and routing reasons remain in the report.

View a saved run without making API calls or modifying its evidence:

```sh
docker compose exec laya tern results artifacts/my-live-run.json
```

Older runs without reference labels show `unknown` under `TRUE_TAG`; labels are never invented from their predictions. New live runs and the offline demo include both tags.

Docker stores reports in the persistent results volume at `/app/artifacts`. Copy them to the host with `docker compose cp laya:/app/artifacts ./local-results`. Native CLI runs write to your current directory.

The report includes actual responses, routing decisions, raw successful classifier results, provider attempts, reported usage/cost, end-to-end latency, truncation flags, and basic tool-call validation. Costs exclude GCP and unknown charges on attempts that did not return usage. A completed response is a transport success, not proof of answer quality. Latency includes four-way generation concurrency; this is an integration run rather than a controlled performance benchmark.

`--json` prints the complete report to stdout and progress to stderr. `--all` controls the offline view; live mode always prints a line for each finished request and saves every response in the report.

See the [recorded 100-request run](live-results.md) for actual results, costs and limitations.

## Common fixes

| Symptom | What to do |
|---|---|
| Docker daemon unavailable | Start Docker Desktop; on Windows use its Linux/WSL2 engine |
| Setup is still waiting | Run `docker compose logs -f laya`; the first run downloads about 0.84 GB of weights and warms the model |
| Port 8080 is occupied | Set `TERN_PORT=8081` in `.env`, rerun Compose, and use that port for host clients |
| CPU routing times out | CPU inference can take tens of seconds. Prefer native Metal or supported NVIDIA hardware; adjust both the client deadline and server inference budget if needed |
| No generation key | `route` still works; use `OPENROUTER_API_KEY` or configure providers with `TERN_CONFIG` |
| Every selected tier is strong | Expected in shadow mode; inspect `proposed_tier` and `probability_economy`, or explicitly set an experimental threshold when generating answers |
| Native client still calls GCP | Existing `.env`/shell settings take precedence. Change `LAYA_ENDPOINT` to `http://127.0.0.1:8080` and `LAYA_AUTH` to `auto` |
| Answer is cut off | Increase `--max-tokens`; reasoning consumes part of the output budget |
| Apple Silicon install fails | Use macOS 14+ and a native ARM64 Python, not Rosetta |

## Next steps

- [Stream from Python](../examples/stream.py).
- [Understand the adapter contract](adapter.md).
- [Deploy an optional GPU endpoint](operations.md#gpu-experiment).
- [Measure quality before enabling economy routing](evaluation-data.md).
