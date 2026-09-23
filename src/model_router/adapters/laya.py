"""Bounded authenticated client for the existing private MLX GPU decision endpoint."""

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from model_router.adapters.auth import GoogleIDTokenProvider
from model_router.adapters.types import DecisionUnavailable
from model_router.backend import MODEL_REVISION
from model_router.policy import RouteRequest, RouteResponse

DEFAULT_ENDPOINT = "https://model-router-laya-gpu-635367932686.asia-southeast1.run.app"


class LayaGPUClient:
    def __init__(
        self,
        endpoint=DEFAULT_ENDPOINT,
        *,
        token_provider: Callable[[], Awaitable[str]] | None = None,
        timeout=0.75,
        failure_threshold=3,
        cooldown=15.0,
        expected_revision=MODEL_REVISION,
        transport=None,
    ):
        url = urlsplit(endpoint)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise ValueError("Laya endpoint must be an HTTPS origin without credentials or query")
        if (
            not math.isfinite(timeout)
            or timeout <= 0
            or failure_threshold < 1
            or not math.isfinite(cooldown)
            or cooldown <= 0
        ):
            raise ValueError("Invalid deadline or circuit settings")
        self.endpoint = endpoint.rstrip("/")
        self.token_provider = token_provider or GoogleIDTokenProvider(self.endpoint)
        self.timeout, self.failure_threshold, self.cooldown = timeout, failure_threshold, cooldown
        self.expected_revision = expected_revision
        self._failures = 0
        self._open_until = 0.0
        self._http = httpx.AsyncClient(transport=transport, follow_redirects=False, timeout=timeout)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        await self._http.aclose()

    async def _headers(self):
        try:
            token = await self.token_provider()
            if not isinstance(token, str) or not token.strip():
                raise ValueError("empty token")
            return {"Authorization": "Bearer " + token}
        except Exception:
            raise DecisionUnavailable("router_auth_error") from None

    async def warmup(self, timeout=90):
        """Explicit startup action; never performed automatically in the request path."""
        async with asyncio.timeout(timeout):
            response = await self._http.get(
                self.endpoint + "/health", headers=await self._headers(), timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            if (
                data.get("ready") is not True
                or data.get("model_revision") != self.expected_revision
            ):
                raise DecisionUnavailable("router_not_ready")
            return data

    async def decide(self, request: RouteRequest) -> RouteResponse:
        if time.monotonic() < self._open_until:
            raise DecisionUnavailable("router_circuit_open")
        try:
            # HTTPX timeouts are phase/inactivity limits; this bounds auth + the entire HTTP call.
            async with asyncio.timeout(self.timeout):
                response = await self._http.post(
                    self.endpoint + "/v1/route",
                    headers=await self._headers(),
                    json=request.model_dump(),
                )
                if response.status_code != 200:
                    raise DecisionUnavailable(f"router_http_{response.status_code}")
                data = RouteResponse.model_validate(response.json(), strict=True)
                if data.model_revision != self.expected_revision:
                    raise DecisionUnavailable("router_revision_mismatch")
                values = [data.router_ms, data.inference_ms]
                if any(not math.isfinite(v) or v < 0 for v in values):
                    raise DecisionUnavailable("router_invalid_response")
                if data.probability_economy is not None and (
                    not math.isfinite(data.probability_economy)
                    or not 0 <= data.probability_economy <= 1
                ):
                    raise DecisionUnavailable("router_invalid_response")
                if data.mode == "shadow" and data.selected_tier == "economy":
                    raise DecisionUnavailable("router_invalid_response")
                if (
                    data.selected_tier is not None
                    and data.selected_tier not in request.eligible_tiers
                ):
                    raise DecisionUnavailable("router_ineligible_selection")
            self._failures = 0
            return data
        except (TimeoutError, httpx.TimeoutException):
            reason = "router_timeout"
        except httpx.HTTPError:
            reason = "router_transport_error"
        except DecisionUnavailable as exc:
            reason = str(exc)
        except (ValidationError, ValueError):
            reason = "router_invalid_response"
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._open_until = time.monotonic() + self.cooldown
        raise DecisionUnavailable(reason) from None
