# 100-request live run

Completed on **2026-09-23**, starting at **15:16:01 UTC**. These were actual OpenRouter generations using the private GCP Laya GPU service, with synthetic test prompts. The [full report](../artifacts/live-100-openrouter.json) contains all 100 distinct provider generation IDs, responses, routing decisions, classifier results and usage records.

## Results

| Measurement | Result |
|---|---:|
| Completed requests with nonempty output | 100 / 100 |
| Provider attempts | 100 |
| Provider errors | 0 |
| Flash Lite completions | 65 |
| Gemini Pro completions | 35 |
| Valid weather function-and-city calls | 25 / 25 |
| Successful GPU classifications | 72 / 75 attempted |
| Classifier deadline fallbacks | 3 |
| Responses truncated at the output limit | 1 |
| Reported OpenRouter generation cost | $0.19648025 |
| Median request latency | 1.58 s |
| Request p95, nearest rank | 16.42 s |
| Median model inference, successful classifier calls | 10.67 ms |
| Batch duration after setup | 95.12 s |
| GPU startup health check | 46.30 s |

The 25 tool requests bypassed classification by policy. All returned `get_weather` calls with the expected city. No weather API was invoked.

## Routes by workload

| Category | Requests | Flash Lite | Gemini Pro | Reported cost |
|---|---:|---:|---:|---:|
| Polite rewrites | 25 | 24 | 1 | $0.01769345 |
| Coding prompts | 25 | 17 | 8 | $0.13524050 |
| Tool-call requests | 25 | 0 | 25 | $0.03119625 |
| Short summaries | 25 | 24 | 1 | $0.01235005 |

This is the observed split under an **uncalibrated 0.7 threshold**, not the offline demo's preset 25/75 split. No answer-quality comparison against an all-strong baseline was performed. The 17 coding requests sent to Flash Lite still need quality evaluation before this policy is suitable for real coding traffic.

## Configuration

```sh
uv run tern demo --live --experimental-threshold 0.7 --max-tokens 2048 --concurrency 4 --output artifacts/live-100-openrouter.json
```

The existing output file is protected from overwriting; omit `--output` for a fresh timestamped run. Re-running makes another 100 paid requests.

- Economy model: `google/gemini-2.5-flash-lite`.
- Strong model: `google/gemini-2.5-pro`.
- GPU endpoint: a private maintainer-owned Cloud Run L4 service in `asia-southeast1`; its URL and project identifier are redacted from the public report.
- Checkpoint: `aac6fef/laya-mlx`, revision `20aed815fc6acde75733882e7ec0e3f28aeb9717`.
- GPU service remained in shadow mode; the adapter explicitly applied the experimental threshold.
- Four concurrent generations; classifier calls serialized to the single GPU instance.
- 750 ms classifier deadline; 120 seconds per generation attempt.
- Maximum 2,048 output tokens per provider attempt, including reasoning.

## Limitations observed

Requests **1, 4 and 10** exceeded the classifier deadline and used the strong fallback. They completed successfully downstream. Their classifier inference time is unavailable, so the 10.67 ms median includes only successful classifier responses.

Request **6**, an idempotent payment-handler coding prompt, ended with `finish_reason=length`. Gemini Pro reported 1,902 reasoning tokens within 2,044 completion tokens, leaving a truncated visible answer. The runner records it as a completed HTTP generation with a truncation flag, not a passing quality result.

Costs are reported by OpenRouter and exclude GPU allocation, startup, storage and networking. All 100 attempts returned usage/cost; there were no missing-cost attempts in this run. Latencies include network and concurrent generation but exclude waiting for a worker slot; batch duration includes that scheduling. Startup time is recorded separately and does not independently prove a cold start. These measurements establish integration behavior, not production SLAs or cost savings.
