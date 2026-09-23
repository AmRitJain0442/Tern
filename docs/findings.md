# Measured findings

These are feasibility and behavior probes, not downstream LLM quality evaluations. The fixtures are authored synthetic prompts; no private user traffic was used.

## MLX CPU: portable but too slow in this configuration

The exact `aac6fef/laya-mlx` checkpoint runs on Linux using MLX 0.32.2 CPU float32. On this WSL machine, six short requests (59–72 total model tokens) had per-case medians of roughly 22.4–27.0 seconds, with five timed repetitions after three warmups. The measured state-token budget for the fixed question is 460. Local load time includes the initial model download and must not be compared to a cached-load benchmark. [Raw samples](../artifacts/local-mlx-cpu.json).

The initial Cloud Run service uses 2 vCPU, 4 GiB, concurrency one, and CPU float32. Six sequential HTTP requests had a 26.45-second client median. This is one sample per case, not a tail-latency estimate or capacity test. Authenticated invocation succeeded; anonymous access to `/openapi.json` returned 403. Language, capability, and context-overflow fallback probes passed. All six model calls exceeded the experimental 2-second inference budget. [Cloud samples](../artifacts/cloud-mlx-cpu.json).

This is enough to reject **this MLX CPU configuration** for interactive pre-dispatch routing. It does not show that all CPU runtimes are slow. An upstream PyTorch comparison and an L4 CUDA experiment follow.

## Question and probability behavior

The binary question describes economy as simple extraction/rewriting/translation/factual responses and strong as difficult reasoning/code/analysis. On the six short prompts, economy probabilities ranged from 0.4154 to 0.8829. None crossed the placeholder 0.9 threshold. A threshold that never accepts economy cannot produce generation savings, even if inference becomes fast.

The highest economy probability was on a prompt that explicitly instructed the router to choose economy and then requested a proof of the Riemann hypothesis. This is a reason to test instruction sensitivity with matched pairs; it is **not** evidence that the stronger LLM can solve that request, nor a measured downstream routing error. Difficulty labels and tier names cannot substitute for paired outcome evaluation.

## Deployment detail discovered experimentally

Cloud Run's public frontend returned a Google 404 for `/healthz` even while startup probes succeeded. Authenticated `/v1/route` and `/openapi.json` worked. The updated application exposes `/health`, and its deployment scripts use that path. The CPU baseline image predates that fix, so its client probe uses `/openapi.json` only to establish reachability. The first health-like request is not a proven cold-start measurement.
