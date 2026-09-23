"""Summarize recorded samples, retaining hardware and measurement distinctions."""

import json
import statistics
from pathlib import Path

from model_router.evaluation import quantile


def summary(values):
    return {
        "n": len(values),
        "p50_ms": statistics.median(values),
        "p95_ms": quantile(values, 0.95),
        "max_ms": max(values),
    }


result = {"note": "Synthetic short-request feasibility probes, not quality or saturation tests."}
root = Path("artifacts")
for name in ["local-mlx-cpu", "local-torch-cpu"]:
    path = root / (name + ".json")
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        result[name] = summary([s["e2e_ms"] for row in data["rows"] for s in row["samples"]])
for name in ["cloud-mlx-cpu", "cloud-mlx-gpu"]:
    path = root / (name + ".json")
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["rows"]
        result[name] = {
            "client": summary([row["client_ms"] for row in rows]),
            "server_router": summary([row["response"]["router_ms"] for row in rows]),
            "economy_proposals": sum(row["response"]["proposed_tier"] == "economy" for row in rows),
            "reasons": sorted({row["response"]["reason"] for row in rows}),
        }
        steady = [row["client_ms"] for row in rows if row["repeat"] > 0]
        if steady:
            result[name]["client_excluding_first_per_case"] = summary(steady)
        actual = [
            row["response"]["inference_ms"] for row in rows if row["response"]["inference_ms"] > 0
        ]
        if actual:
            result[name]["model_inference"] = summary(actual)
        # Slow-budget fallback responses in the first CPU revision record zero, not real zero latency.
if (root / "cloud-mlx-gpu.json").exists():
    cpu = json.loads((root / "local-mlx-cpu.json").read_text(encoding="utf-8"))
    gpu = json.loads((root / "cloud-mlx-gpu.json").read_text(encoding="utf-8"))
    probabilities = {row["case"]: row["samples"][0]["probability_economy"] for row in cpu["rows"]}
    differences = [
        abs(probabilities[row["case"]] - row["response"]["probability_economy"])
        for row in gpu["rows"]
        if row["response"]["probability_economy"] is not None
    ]
    result["gpu_vs_cpu_fixture_probability_max_abs_difference"] = (
        max(differences) if differences else None
    )
(root / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
