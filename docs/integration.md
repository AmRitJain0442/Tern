# Connecting the decision service to an LLM gateway

The current service does not generate completions. Its contract is `POST /v1/route`, with tier IDs `economy` and `strong`. The deployed mode is shadow: the selected tier stays strong; the proposed tier is research telemetry.

## Caller responsibilities

1. Authenticate the user and validate the request before sending anything to the classifier.
2. Enforce privacy/region requirements **before transmitting prompt text to this GCP endpoint**. A classifier-side privacy flag is not a substitute for this check.
3. Build an eligible model pool from actual context limits, tools, modalities, structured-output support, health, and budget. Keep full conversation state at the gateway.
4. Map eligible concrete model IDs into the two tiers. An absent valid strong route must produce an explicit failure or caller-approved alternative.
5. Call the decision service with a short caller deadline. Use an eligible conservative fallback on timeout, busy, invalid JSON, or error. Do not retry classification blindly.
6. Use `selected_tier` for dispatch, and log `proposed_tier` only for evaluation. Respect a null selection. A Laya probability must never override eligibility.
7. Execute generation through a provider gateway that owns bounded retries, streaming, usage accounting, and secrets.

Example request:

```json
{
  "prompt": "Rewrite this politely: please send the invoice today.",
  "language": "en",
  "eligible_tiers": ["economy", "strong"],
  "requires_tools": false,
  "requires_vision": false,
  "has_conversation_history": false
}
```

Example shape, with illustrative values (not a recorded response):

```json
{
  "selected_tier": "strong",
  "proposed_tier": "economy",
  "reason": "shadow_proposal",
  "mode": "shadow",
  "policy_version": "binary-shadow-v1",
  "probability_economy": 0.94,
  "inference_ms": 25.0,
  "router_ms": 26.0,
  "input_tokens": 62,
  "model_revision": "20aed815fc6acde75733882e7ec0e3f28aeb9717"
}
```

Cloud callers should use their workload identity to obtain an ID token whose audience is the Cloud Run service URL, and need `roles/run.invoker` on that service. Local experiments use `gcloud auth print-identity-token`; do not copy a local user's token into production configuration. [Cloud Run service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service).

## Before enabling experimental dispatch

Freeze the actual candidate model IDs and evaluation rubric for each family in [workloads.md](workloads.md). Collect paired outcomes and choose a policy using [design.md](design.md). Setting `ROUTER_MODE=experimental` only changes dispatch semantics; it does not make the default threshold calibrated or establish model quality.

Conversation/history, long input, non-English text, tools, and vision currently bypass classification. To serve all workload families efficiently, add and evaluate the relevant routing representations and multilingual/capability paths. Do not mark history false just to force a request through the short-input experiment.
