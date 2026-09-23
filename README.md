# Model Router Lab

Research and a private GCP prototype using **`aac6fef/laya-mlx`** to propose LLM routes. Covers general chat/API, coding/agents, and business workflows.

**Recommendation:** use Laya inside a policy calibrated against real downstream outcomes. Keep capability checks deterministic, begin with two tiers, and retain a conservative fallback. The GPU decision service runs in shadow mode. The [Python OpenRouter adapter](docs/adapter.md) now dispatches real completions and streams, with explicit experimental thresholds for testing economy routing.

## What we measured

| Runtime / measurement | Median |
|---|---:|
| Cloud Run MLX CPU, client HTTP, six short requests | 26.45 s |
| Local PyTorch CPU, thirty short inferences | 688 ms |
| Cloud Run L4 MLX FP16, sixty model inferences | 9.47 ms |
| Same L4 service, client HTTP including network | 101.23 ms |

These are different hardware/measurement boundaries, not a controlled GPU speedup claim. GPU client p95 across all samples was **280 ms**; excluding the first call per prompt, it was **105 ms**. Startup took tens of seconds. Full methodology, sample sizes, probability comparisons, and raw data are in [findings](docs/findings.md).

No production quality or cost saving is established. None of the six fixtures exceeded the provisional economy threshold. Matched instruction prefixes changed routing probabilities; threshold selection needs actual task outcomes and robustness testing.

## Live prototype

- Project: `tribe-v2-host`; region: `asia-southeast1`.
- Service: `model-router-laya-gpu`; one L4, 4 vCPU, 16 GiB.
- Private IAM authentication; minimum zero, maximum one instance.
- Endpoint: `https://model-router-laya-gpu-635367932686.asia-southeast1.run.app/v1/route`.
- Health: `/health`; selected tier stays strong in shadow mode.
- [Exact deployment manifest](artifacts/deployment.json), [authentication/deployment/cleanup](docs/operations.md), [gateway contract](docs/integration.md).

The GPU bills while allocated, including warm idle time. Scaling to zero is not a hard dollar cap. The CPU baseline service was removed after measurement; its artifacts remain for reproduction.

## Read the research

- [Sources and initial hypotheses](docs/research.md)
- [Architecture, alternatives, economics, evaluation and rollout](docs/design.md)
- [Chat, coding/agent and business workload experiments](docs/workloads.md)
- [Measured findings and limitations](docs/findings.md)
- [Paired outcome evaluation format](docs/evaluation-data.md)

## Development

```powershell
uv sync --extra dev --extra adapter --python 3.12
uv run --no-sync pytest -q
uv run --no-sync ruff check src tests scripts
```

The policy/API/evaluation tests use fake inference and synthetic outcomes; real hosting probes are recorded separately. CI runs on every push. Model weights, credentials, and private evaluation data are excluded from Git.

To progress from this feasibility prototype to production routing, choose concrete downstream candidates per workload, gather representative paired outcomes, calibrate thresholds on a separate split, and validate the cost/quality tradeoff before enabling cheaper dispatch.
