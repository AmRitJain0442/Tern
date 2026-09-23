"""Paired offline evaluation. Rows must contain outcomes for BOTH candidate models."""

import math
import random
from collections import defaultdict
from statistics import mean

from pydantic import BaseModel, ConfigDict, Field


class OutcomeRow(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str
    group: str  # conversation/template cluster; used for bootstrap resampling
    split: str
    probability_economy: float = Field(ge=0, le=1)
    economy_eligible: bool
    quality_economy: float = Field(ge=0, le=1)
    quality_strong: float = Field(ge=0, le=1)
    cost_economy: float = Field(ge=0)
    cost_strong: float = Field(ge=0)
    router_cost: float = Field(ge=0)
    # All costs are USD per request, including billed retries. Router cost is separate.


def quantile(values, probability):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * probability
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def evaluate(rows: list[OutcomeRow], threshold=0.9, bootstrap=2000, seed=42):
    if not rows or not 0.5 < threshold <= 1 or bootstrap < 1:
        raise ValueError("Need nonempty rows, threshold in (0.5, 1], and positive bootstrap")
    if len({row.id for row in rows}) != len(rows):
        raise ValueError("Duplicate request IDs")
    if len({row.split for row in rows}) != 1:
        raise ValueError("Evaluate one split at a time; never mix calibration and test")
    choose = [row.economy_eligible and row.probability_economy >= threshold for row in rows]
    quality = [r.quality_economy if c else r.quality_strong for r, c in zip(rows, choose)]
    cost = [(r.cost_economy if c else r.cost_strong) + r.router_cost for r, c in zip(rows, choose)]
    deltas = [q - r.quality_strong for q, r in zip(quality, rows)]
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row.group].append(index)
    rng, names = random.Random(seed), list(groups)
    boot = []
    for _ in range(bootstrap):
        indices = [i for name in rng.choices(names, k=len(names)) for i in groups[name]]
        boot.append(mean(deltas[i] for i in indices))
    eligible = sum(r.economy_eligible for r in rows)
    # Exact expected random baseline at the same eligible coverage; no noisy random run.
    fraction = sum(choose) / eligible if eligible else 0
    random_quality, random_cost = [], []
    for row in rows:
        p = fraction if row.economy_eligible else 0
        random_quality.append(p * row.quality_economy + (1 - p) * row.quality_strong)
        random_cost.append(p * row.cost_economy + (1 - p) * row.cost_strong)
    baseline_cost = mean(r.cost_strong for r in rows)
    return {
        "n": len(rows),
        "groups": len(groups),
        "split": rows[0].split,
        "threshold": threshold,
        "bootstrap": bootstrap,
        "seed": seed,
        "laya": {
            "quality": mean(quality),
            "mean_cost_usd": mean(cost),
            "economy_fraction": mean(choose),
            "quality_delta_vs_strong": mean(deltas),
            "quality_delta_95pct_cluster_bootstrap": [quantile(boot, 0.025), quantile(boot, 0.975)],
            "cost_reduction_vs_strong": 1 - mean(cost) / baseline_cost if baseline_cost else None,
            "downgrade_loss": mean(max(0, r.quality_strong - q) for r, q in zip(rows, quality)),
        },
        "baselines": {
            "always_strong": {
                "quality": mean(r.quality_strong for r in rows),
                "mean_cost_usd": baseline_cost,
            },
            "economy_when_eligible": {
                "quality": mean(
                    r.quality_economy if r.economy_eligible else r.quality_strong for r in rows
                ),
                "mean_cost_usd": mean(
                    r.cost_economy if r.economy_eligible else r.cost_strong for r in rows
                ),
            },
            "random_same_coverage_expected": {
                "quality": mean(random_quality),
                "mean_cost_usd": mean(random_cost),
            },
            "oracle_quality_upper_bound": mean(
                max(r.quality_economy, r.quality_strong) if r.economy_eligible else r.quality_strong
                for r in rows
            ),
        },
        "notes": [
            "Threshold must be selected on a separate calibration split.",
            "Static/random baselines do not pay for a Laya call.",
            "Small numbers of independent groups produce unreliable confidence intervals.",
            "Label probabilities are not evaluated as quality probabilities.",
        ],
    }
