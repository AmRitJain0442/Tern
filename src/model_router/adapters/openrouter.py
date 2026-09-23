"""OpenRouter transport with preserved responses, bounded requests and SSE errors."""

import asyncio
import json
import math

import httpx

from model_router.adapters.types import ChatRequest, ModelSpec, ProviderError

BASE_URL = "https://openrouter.ai/api/v1"
RETRYABLE_STATUSES = {429, 502, 503, 504}


def check_payload(payload):
    if not isinstance(payload, dict):
        raise ProviderError(None, kind="invalid_response")
    error = payload.get("error")
    choices = payload.get("choices")
    partial_error = any(
        isinstance(c, dict) and (c.get("error") or c.get("finish_reason") == "error")
        for c in (choices if isinstance(choices, list) else [])
    )
    if error or partial_error:
        code = error.get("code") if isinstance(error, dict) else None
        status = code if isinstance(code, int) and not isinstance(code, bool) else None
        raise ProviderError(
            status,
            retryable=status in RETRYABLE_STATUSES and not partial_error,
            kind="response_error",
        )
    if not isinstance(choices, list) or any(not isinstance(c, dict) for c in choices):
        raise ProviderError(None, kind="invalid_response")
    return payload


class OpenRouterClient:
    def __init__(self, api_key: str, *, timeout=60.0, transport=None):
        if not api_key or not api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is required")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Provider timeout must be positive")
        self.timeout = timeout
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            headers={
                "Authorization": "Bearer " + api_key.strip(),
                "X-OpenRouter-Title": "Model Router Lab",
            },
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        await self._http.aclose()

    async def models(self, assignments: dict[str, str]) -> list[ModelSpec]:
        """Resolve explicit IDs against current public catalog; no model-name guessing."""
        response = await self._http.get("/models")
        response.raise_for_status()
        catalog = {row["id"]: row for row in response.json()["data"]}
        specs = []
        for model_id, tier in assignments.items():
            if model_id not in catalog:
                raise ValueError(f"Model absent from OpenRouter catalog: {model_id}")
            row = catalog[model_id]
            top = row.get("top_provider") or {}
            context = min(row["context_length"], top.get("context_length") or row["context_length"])
            specs.append(
                ModelSpec(
                    id=model_id,
                    tier=tier,
                    context_length=context,
                    max_output_tokens=top.get("max_completion_tokens") or context,
                    input_modalities=row.get("architecture", {}).get("input_modalities", ["text"]),
                    supported_parameters=row.get("supported_parameters", []),
                )
            )
        return specs

    @staticmethod
    def _body(model, request: ChatRequest, stream):
        return {
            **request.model_dump(exclude_none=True),
            "model": model,
            "stream": stream,
            # Keep the selected model fixed; provider failover stays within that model.
            "provider": {"require_parameters": True, "allow_fallbacks": True},
        }

    @staticmethod
    def _check_status(response):
        if response.status_code != 200:
            raise ProviderError(
                response.status_code, retryable=response.status_code in RETRYABLE_STATUSES
            )

    async def complete(self, model: str, request: ChatRequest) -> dict:
        try:
            async with asyncio.timeout(self.timeout):
                response = await self._http.post(
                    "/chat/completions", json=self._body(model, request, False)
                )
                self._check_status(response)
                payload = check_payload(response.json())
                if not payload["choices"]:
                    raise ProviderError(None, kind="empty_response")
                return payload
        except (TimeoutError, httpx.TimeoutException):
            # The provider may already have billed a completion; never blindly replay it.
            raise ProviderError(None, kind="timeout") from None
        except httpx.HTTPError:
            raise ProviderError(None, kind="transport_error") from None
        except (ValueError, TypeError):
            raise ProviderError(None, kind="invalid_response") from None

    async def stream(self, model: str, request: ChatRequest):
        # Per-read timeout stays active while awaiting provider data. The outer adapter must
        # close this generator on client disconnect; it never retries a partially yielded stream.
        try:
            async with self._http.stream(
                "POST", "/chat/completions", json=self._body(model, request, True)
            ) as response:
                self._check_status(response)
                if "text/event-stream" not in response.headers.get("content-type", ""):
                    await response.aread()
                    check_payload(response.json())
                    raise ProviderError(None, kind="expected_event_stream")
                parts, size = [], 0
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        part = line[5:].lstrip(" ")
                        size += len(part)
                        if size > 1_048_576:
                            raise ProviderError(None, kind="oversized_event")
                        parts.append(part)
                    elif line == "" and parts:
                        data = "\n".join(parts)
                        parts, size = [], 0
                        if data == "[DONE]":
                            return
                        yield check_payload(json.loads(data))
                raise ProviderError(None, kind="incomplete_stream")
        except httpx.TimeoutException:
            raise ProviderError(None, kind="timeout") from None
        except httpx.HTTPError:
            raise ProviderError(None, kind="transport_error") from None
        except (ValueError, TypeError):
            raise ProviderError(None, kind="invalid_response") from None
