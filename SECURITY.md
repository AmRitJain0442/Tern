# Security reports

Report vulnerabilities privately to the repository owner, **AmRitJain0442**, through your existing private collaboration channel. If GitHub private vulnerability reporting is enabled for this repository, use **Security → Report a vulnerability**. Do not include credentials or sensitive prompt data in an ordinary issue.

Include the affected commit, a minimal synthetic reproduction, expected impact and any proposed fix. Use placeholders for API keys and identity tokens. The actively maintained branch is `main`; there is no supported stable release yet.

Cloud Run IAM protects the deployed GPU endpoint. The local development server binds to loopback. `TERN_API_KEY` optionally protects `/v1/chat/completions` and `/v1/models`; `/health` and `/v1/route` retain the existing network/IAM boundary. The adapter's private-processing and regional restrictions are described in the [integration guide](docs/adapter.md); configured providers are not automatically verified to satisfy those requirements.

Compose publishes the local service only on `127.0.0.1`; the native `tern serve` command also binds to loopback. A public deployment needs TLS, access controls and appropriate spending/rate limits beyond this local setup. Local classifier clients send no Google credentials and bypass environment proxies. Remote classifier clients continue to require HTTPS and authentication. Downloaded weights and reports live in Docker volumes; `.env` is excluded from the build context.

Provider URLs and credentials are controlled by server configuration, never caller payloads. Keys are read from named environment variables and isolated per provider; incoming Tern bearer tokens are not forwarded. Redirects and URL credentials are rejected. Non-loopback HTTP requires explicit `allow_http` configuration for a trusted network. Keep configuration access restricted and never put keys directly in provider JSON. See the [API and provider guide](docs/providers.md).
