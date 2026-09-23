import pytest

from model_router.policy import RouteRequest, Settings, decide, preflight


def test_shadow_never_sends_traffic_to_unvalidated_economy():
    request = RouteRequest(prompt="Hello", language="en")
    result = decide(request, Settings(), 0.99, 20, 80)
    assert result.proposed_tier == "economy"
    assert result.selected_tier == "strong"


@pytest.mark.parametrize("fields,reason", [
    ({"language": "hi"}, "unsupported_or_unknown_language"),
    ({"requires_tools": True}, "capability_or_risk_constraint"),
    ({"requires_vision": True}, "capability_or_risk_constraint"),
    ({"high_stakes": True}, "capability_or_risk_constraint"),
    ({"has_conversation_history": True}, "full_conversation_required"),
    ({"eligible_tiers": ["strong"]}, "economy_ineligible"),
])
def test_constraints_bypass_classifier(fields, reason):
    args = {"prompt": "Hello", "language": "en", **fields}
    assert preflight(RouteRequest(**args), Settings()).reason == reason


def test_private_processing_is_not_guessed():
    req = RouteRequest(prompt="Hello", requires_private_processing=True)
    assert preflight(req, Settings()).selected_tier is None


def test_absent_fallback_does_not_violate_eligibility():
    req = RouteRequest(prompt="Hello", language="en", eligible_tiers=["economy"])
    assert decide(req, Settings(), 0.99, 20, 80).selected_tier is None
    assert decide(req, Settings(mode="experimental"), 0.2, 20, 80).selected_tier is None


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_probabilities_fall_back(probability):
    assert decide(RouteRequest(prompt="Hello"), Settings(), probability, 20, 80).selected_tier == "strong"


def test_slow_inference_cannot_downroute():
    result = decide(RouteRequest(prompt="Hello"), Settings(mode="experimental"), 0.99, 3000, 80)
    assert result.reason == "inference_budget_exceeded"
    assert result.selected_tier == "strong"


def test_threshold_boundary():
    req = RouteRequest(prompt="Hello")
    config = Settings(mode="experimental", threshold=0.9)
    assert decide(req, config, 0.9, 10, 80).selected_tier == "economy"
    assert decide(req, config, 0.8999, 10, 80).selected_tier == "strong"
