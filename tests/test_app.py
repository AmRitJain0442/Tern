from fastapi.testclient import TestClient

from model_router.app import create_app
from model_router.backend import BackendBusy, ContextOverflow


class FakeBackend:
    revision = "test"

    def predict(self, text):
        if text == "overflow":
            raise ContextOverflow()
        if text == "busy":
            raise BackendBusy()
        if text == "failure":
            raise RuntimeError("possibly sensitive text")
        return 0.99, 10, 80


def test_api_proposal_and_fallbacks():
    with TestClient(create_app(FakeBackend)) as client:
        assert client.get("/health").json()["ready"]
        for prompt, reason in [
            ("hi", "shadow_proposal"),
            ("overflow", "router_context_overflow"),
            ("busy", "router_busy"),
            ("failure", "router_error"),
        ]:
            response = client.post("/v1/route", json={"prompt": prompt, "language": "en"})
            assert response.status_code == 200
            data = response.json()
            assert data["reason"] == reason
            assert data["selected_tier"] == "strong"
            assert data["router_ms"] >= 0


def test_invalid_payload_and_unknown_metadata_rejected():
    with TestClient(create_app(FakeBackend)) as client:
        for body in [
            {"prompt": ""},
            {"prompt": "a" * 16001},
            {"prompt": "hi", "provider_url": "https://example.com"},
            {"prompt": "hi", "eligible_tiers": ["invented"]},
        ]:
            assert client.post("/v1/route", json=body).status_code == 422
