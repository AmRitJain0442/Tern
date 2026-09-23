# Routing design and experiment plan

## Recommendation

Use Laya as a **cheap feature/decision producer inside a measured policy**, initially for a two-tier pool. Keep capability checks deterministic. Train or calibrate the final decision against the actual models and workload. A model that recognizes difficult-looking text is not necessarily a model that predicts comparative LLM performance.

The deployed prototype is deliberately a decision API. It makes the hosting hypothesis testable without coupling inference experiments to provider credentials or generation spend. A gateway can later map its tiers to concrete model IDs.

## Four useful designs

| Design | What Laya does | Best use | Principal failure | Priority |
|---|---|---|---|---|
| Binary pre-dispatch | Predict economy vs strong from request text | Two LLMs with a meaningful price gap | Difficulty labels do not track model-specific quality | First experiment |
| Task features plus policy | Predict domain, task, or reasoning requirements; policy uses model outcomes | Several task-specialized models | More questions mean more inference work and calibration dimensions | Second if binary loses coverage |
| Response cascade | Assess cheap-model output and escalate on likely failure | Tasks with reliable validators | Pays for the first answer and sometimes the second; false acceptance | Prefer executable validators over subjective judging |
| Learned quality/cost head | Predict per-model outcomes from Laya representations | Stable workload with labeled traffic | Data collection, retraining, drift, and selection bias | Long-term candidate |

