"""Decision API; Cloud Run IAM is the authentication boundary."""

import logging
import os
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI

from model_router.backend import BackendBusy, ContextOverflow, MLXBackend
from model_router.policy import (
    RouteRequest,
    RouteResponse,
    Settings,
    conservative,
    decide,
    preflight,
)

logger = logging.getLogger(__name__)


def create_app(backend_factory=MLXBackend, settings=None):
    config = settings or Settings(
        mode=os.environ.get("ROUTER_MODE", "shadow"),
        threshold=float(os.environ.get("ECONOMY_THRESHOLD", "0.9")),
        max_inference_ms=float(os.environ.get("MAX_INFERENCE_MS", "2000")),
    )

    @asynccontextmanager
    async def lifespan(app):
        app.state.backend = backend_factory()
        # Readiness means both weights and a real forward pass succeeded.
        app.state.backend.predict("Rewrite: Hello, how are you?")
        yield

    app = FastAPI(title="Model Router Lab", lifespan=lifespan)

    @app.get("/healthz")
    def health():
        return {"ready": True, "mode": config.mode, "model_revision": app.state.backend.revision}

    @app.post("/v1/route", response_model=RouteResponse)
    def route(request: RouteRequest):
        started = perf_counter()
        response = preflight(request, config)
        if response is None:
            try:
                probability, elapsed, tokens = app.state.backend.predict(request.prompt)
                response = decide(request, config, probability, elapsed, tokens)
            except ContextOverflow:
                response = conservative(request, config, "router_context_overflow")
            except BackendBusy:
                response = conservative(request, config, "router_busy")
            except Exception as exc:
                # Exception messages may contain user text. Log only the class.
                logger.error("Inference failed: %s", type(exc).__name__)
                response = conservative(request, config, "router_error")
        response.model_revision = app.state.backend.revision
        response.router_ms = round((perf_counter() - started) * 1000, 3)
        return response

    return app


app = create_app()
