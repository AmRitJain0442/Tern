# Offline outcome format

The evaluator consumes JSONL containing **paired actual model outcomes**, not intuitive difficulty labels. It makes no API calls. This synthetic row illustrates the schema and is not an observed result:

```json
{"id":"example-1","group":"conversation-1","split":"test","probability_economy":0.91,"economy_eligible":true,"quality_economy":1.0,"quality_strong":1.0,"cost_economy":0.001,"cost_strong":0.01,"router_cost":0.0001}
```

`economy_eligible` must include every preflight, context, runtime, timeout, and capability constraint. A high Laya probability cannot override it. Costs are USD per request, including each model's measured retries; router cost is separate. Quality is a normalized task rubric score. A value of 1 is not required to mean perfect general intelligence; document the rubric alongside the data.

Store sensitive paired outputs in `artifacts/private/` (Git-ignored). Publish only authorized aggregate results and synthetic fixtures. Save dataset revision, model IDs, generation settings, policy version, and judge/rubric version in a companion manifest. The evaluator cannot detect leaked splits on its own; dataset construction must group related prompts before splitting.

```powershell
uv run --no-sync python scripts/evaluate.py artifacts/private/test.jsonl --threshold 0.9 --output artifacts/evaluation.json
```

Pick the threshold on separate calibration data and freeze it before test. The report includes always-strong, economy-when-eligible, exact expected random routing at matched coverage, and an oracle quality upper bound. It includes router cost only for the learned policy. Confidence intervals resample independent groups; too few groups makes those intervals uninformative. This implementation does not yet provide a trained baseline or online calibration.
