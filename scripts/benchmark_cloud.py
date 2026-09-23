"""Authenticated sequential Cloud Run probe; credentials never enter artifacts."""

import argparse
import json
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from benchmark_local import CASES

parser = argparse.ArgumentParser()
parser.add_argument("--endpoint", required=True)
parser.add_argument("--output", type=Path, default=Path("artifacts/cloud-mlx-cpu.json"))
parser.add_argument("--repeats", type=int, default=3)
args = parser.parse_args()
if args.repeats < 1:
    parser.error("repeats must be positive")
token = subprocess.check_output(["gcloud.cmd", "auth", "print-identity-token"], text=True).strip()
rows = []
with httpx.Client(timeout=90) as client:
    anonymous = client.get(args.endpoint + "/healthz")
    if anonymous.status_code != 403:
        raise RuntimeError(f"Expected anonymous rejection, got {anonymous.status_code}")
    client.headers["Authorization"] = "Bearer " + token
    start = time.perf_counter()
    health = client.get(args.endpoint + "/healthz")
    health.raise_for_status()
    first_health_ms = (time.perf_counter() - start) * 1000
    for name, prompt in CASES:
        for repeat in range(args.repeats):
            start = time.perf_counter()
            response = client.post(
                args.endpoint + "/v1/route", json={"prompt": prompt, "language": "en"}
            )
            elapsed = (time.perf_counter() - start) * 1000
            response.raise_for_status()
            rows.append(
                {"case": name, "repeat": repeat, "client_ms": elapsed, "response": response.json()}
            )
        print(name, round(rows[-1]["client_ms"], 1), "ms", flush=True)
    for request, reason in [
        ({"prompt": "Hello"}, "unsupported_or_unknown_language"),
        ({"prompt": "hello " * 2000, "language": "en"}, "router_context_overflow"),
        (
            {"prompt": "Hello", "language": "en", "requires_tools": True},
            "capability_or_risk_constraint",
        ),
    ]:
        response = client.post(args.endpoint + "/v1/route", json=request)
        response.raise_for_status()
        if response.json()["reason"] != reason:
            raise RuntimeError("Constraint probe failed: " + reason)
result = {
    "kind": "sequential_synthetic_hosting_probe_not_quality_evaluation",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "endpoint": args.endpoint,
    "anonymous_status": anonymous.status_code,
    "first_health_ms": first_health_ms,
    "first_health_is_proven_cold_start": False,
    "health": health.json(),
    "rows": rows,
    "median_client_ms": statistics.median(row["client_ms"] for row in rows),
    "constraints_passed": True,
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"median_client_ms": result["median_client_ms"], "constraints_passed": True}))
