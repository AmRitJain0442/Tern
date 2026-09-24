# Changelog

## Unreleased — 0.1.0 experimental

Initial release candidate; no stable API or production service-level guarantee is implied.

- Local Laya inference with a pinned model revision and persistent downloads; Docker CPU setup, native Apple Metal instructions, and an optional NVIDIA configuration.
- Conservative economy/strong routing with capability checks, shadow mode, explicit experimental thresholds, deadlines and fallback.
- A Chat Completions API with model alias `tern/auto`, optional caller authentication, streamed responses and visible routing metadata.
- OpenRouter and configurable compatible providers, including different providers per tier. Native vendor APIs need a separately configured translation gateway.
- Python adapter, CLI setup checks, a clearly labeled synthetic preview, and opt-in paid live demonstrations.
- Recorded CPU/GPU feasibility probes and live OpenRouter integration results, with limitations documented alongside measurements.
- MIT license for Tern, third-party notices, release checks and automated secret scanning.

See [the provider guide](docs/providers.md) for supported protocol fields and [the findings](docs/findings.md) for measured performance boundaries.
