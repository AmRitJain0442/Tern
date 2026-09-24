# Releasing Tern

The first release is experimental. Use the version in `pyproject.toml`; do not claim universal provider compatibility, production savings, or a published PyPI package without separate evidence.

## Prepare the candidate

1. Review `CHANGELOG.md`, the README, setup commands, provider boundaries and measured results. Update only claims supported by tests or recorded experiments.
2. Keep `LICENSE`, package metadata and third-party notices consistent. Retain model license/notice files in downloads and containers.
3. Run the offline checks and build:

   ```sh
   uv sync --frozen --extra dev --extra cli --python 3.12
   uv run --no-sync ruff check src tests scripts examples
   uv run --no-sync pytest -q
   uv run --no-sync python scripts/check_release.py
   uv build
   uv run --no-sync python scripts/check_release.py --dist dist
   ```

4. Run Gitleaks with redaction against both full history and the checkout. CI uses the pinned, checksum-verified Gitleaks release in `secrets.yml`. Do not upload unredacted findings or logs.
5. Audit locked dependency versions against current advisories. VCS dependencies, including pinned Laya source, need a separate source review; a clean registry advisory scan does not assess their source code.
6. Review generated reports and assets for credentials, personal information and private endpoints. `.env`, local provider configuration, downloaded weights and unreviewed reports must remain excluded from Git, package files and build contexts.
7. Require successful **Checks** and **Secret scan** runs on the exact candidate commit. Do not rely on an older green run.

## GitHub publication

Changing a private repository to public exposes its existing history, issues and other repository surfaces. It is a separate maintainer action after the candidate review. A preparation branch or draft pull request does not publish the repository.

Before the visibility change, review existing issues, pull requests, workflow logs, release assets, branches and tags as well as Git objects. Rotate any real credential shared in a chat, ticket or past artifact; deleting text is not revocation. Non-secret infrastructure identifiers may remain in historical commits even when current benchmark files are redacted.

After the repository becomes public:

- Enable [private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository), and verify the link in `SECURITY.md` works for an external user. GitHub exposes this feature for public repositories.
- Enable GitHub secret scanning and push protection where available, and enable dependency alerts. The committed Gitleaks workflow provides a separate check.
- Protect `main`: require a pull request and successful candidate checks; block force pushes and deletion. Use a rule appropriate for the maintainer count, so a solo maintainer is not locked out by mandatory self-review.
- Confirm the About description, topics, documentation URL, license display and issue forms render correctly.
- Set the GitHub Actions fork policy to require approval for outside contributors. Do not add provider or GCP secrets to workflows that execute untrusted pull-request code.
- Publish a tagged GitHub prerelease only after the candidate is merged and its checks pass. Attach reviewed artifacts and explain experimental limitations. PyPI publication and container publication are separate release tasks.

## Useful boundaries

Tests and release checks do not call Laya or paid providers. A live smoke test requires an explicit invocation and its own credentials; costs and output limits must be stated. Native Metal, NVIDIA hosts and third-party providers should not be presented as live-verified unless that exact path has been tested.

See [security reporting](../SECURITY.md), [dependency attribution](../THIRD_PARTY_NOTICES.md), [operations](operations.md), and [provider compatibility](providers.md).
