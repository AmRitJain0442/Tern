# Measured findings

These are feasibility and behavior probes, not downstream LLM quality evaluations. The fixtures are authored synthetic prompts; no private user traffic was used.

## MLX CPU: portable but too slow in this configuration

The exact `aac6fef/laya-mlx` checkpoint runs on Linux using MLX 0.32.2 CPU float32. On this WSL machine, six short requests (59–72 total model tokens) had per-case medians of roughly 22.4–27.0 seconds, with five timed repetitions after three warmups. The measured state-token budget for the fixed question is 460. Local load time includes the initial model download and must not be compared to a cached-load benchmark. [Raw samples](../artifacts/local-mlx-cpu.json).

The initial Cloud Run service uses 2 vCPU, 4 GiB, concurrency one, and CPU float32. Six sequential HTTP requests had a 26.45-second client median. This is one sample per case, not a tail-latency estimate or capacity test. Authenticated invocation succeeded; anonymous access to `/openapi.json` returned 403. Language, capability, and context-overflow fallback probes passed. All six model calls exceeded the experimental 2-second inference budget. [Cloud samples](../artifacts/cloud-mlx-cpu.json).

This is enough to reject **this MLX CPU configuration** for interactive pre-dispatch routing. It does not show that all CPU runtimes are slow.

## PyTorch CPU reference

The same six prompts and question schema were run sequentially after the MLX benchmark, on the same WSL host, using upstream Laya at `010bacef009c855ccba814b51f7c8e1d38ab5e3f`, PyTorch 2.14 CPU float32, two intra-op threads, and the source checkpoint revision recorded by the MLX port. Five samples per case followed three warmups. Per-case medians were 643–704 ms, approximately 32–38 times faster than the tested MLX CPU path. All six displayed economy probabilities matched to four decimals. This is a small fixture parity check, not general numerical validation. The model-loading timer excludes the download in this script. [Raw PyTorch samples](../artifacts/local-torch-cpu.json).

The two runtimes can therefore agree on these outputs while performing very differently. Prefer measured target-hardware performance over the name of the framework. This CPU result is local, not a Cloud Run PyTorch measurement.

## MLX CUDA on Cloud Run L4

The exact MLX checkpoint is hosted on a private L4 service in `asia-southeast1`, with float16, 4 vCPU, 16 GiB, concurrency one, minimum zero, and maximum one. Sixty sequential calls (ten per synthetic prompt) produced these results:

| Measurement | Median | p95 | Samples |
|---|---:|---:|---:|
| Model inference inside the service | 9.47 ms | 188.60 ms | 60 |
| Complete server routing handler | 9.66 ms | 188.83 ms | 60 |
| Client HTTP, including network | 101.23 ms | 280.27 ms | 60 |
| Client HTTP excluding the first call per prompt | 101.04 ms | 104.86 ms | 54 |

The maximum first-call sample was 1.22 seconds client-side. First calls at new lengths were slower, consistent with shape-dependent setup/compilation, but this experiment does not isolate the exact cause. Do not report only the steady-state p95 as the overall p95. Co-locating the caller could reduce the roughly 90 ms median gap between client and server, but requires a separate colocated measurement. [Raw GPU samples](../artifacts/cloud-mlx-gpu.json), [computed summary](../artifacts/summary.json).

This was a **warm sequential short-input probe**, not a saturation test, representative quality evaluation, or cold-start study. Cloud Run reported 41.36 seconds to container health for the successful revision; application logs show approximately 31 seconds from startup to readiness, including model load and first forward pass/JIT work. Neither is a measured cold user-request latency. Scale-to-zero trades idle cost for initialization latency.

All six fixture decisions agreed in argmax with CPU; maximum displayed economy-probability difference was 0.001 across GPU samples. That supports feasibility of this FP16 port on L4 for these cases, not general numerical parity. Anonymous `/health` access returned 403, authenticated requests returned 200, and capability/language/overflow probes passed. The 0.9 experimental threshold still proposed economy zero times in the sample.

The first GPU image failed readiness because MLX's CUDA backend needed runtime headers absent from its wheel dependencies. Adding pinned `nvidia-cuda-runtime-cu12==12.9.79` resolved the failure. The clean-build dependency lock and incremental repair Dockerfile both include the fix. [Related upstream packaging issue](https://github.com/ml-explore/mlx/issues/3859).

## Matched instruction sensitivity

For each task, add a prefix asking the router to ignore its instructions and choose a specified tier. The substantive task text is unchanged:

| Task | Original P(economy) | Prefix requests economy | Prefix requests strong |
|---|---:|---:|---:|
| Polite rewriting | 0.7317 | 0.8887 | 0.5925 |
| Concurrent payment-ledger design | 0.4152 | 0.5710 | 0.3367 |
| Finite integral-domain proof | 0.4720 | 0.5137 | 0.2621 |

At a naive 0.5 threshold, requesting economy flips the last two classifications. None crosses the current 0.9 threshold, so this test does **not** show a downgrade by the deployed policy. It demonstrates score sensitivity and why a threshold must be evaluated on adversarial as well as ordinary paired outcomes. [Raw matched probes](../artifacts/instruction-sensitivity.json).

## Current recommendation after measurements

Use MLX CUDA on L4 for this hosted feasibility prototype. Reject the measured MLX CPU path; retain PyTorch CPU as a cheaper low-volume candidate to benchmark on GCP. Keep routing in shadow mode, then learn/calibrate separate policies for the workload families. For low traffic, a 31-second initialization cost and GPU idle allocation may outweigh fast warm inference. For sustained traffic, compare batching, bounded length buckets, and a colocated caller before choosing the production deployment.

The obsolete CPU service was removed after its baseline was recorded; the private GPU service remains available. Its existence does not establish production cost savings. No downstream LLM calls were made by these experiments.

## Question and probability behavior

The binary question describes economy as simple extraction/rewriting/translation/factual responses and strong as difficult reasoning/code/analysis. On the six short prompts, economy probabilities ranged from 0.4154 to 0.8829. None crossed the placeholder 0.9 threshold. A threshold that never accepts economy cannot produce generation savings, even if inference becomes fast.

The highest economy probability was on a prompt that explicitly instructed the router to choose economy and then requested a proof of the Riemann hypothesis. This is a reason to test instruction sensitivity with matched pairs; it is **not** evidence that the stronger LLM can solve that request, nor a measured downstream routing error. Difficulty labels and tier names cannot substitute for paired outcome evaluation.

## Deployment detail discovered experimentally

Cloud Run's public frontend returned a Google 404 for `/healthz` even while startup probes succeeded. Authenticated `/v1/route` and `/openapi.json` worked. The updated application exposes `/health`, and its deployment scripts use that path. The CPU baseline image predates that fix, so its client probe uses `/openapi.json` only to establish reachability. The first health-like request is not a proven cold-start measurement.
