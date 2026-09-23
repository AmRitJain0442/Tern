# Security reports

Report vulnerabilities privately to the repository owner, **AmRitJain0442**, through your existing private collaboration channel. If GitHub private vulnerability reporting is enabled for this repository, use **Security → Report a vulnerability**. Do not include credentials or sensitive prompt data in an ordinary issue.

Include the affected commit, a minimal synthetic reproduction, expected impact and any proposed fix. Use placeholders for API keys and identity tokens. The actively maintained branch is `main`; there is no supported stable release yet.

Cloud Run IAM protects the deployed GPU endpoint. The local development server has no application authentication and should bind to loopback. The adapter's private-processing and regional restrictions are described in the [integration guide](docs/adapter.md); generic OpenRouter routing is not configured to satisfy those requirements.

Compose publishes the local service only on `127.0.0.1`; the native `tern serve` command also binds to loopback. Do not expose this unauthenticated endpoint to a public interface. Local clients send no Google credentials and bypass environment proxies. Remote clients continue to require HTTPS and authentication. Downloaded weights and reports live in Docker volumes; `.env` is excluded from the build context.
