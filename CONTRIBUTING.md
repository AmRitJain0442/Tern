# Contributing to Tern

Thanks for helping make routing easier to use and easier to evaluate. Small, focused changes are the easiest to review. Contributions do not require cloud credentials. Please follow the [community conduct](CODE_OF_CONDUCT.md).

## Local setup

```sh
git clone https://github.com/AmRitJain0442/tern.git
cd tern
uv sync --extra dev --extra cli --python 3.12
uv run tern demo
uv run pytest -q
uv run ruff check src tests scripts examples
uv run python scripts/check_release.py
```

## Where to work

| Area | Location |
|---|---|
| CLI and offline demo | `src/model_router/cli.py`, `src/model_router/demo.py` |
| OpenRouter adapter, auth and streaming | `src/model_router/adapters/` |
| GPU inference and decision service | `src/model_router/backend.py`, `src/model_router/app.py` |
| Deterministic routing policy | `src/model_router/policy.py` |
| Tests without live credentials | `tests/` |
| Research and integration documentation | `docs/` |
| Synthetic measured results | `artifacts/` |

## Before opening a pull request

- Explain the problem and the resulting behavior. Include a small reproduction for bugs.
- Run the checks above. Add meaningful tests when changing routing, authentication, eligibility or streaming behavior.
- Keep normal tests offline. Live smoke tests must be explicitly invoked and document their costs.
- Preserve capability checks and conservative fallback. Never silently drop history, tools or modalities to make a request fit.
- For benchmark changes, record the hardware, model revision, sample size and measurement boundaries. Keep synthetic examples clearly labeled.
- Keep API keys, identity tokens and private user traffic out of code, screenshots and artifacts. Generated JSON reports are ignored by default; add curated evidence only after reviewing it for sensitive content.

For documentation and presentation changes, check relative links and image alt text. Regenerate terminal captures with the [asset workflow](docs/branding.md) when CLI output changes.

Use an issue to discuss broader changes before investing in an implementation. Useful areas include workload evaluation, tokenizer integration, provider capability handling and a simpler application integration layer. Follow [SECURITY.md](SECURITY.md) for sensitive reports.

By submitting an original contribution, you agree to license it under the project's [MIT License](LICENSE). Preserve third-party attribution and do not submit material you do not have permission to share. Release maintainers should follow the [release procedure](docs/releasing.md).
