"""Chat Completions transport for configurable OpenAI-compatible endpoints."""

import math
from urllib.parse import urlsplit

import httpx

from model_router.adapters.openrouter import OpenRouterClient


class OpenAICompatibleClient(OpenRouterClient):
    """Reuse validated completions/SSE handling without OpenRouter-specific request fields."""

    def __init__(
        self,
        base_url,
        api_key=None,
        *,
        timeout=120.0,
        transport=None,
        allow_http=False,
        token_parameter="max_tokens",
        auth_header="Authorization",
    ):
        url = urlsplit(base_url)
        try:
            port = url.port
        except ValueError:
            raise ValueError("Invalid provider port") from None
        if (
            url.scheme not in {"https", "http"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or (port is not None and not 1 <= port <= 65535)
            or (
                url.scheme == "http"
                and not allow_http
                and url.hostname not in {"127.0.0.1", "localhost", "::1"}
            )
        ):
            raise ValueError(
                "Provider URL must use HTTPS; trusted private HTTP requires allow_http"
            )
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Provider timeout must be positive")
        if token_parameter not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("Invalid output token parameter")
        if auth_header not in {"Authorization", "api-key"}:
            raise ValueError("Unsupported authentication header")
        headers = {}
        if api_key:
            headers[auth_header] = (
                "Bearer " if auth_header == "Authorization" else ""
            ) + api_key.strip()
        self.timeout = timeout
        self.token_parameter = token_parameter
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            trust_env=url.scheme == "https",
        )

    def _body(self, model, request, stream):
        body = {**request.model_dump(exclude_none=True), "model": model, "stream": stream}
        if self.token_parameter == "max_completion_tokens":
            body["max_completion_tokens"] = body.pop("max_tokens")
        return body

    async def models(self, assignments):
        raise ValueError("Compatible endpoints require explicit model capabilities in Tern config")

    async def check_credentials(self):
        raise ValueError(
            "Use a completion to verify this provider; no universal credential endpoint exists"
        )
