"""Deterministic, credential-free tour through the real adapter with local transports."""

import json

import httpx

from model_router.adapters import (
    ChatRequest,
    LayaGPUClient,
    ModelSpec,
    OpenRouterAdapter,
    OpenRouterClient,
    RoutingContext,
)
from model_router.backend import MODEL_REVISION


async def run_demo():
    """Synthetic probabilities and completions; never contacts GCP or OpenRouter."""
    responses = {
        "Rewrite this politely: send the report.": (0.82, "Could you please send the report?"),
        "Design a thread-safe LRU cache.": (0.41, "Use a lock around lookup, update and eviction."),
        "Look up the weather in Paris.": (None, "Tool requests stay on the strong model."),
        "Demonstrate a classifier outage.": (None, "The strong model handles classifier failures."),
    }

    async def token():
        return "offline-demo"

    def classify(request):
        prompt = json.loads(request.content)["prompt"]
        if prompt == "Demonstrate a classifier outage.":
            return httpx.Response(503)
        probability, _ = responses[prompt]
        return httpx.Response(
            200,
            json={
                "selected_tier": "strong",
                "proposed_tier": "strong",
                "mode": "shadow",
                "reason": "shadow_proposal",
                "probability_economy": probability,
                "model_revision": MODEL_REVISION,
            },
        )

    def complete(request):
        body = json.loads(request.content)
        _, answer = responses[body["messages"][0]["content"]]
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "choices": [
                    {"message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}
                ],
            },
        )

    models = [
        ModelSpec(
            id=f"demo/{tier}",
            tier=tier,
            context_length=8192,
            max_output_tokens=1024,
            supported_parameters={"max_tokens", "tools"},
        )
        for tier in ("economy", "strong")
    ]
    async with LayaGPUClient(token_provider=token, transport=httpx.MockTransport(classify)) as laya:
        async with OpenRouterClient("offline-demo", transport=httpx.MockTransport(complete)) as api:
            router = OpenRouterAdapter(
                models, laya, api, experimental_thresholds={"chat": 0.7, "coding": 0.7}
            )
            rows = []
            for index, prompt in enumerate(responses):
                request = ChatRequest(
                    messages=[{"role": "user", "content": prompt}], max_tokens=256
                )
                if index == 2:
                    request.tools = [
                        {
                            "type": "function",
                            "function": {"name": "weather", "parameters": {"type": "object"}},
                        }
                    ]
                result = await router.complete(
                    request,
                    RoutingContext(
                        input_tokens=256,
                        language="en",
                        workload="coding" if index == 1 else "chat",
                    ),
                )
                rows.append(
                    {
                        "prompt": prompt,
                        "tier": result.routing.tier,
                        "reason": result.routing.reason,
                        "probability": result.routing.probability_economy,
                        "answer": result.response["choices"][0]["message"]["content"],
                    }
                )
            return {"mode": "offline_demo", "synthetic": True, "network_requests": 0, "rows": rows}
