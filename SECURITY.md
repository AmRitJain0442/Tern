# Security reports

Report vulnerabilities to the maintainer, [AmRitJain0442](https://github.com/AmRitJain0442), through [GitHub private vulnerability reporting](https://github.com/AmRitJain0442/tern/security/advisories/new) when available. If the form is unavailable, open an issue titled **Private security contact requested**, without vulnerability details, credentials, exploit steps or sensitive prompt data; the maintainer will arrange a private channel. Existing collaborators may use their established private channel. Do not post a vulnerability report in an ordinary public issue.

Include the affected commit, a minimal synthetic reproduction, expected impact and any proposed fix. Use placeholders for API keys and identity tokens. The actively maintained branch is `main`; there is no supported stable release yet.

Cloud Run IAM protects the deployed GPU endpoint. The local development server binds to loopback. `TERN_API_KEY` optionally protects `/v1/chat/completions` and `/v1/models`; `/health` and `/v1/route` retain the existing network/IAM boundary. The adapter's private-processing and regional restrictions are described in the [integration guide](docs/adapter.md); configured providers are not automatically verified to satisfy those requirements.

Compose publishes the local service only on `127.0.0.1`; the native `tern serve` command also binds to loopback. A public deployment needs TLS, access controls and appropriate spending/rate limits beyond this local setup. Local classifier clients send no Google credentials and bypass environment proxies. Remote classifier clients continue to require HTTPS and authentication. Downloaded weights and reports live in Docker volumes; `.env` is excluded from the build context.

Provider URLs and credentials are controlled by server configuration, never caller payloads. Keys are read from named environment variables and isolated per provider; incoming Tern bearer tokens are not forwarded. Redirects and URL credentials are rejected. Non-loopback HTTP requires explicit `allow_http` configuration for a trusted network. Keep configuration access restricted and never put keys directly in provider JSON. See the [API and provider guide](docs/providers.md).

## Handling an exposed credential

Revoke or rotate the credential at its issuer first, including when it was pasted into a chat or ticket. Deleting a file, comment or commit does not invalidate a key. Inspect Git history, build artifacts and logs before publication. Coordinate any necessary history cleanup with the maintainer rather than force-pushing shared branches. Secret scanners are useful checks, not a guarantee that every possible secret has been recognized.
