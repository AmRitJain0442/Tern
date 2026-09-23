# One router across chat, coding/agents, and business workflows

The user wants all three workload families. Share an inference service and provider gateway, but keep task-specific eligibility, evaluation, and policy versions. A universal scalar difficulty score is only a baseline.

| Family | Candidate routes | Main quality evidence | Signals beyond user text |
|---|---|---|---|
| General chat/API | Economy generalist, strong generalist, long-context route | Blinded rubric, factual checks, instruction following | Language, freshness/tools, conversation length, response format |
| Coding | Economy code edits/explanations, stronger reasoning/code model | Tests pass, build/static checks, patch correctness | Repository scope, files touched, tool availability, required execution |
| Agent tasks | Cheap routine step, strong planning/debugging, escalation | Whole task success and total spend | Tool failures, repeated attempts, state changes, unresolved blockers |
| Support/business | Economy extraction/rewriting, specialist classification, strong exception handling | Schema validity, field accuracy, task correctness | Workflow ID, source format, policy version, contractual constraints |

## Proposed hierarchy

1. Trusted caller specifies workflow family when known; this avoids a redundant task classifier.
2. Eligibility filter narrows the pool using capabilities and deployment health.
3. One Laya question proposes a tier within that pool.
4. A policy calibrated for that family accepts the cheaper route or abstains.
5. Task validators trigger a bounded escalation path where their accuracy is established.

If the caller cannot supply a family, compare one joint choice among a few stable task/tier combinations against a separate family classifier. Joint routing saves a pass but increases label complexity; separate routing makes errors compound. Measure both rather than assuming a hierarchy always wins.

## Experiments by family

**Chat/API:** stratify rewriting, summarization, extraction, factual QA, reasoning, multi-turn follow-ups, and requests needing fresh information. Include small models that already solve a high proportion of the workload, because that is where routing savings are plausible. Long context must be evaluated separately; the current endpoint conservatively bypasses history and overflow.

**Coding:** start with bounded edit/explain/test tasks whose outputs can be checked. Partition by repository/template before splitting data. Difficulty of a prompt's wording is a poor proxy for codebase complexity; supplied repository features or tool feedback may be more predictive. Track valid patches, regressions, execution time, and full token cost.

**Agents:** route whole episodes or stable phases. Compare always-strong, always-economy with bounded escalation, and Laya-informed selection. Charge every unsuccessful turn and tool call. Preserve state when escalating, but do not treat the failed model's reasoning as verified evidence. Keep ordinary retries distinct from escalation to another capability tier.

**Business:** separate deterministic extraction/formatting from policy interpretation. Laya may sometimes directly answer a bounded classification question and avoid a generative model entirely. That is a separate product feature requiring labeled classification accuracy; the prototype currently chooses a tier and does not replace generation with a classification response. Explicitly handle unsupported languages and missing information.

## Milestones

| Stage | Deliverable | Exit evidence |
|---|---|---|
| Feasibility | Pinned model, private GCP service, benchmark scripts | Real inference and authenticated requests |
| Routing pilot | Paired outcomes for a small pool in each family | Labels, cost accounting, reproducible baselines |
| Calibration | Per-family thresholds or a learned head | Held-out cost/quality curves with uncertainty |
| Integration | Tier mapping and gateway fallback | End-to-end provider tests, latency/cost limits |
| Controlled rollout | Shadow then small canary | Task quality maintained on real traffic |
| Optimization | Quantization, batching, caching, scheduling | Better measured total cost at the same quality |

Feasibility is the current implementation milestone. The other stages require real downstream candidate choices and representative paired outcomes. Hosting benchmarks do not complete those stages.
