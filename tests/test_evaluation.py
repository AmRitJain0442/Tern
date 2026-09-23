import pytest
from pydantic import ValidationError

from model_router.evaluation import OutcomeRow, evaluate


def row(id="a", **kw):
    return OutcomeRow(
        id=id,
        group=id,
        split="test",
        **{
            "probability_economy": 0.99,
            "economy_eligible": True,
            "quality_economy": 1,
            "quality_strong": 1,
            "cost_economy": 0.001,
            "cost_strong": 0.01,
            "router_cost": 0.0001,
            **kw,
        },
    )


def test_router_overhead_and_fallback_are_charged_correctly():
    result = evaluate([row(), row("b", economy_eligible=False, quality_economy=0)])
    assert result["laya"]["quality"] == 1
    assert result["laya"]["mean_cost_usd"] == pytest.approx(0.0056)
    assert result["laya"]["economy_fraction"] == 0.5
    assert result["laya"]["quality_delta_95pct_cluster_bootstrap"] == [0, 0]


def test_harmful_downgrade_and_random_baseline():
    result = evaluate([row(quality_economy=0), row("b", probability_economy=0.6)])
    assert result["laya"]["quality_delta_vs_strong"] == -0.5
    assert result["baselines"]["random_same_coverage_expected"]["quality"] == 0.75


def test_bad_data_cannot_silently_bias_metrics():
    with pytest.raises(ValidationError):
        row(cost_economy=float("nan"))
    with pytest.raises(ValueError):
        evaluate([row(), row()])
    other = row("b").model_copy(update={"split": "calibration"})
    with pytest.raises(ValueError):
        evaluate([row(), other])