FrugalGPT studies learned cascades, an alternative to deciding before generation. Its results are evidence for the approach, not a guarantee that Laya is a good answer evaluator. [FrugalGPT](https://arxiv.org/abs/2305.05176).

Do not ask Laya to choose opaque model names whose current abilities it has never observed. Describe capabilities for a zero-shot baseline; learn outcomes for a durable policy. Reevaluate whenever a model alias, pricing schedule, or tool environment changes.

## Policy objective

For request x and eligible models M(x), target:

`argmin_m E[cost(m,x) + retry_cost(m,x)]`

subject to a task-quality floor and an end-to-end latency budget. Cost includes input, cached input, output, reasoning tokens where billed, router compute, network, and failed attempts. A weighted utility objective is another option, but its weights must reflect actual product preferences.

With two models, learn the quality difference `Q_strong(x) - Q_economy(x)` and the total cost difference. This avoids treating every hard prompt as necessarily benefiting from the stronger model. Some requests are unanswerable by both; some are easy for a specialist small model.

Use route probabilities for **ranking** initially. Fit a calibration mapping to downstream outcomes only on a calibration split. Temperature scaling that improves the typed decision task does not establish calibration for LLM answer quality. The port computes choice confidence from normalized entropy; it is a different quantity from the top label probability. [Pinned implementation](https://github.com/mizorewww/laya-mlx/blob/0a859518634112655cb97c745dbf04f5191aaf13/laya_mlx/common.py).

## Constraints before classification

The gateway determines eligible models using trusted metadata: language, input/output context capacity, image/audio support, tools, structured output, regional restrictions, provider health, and available budget. Never infer permission from request text or let the model override these constraints.

The prototype only classifies short English standalone requests. Unknown language, history, tools, vision, and high-stakes flags take a conservative path. Private-processing requests return no route until an appropriate deployment is configured. A `strong` tier is not proof of a capability: the caller must map only eligible concrete deployments into it. The endpoint has no raw chat-history or multimedia schema and must not be used as a drop-in chat proxy.

For a conversation, include system instructions, relevant earlier turns, tool state, and latest intent. Laya's small context creates a genuine tradeoff. Options are a trusted short routing summary, several bounded views with conservative disagreement handling, a longer-context router, or bypass. Do not silently cut the conversation or increase the model's trained limit just because the encoder can accept more positions.

For agents, evaluate complete tasks, including tool calls and retries. Per-turn savings can be overwhelmed by extra turns. Route at stable task boundaries, retain session affinity when useful, and promote after repeated validator failures. Do not switch models in the middle of a streamed response.

## Efficiency sequence

1. **Avoid unnecessary decisions.** Single eligible model, explicit tier, and unsupported inputs need no classifier pass.
2. **Keep the question short.** Test one binary question before a multi-question taxonomy. Questions are batched rows, not free additional labels.
3. **Colocate.** Measure caller-to-router and router-to-provider round trips. A remote service can erase local single-digit-millisecond advantages.
4. **Load once per process.** Bake pinned weights into the image, warm up before readiness, and use one worker to avoid duplicate resident models.
5. **Benchmark lengths and load.** Short, typical, and near-context-limit prompts; concurrency 1/2/4/8; open-loop arrival tests; queueing and rejection included. Report model time, warm request time, cold first response, p50/p95/p99, and sustainable throughput separately.
6. **Optimize the measured bottleneck.** CPU PyTorch/ONNX/OpenVINO INT8, MLX CUDA, and C++ are candidates. Quantization must pass decision/probability agreement and downstream quality tests, particularly near routing thresholds. [Alternative C++ implementation](https://github.com/lkarlslund/laya.cpp).
7. **Batch only when traffic supports it.** Cross-request microbatches need a bounded wait and queue. Length bucketing reduces padding but increases scheduler complexity. Large batches do not demonstrate low interactive latency.
8. **Cache carefully.** A routing cache key needs tenant, full normalized input, metadata, candidate pool, policy version, and checkpoint revision. Do not cache only the latest user sentence. Measure whether hit rate pays for storage/network overhead.

## Hosting choices

| Option | Advantage | Cost/latency tradeoff | Decision |
|---|---|---|---|
| MLX on local Apple Silicon | Existing hardware, no request network hop | Not this Windows/GCP environment; Mac measurements do not transfer | Edge option for Mac clients |
| Cloud Run CPU | Scale-to-zero, straightforward deployment | Cold starts and CPU forward-pass latency | Current experimental host |
| Cloud Run L4 | Managed GPU, scale-to-zero, batching potential | Minimum CPU/RAM allocation and billed warm instance time | Benchmark if CPU misses measured SLO |
| Compute Engine GPU | Control of runtime and sustained throughput | VM operations and idle cost | Consider for steady volume |
| Vertex AI endpoint | Managed model lifecycle and deployment integration | Pricing and scaling depend on endpoint type | Use when lifecycle requirements justify it |
| GKE | Shared serving fleet and scheduling flexibility | Operational overhead | Defer for this small service |

Cloud Run's GPU platform startup figure excludes application model loading. L4 needs at least 4 vCPU and 16 GiB; Mumbai access is invitation-only per the current documentation, so an available region may add a network hop. [GCP GPU documentation](https://docs.cloud.google.com/run/docs/configuring/services/gpu).

## Cost arithmetic

Use regional SKU rates before a budget decision. For illustration, the displayed on-demand request rates of $0.000024/vCPU-second and $0.0000025/GiB-second imply $0.000058/active second at 2 vCPU and 4 GiB, before request fees and other services. A hypothetical 200 ms request costs about $0.0000116 of active compute; a 2-second request costs ten times as much. Actual request billing rounds time and includes startup. [Cloud Run pricing](https://cloud.google.com/run/pricing).

At the displayed instance rates, L4 without zonal redundancy plus 4 vCPU/16 GiB is approximately `(0.0001867 + 4*0.000018 + 16*0.000002)*3600 = $1.0465/hour`. It is about $764/month if continuously allocated for 730 hours, before other costs. GPU-only price is an incomplete estimate. These are planning examples, not a quote for our deployment.

For a constant-price two-tier simplification:

`saving/request = economy_fraction * (strong_cost - economy_cost) - router_cost - extra_retry_cost`

If the strong answer costs $0.003, economy $0.0003, and routing $0.00003, break-even coverage before retries is roughly 1.11%. If the models differ by only $0.00001, that router loses money at every coverage. Real token lengths correlate with route and must be calculated per row. Output length and retries can dominate input price differences.

## Evaluation that answers the real question

Collect representative queries and outcomes from every candidate model on the same frozen prompts. Start with a small pilot to debug labels, then scale according to statistical uncertainty; hundreds of easy synthetic prompts cannot establish production quality. Preserve separate train, calibration, and untouched test splits, grouped by conversation, customer/template family, and time. Prevent paraphrases of the same problem from leaking across splits.

Use executable tests for code, exact/structured checks for extraction, and blinded rubric judgments with human spot checks for open-ended answers. Randomize judge order, track ties, and do not assume an LLM judge is ground truth. Record failures and full billed token usage. A routed production log alone cannot reveal the unchosen model's counterfactual result; a limited randomized exploration sample or offline paired evaluation is needed.

Required baselines: always economy, always strong, random at equal economy coverage, simple task/length heuristics, embedding plus logistic regression, RouteLLM-style preference routing, Laya binary, Laya task features, and an oracle **upper bound** using known outcomes. [RouteLLM](https://arxiv.org/abs/2406.18665), [RouterBench](https://arxiv.org/abs/2403.12031).

Report quality versus total cost and latency, routing coverage, harmful downgrade rate (`economy fails AND strong succeeds`), abstentions, timeout rate, calibration metrics if predicting the corresponding event, and slices by language/domain/length/tools. Use paired bootstrap confidence intervals grouped by conversation. Select the threshold on calibration data, then report one frozen threshold on test; a test-set threshold sweep is exploratory and must be labeled accordingly.

Suggested acceptance target, pending product preference: at least 20% total cost reduction with the upper confidence bound on quality loss below one percentage point and no unacceptable regression in a critical slice. This is a proposal, not an achieved result. Pick the simpler static policy if learned routing fails to beat it.

## Rollout and monitoring

Shadow predictions first; map tiers to real providers only after evaluation. Use a small canary with a rollback switch and fixed policy version. Track route mix, selected/proposed differences, latency percentiles, fallback reasons, token spend, and task outcomes without recording raw prompts by default. Revalidate on drift and candidate-model changes.

A gateway such as LiteLLM already implements provider retries, cooldowns, and fallback mechanics; connect the learned quality policy above that layer rather than recreating those functions. Cap retries across both gateway and SDK to avoid multiplying calls. [LiteLLM routing documentation](https://docs.litellm.ai/docs/routing).

## What remains unproven

- Whether Laya beats static routing for the user's real workload.
- Which downstream model pair gives enough quality/cost separation.
- Whether Linux MLX is the fastest economical GCP runtime.
- Whether multilingual, conversation summaries, or agent features improve routing.
- Whether any threshold in the current prototype is calibrated.

The runtime benchmark and deployed endpoint answer feasibility questions only. They are not a production cost-saving claim.
