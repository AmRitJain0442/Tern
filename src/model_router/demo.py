"""Deterministic, credential-free tour through the real adapter with local transports."""

import json
from collections import Counter

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

# Declared demo expectations, independent of classifier predictions. Not quality labels.
EXPECTED_TAGS = {
    "rewrites": "economy",
    "coding": "strong",
    "tools": "strong",
    "outages": "strong",
    "summaries": "economy",
}


def demo_cases():
    """100 distinct synthetic prompts, interleaved to demonstrate isolated outages."""
    documents = [
        "report",
        "invoice",
        "proposal",
        "meeting notes",
        "project brief",
        "budget",
        "contract",
        "release notes",
        "roadmap",
        "design mockups",
        "test results",
        "sales forecast",
        "onboarding guide",
        "status update",
        "timeline",
        "feedback",
        "presentation",
        "purchase order",
        "requirements",
        "support summary",
        "expense receipt",
        "team schedule",
        "audit checklist",
        "training material",
        "delivery plan",
    ]
    coding_tasks = [
        "Design a thread-safe LRU cache.",
        "Implement an idempotent payment handler.",
        "Explain deadlock prevention in a worker pool.",
        "Design a distributed rate limiter.",
        "Implement cursor-based pagination.",
        "Diagnose a database connection leak.",
        "Design a transactional outbox.",
        "Explain isolation levels for concurrent writes.",
        "Implement exponential backoff with jitter.",
        "Design a resumable file upload protocol.",
        "Debug a race between cancellation and completion.",
        "Implement a bounded asynchronous queue.",
        "Design cache invalidation for inventory updates.",
        "Explain safe retries after a partial write.",
        "Implement dependency ordering for a build graph.",
        "Design a zero-downtime database migration.",
        "Diagnose a memory leak in an event subscriber.",
        "Implement a streaming JSON parser.",
        "Design leader election for scheduled jobs.",
        "Explain consistency during a network partition.",
        "Implement deduplication for webhook deliveries.",
        "Design backpressure for an event pipeline.",
        "Debug an authorization cache invalidation bug.",
        "Implement safe shutdown for background tasks.",
        "Design recovery from a failed distributed transaction.",
    ]
    cities = [
        "Paris",
        "London",
        "Tokyo",
        "Delhi",
        "Berlin",
        "Sydney",
        "Toronto",
        "Nairobi",
        "Lisbon",
        "Seoul",
        "Mumbai",
        "Oslo",
        "Lima",
        "Cairo",
        "Madrid",
        "Rome",
        "Bangkok",
        "Jakarta",
        "Dublin",
        "Helsinki",
        "Prague",
        "Vienna",
        "Boston",
        "Cape Town",
        "Singapore",
    ]
    cases = []
    for document, task, city in zip(documents, coding_tasks, cities, strict=True):
        # Each successful inference resets the failure count before the next isolated outage.
        cases.extend(
            [
                {
                    "category": "rewrites",
                    "workload": "business",
                    "probability": 0.82,
                    "prompt": f"Rewrite this politely: send the {document}.",
                    "answer": f"Could you please send the {document}?",
                },
                {
                    "category": "coding",
                    "workload": "coding",
                    "probability": 0.41,
                    "prompt": task,
                    "answer": f"Synthetic strong-model response for: {task}",
                },
                {
                    "category": "tools",
                    "workload": "chat",
                    "probability": None,
                    "prompt": f"Look up the weather in {city}.",
                    "answer": f"Synthetic tool-capable response for {city}; no weather data fetched.",
                },
                {
                    "category": "outages",
                    "workload": "business",
                    "probability": None,
                    "prompt": f"Summarize the {document} while the classifier is unavailable.",
                    "answer": "Synthetic fallback response; the strong model handles this request.",
                },
            ]
        )
    return cases


async def run_demo():
    """Synthetic probabilities and completions; never contacts GCP or OpenRouter."""
    cases = demo_cases()
    responses = {case["prompt"]: case for case in cases}

    async def token():
        return "offline-demo"

    def classify(request):
        prompt = json.loads(request.content)["prompt"]
        case = responses[prompt]
        if case["category"] == "outages":
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "selected_tier": "strong",
                "proposed_tier": "strong",
                "mode": "shadow",
                "reason": "shadow_proposal",
                "probability_economy": case["probability"],
                "model_revision": MODEL_REVISION,
            },
        )

    def complete(request):
        body = json.loads(request.content)
        answer = responses[body["messages"][0]["content"]]["answer"]
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
                models,
                laya,
                api,
                experimental_thresholds={"chat": 0.7, "coding": 0.7, "business": 0.7},
            )
            rows = []
            for index, case in enumerate(cases, start=1):
                prompt = case["prompt"]
                request = ChatRequest(
                    messages=[{"role": "user", "content": prompt}], max_tokens=256
                )
                if case["category"] == "tools":
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
                        workload=case["workload"],
                    ),
                )
                rows.append(
                    {
                        "id": index,
                        "category": case["category"],
                        "workload": case["workload"],
                        "prompt": prompt,
                        "tier": result.routing.tier,
                        "true_tag": EXPECTED_TAGS[case["category"]],
                        "true_tag_source": "fixture_expectation",
                        "output_tag": result.routing.tier,
                        "reason": result.routing.reason,
                        "probability": result.routing.probability_economy,
                        "answer": result.response["choices"][0]["message"]["content"],
                    }
                )
            return {
                "mode": "offline_demo",
                "synthetic": True,
                "network_requests": 0,
                "summary": {
                    "total_requests": len(rows),
                    "routes": dict(Counter(row["tier"] for row in rows)),
                    "categories": dict(Counter(row["category"] for row in rows)),
                },
                "rows": rows,
            }
