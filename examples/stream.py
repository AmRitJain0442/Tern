"""Live streaming with explicit lifecycle management.

Run from the repository: uv run --extra cli --env-file .env python examples/stream.py
Requires a configured key and Cloud Run invoker access. Incurs live usage charges.
"""

import asyncio
import os
from contextlib import aclosing

from model_router.adapters import (
    ChatRequest,
    GcloudIDTokenProvider,
    LayaGPUClient,
    OpenRouterAdapter,
    OpenRouterClient,
    RoutingContext,
)
from model_router.adapters.laya import DEFAULT_ENDPOINT


async def main():
    async with (
        LayaGPUClient(
            os.environ.get("LAYA_ENDPOINT", DEFAULT_ENDPOINT),
            token_provider=GcloudIDTokenProvider(),  # On GCP, omit this to use workload identity.
        ) as laya,
        OpenRouterClient(os.environ["OPENROUTER_API_KEY"]) as provider,
    ):
        await laya.warmup()
        models = await provider.models(
            {
                os.environ.get(
                    "OPENROUTER_ECONOMY_MODEL", "google/gemini-2.5-flash-lite"
                ): "economy",
                os.environ.get("OPENROUTER_STRONG_MODEL", "google/gemini-2.5-pro"): "strong",
            }
        )
        router = OpenRouterAdapter(models, laya, provider)
        request = ChatRequest(
            messages=[{"role": "user", "content": "Explain idempotency in two sentences."}],
            max_tokens=4096,
        )
        # This generous bound is for the tiny fixed prompt, not arbitrary user payloads.
        context = RoutingContext(input_tokens=256, language="en", workload="chat")
        first = True
        async with aclosing(router.stream(request, context)) as stream:
            async for item in stream:
                if first:
                    print(f"Route: {item.routing.model} ({item.routing.reason})\n")
                    first = False
                for choice in item.chunk.get("choices", []):
                    print(choice.get("delta", {}).get("content") or "", end="", flush=True)
                if item.chunk.get("usage"):
                    print(f"\nUsage: {item.chunk['usage']}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
