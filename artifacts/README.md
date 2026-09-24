# Published evidence

These are curated results from synthetic prompts, local setup checks and explicit live integration runs. They are not private user traffic. Reports distinguish real inference/generations from synthetic previews; see the linked methodology in `docs/` before interpreting a result.

Private GCP project identifiers, registry project paths and service URLs have been redacted from published JSON. Each affected report lists the modified fields under `public_redaction`. Timings, probabilities, model revisions, image digests, provider responses, usage and costs remain unchanged. Redacted URLs are not callable endpoints.

New JSON files in this directory are ignored by Git to avoid accidentally publishing prompts, responses or configuration. Store private runs under `artifacts/private/`. To publish a curated report, review every field, scan it for credentials, document its methodology, and deliberately add only that reviewed file with `git add -f artifacts/your-reviewed-report.json`.

Do not replace real results with simulated values, remove inconvenient measurements, or relabel fixture expectations as answer-quality ground truth.
