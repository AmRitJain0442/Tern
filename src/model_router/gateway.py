"""A Chat Completions API backed by Tern's existing policy and configurable providers."""

import asyncio
import json
import secrets
from contextlib import aclosing
from typing import Literal
from urllib.parse import quote

import anyio
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from model_router.adapters.router import OpenRouterAdapter, inspect_request
from model_router.adapters.types import ChatRequest, NoEligibleModel, ProviderError, RoutingContext


class CompletionRequest(ChatRequest):
    model: Literal["tern/auto"] = "tern/auto"
    stream: bool = False
    routing: RoutingContext | None = None


class InProcessClassifier:
    def __init__(self, classify):
        self._classify = classify

    async def decide(self, request):
        # Keep synchronous MLX inference off the API's event loop.
        return await asyncio.to_thread(self._classify, request)


class Gateway:
    def __init__(self, classifier, providers, *, api_key=None, default_language="unknown"):
        self.classifier, self.providers = classifier, providers
        self.api_key = api_key
        self.default_language = default_language
        self._adapter = None
        self._lock = asyncio.Lock()

    def authorized(self, authorization):
        if not self.api_key:
            return True
        expected = ("Bearer " + self.api_key).encode("utf-8")
        return secrets.compare_digest((authorization or "").encode("utf-8"), expected)

    async def adapter(self):
        async with self._lock:
            if self._adapter is None:
                settings = self.providers.settings
                self._adapter = OpenRouterAdapter(
                    await self.providers.models(),
                    self.classifier,
                    self.providers,
                    experimental_thresholds=settings.experimental_thresholds if settings else None,
                )
            return self._adapter

    def context(self, body, request):
        modalities, _, _ = inspect_request(request)
        if body.routing is not None:
            return body.routing
        if (
            modalities != {"text"}
            or len(json.dumps(request.model_dump(exclude_none=True)).encode("utf-8")) > 4096
        ):
            raise ValueError("Supply routing.input_tokens for long or multimodal requests")
        settings = self.providers.settings
        return RoutingContext(
            input_tokens=8192,
            language=settings.default_language if settings else self.default_language,
        )


def api_error(status, code, message):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "message": message,
                "type": code,
                "param": None,
                "code": code,
            }
        },
    )


def provider_error(exc):
    status = 504 if exc.kind == "timeout" else 429 if exc.status == 429 else 502
    return api_error(
        status, "upstream_error", "The selected provider could not complete the request"
    )


def routing_headers(decision):
    return {
        "X-Tern-Tier": decision.tier,
        "X-Tern-Model": quote(decision.model, safe=""),
        "X-Tern-Reason": quote(decision.reason, safe=""),
    }


class ClosingStream(StreamingResponse):
    """Always release the upstream generator, including a disconnect before iteration."""

    def __init__(self, content, upstream, **kwargs):
        super().__init__(content, **kwargs)
        self.upstream = upstream

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.upstream.aclose()


def install_gateway_routes(app):
    @app.get("/v1/models")
    async def models(request: Request):
        gateway = request.app.state.gateway
        if not gateway.authorized(request.headers.get("authorization")):
            return api_error(401, "authentication_error", "Invalid Tern API key")
        return {
            "object": "list",
            "data": [
                {
                    "id": "tern/auto",
                    "object": "model",
                    "created": 0,
                    "owned_by": "tern",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def completions(body: CompletionRequest, request: Request):
        gateway = request.app.state.gateway
        if not gateway.authorized(request.headers.get("authorization")):
            return api_error(401, "authentication_error", "Invalid Tern API key")
        try:
            chat = ChatRequest.model_validate(
                body.model_dump(exclude={"model", "stream", "routing"})
            )
            if chat.stream_options is not None and not body.stream:
                raise ValueError("stream_options requires stream=true")
            context = gateway.context(body, chat)
            if context.requires_private_processing or context.required_region:
                raise NoEligibleModel("Private or region-bound generation is not configured")
        except ValueError as exc:
            return api_error(400, "invalid_request_error", str(exc))
        try:
            adapter = await gateway.adapter()
        except Exception:
            # Server configuration/catalog errors can contain keys or provider bodies.
            return api_error(
                503, "configuration_error", "Configure providers and credentials on the Tern server"
            )
        try:
            if not body.stream:
                result = await adapter.complete(chat, context)
                return JSONResponse(
                    {
                        **result.response,
                        "tern": {
                            "routing": result.routing.model_dump(),
                            "attempted_models": result.attempted_models,
                        },
                    },
                    headers=routing_headers(result.routing),
                )
            upstream = adapter.stream(chat, context)
            try:
                first = await anext(upstream)
            except BaseException:
                await upstream.aclose()
                raise

            async def events():
                try:
                    async with aclosing(upstream):
                        yield "data: " + json.dumps(first.chunk) + "\n\n"
                        async for item in upstream:
                            yield "data: " + json.dumps(item.chunk) + "\n\n"
                    yield "data: [DONE]\n\n"
                except Exception:
                    # Headers are already sent. Signal failure; never replay generated output.
                    yield 'data: {"error":{"type":"upstream_error","message":"Upstream stream interrupted"}}\n\n'

            return ClosingStream(
                events(),
                upstream,
                media_type="text/event-stream",
                headers={
                    **routing_headers(first.routing),
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        except NoEligibleModel as exc:
            return api_error(400, "invalid_request_error", str(exc))
        except ProviderError as exc:
            return provider_error(exc)
        except Exception:
            return api_error(502, "upstream_error", "The request could not be completed")
