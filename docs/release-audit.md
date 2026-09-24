# Open-source release preparation — 2026-09-24

This audit started from commit `4ec01e196e0a8d3e24cd4bd74f66c0f4369d718d`. The release-preparation branch adds licensing, safe publication defaults, documentation corrections and continuous release checks. It does not publish the repository or certify the application as vulnerability-free.

## Checks completed locally

| Check | Result and scope |
|---|---|
| Git history secret scan | No credential findings across all 38 baseline commits and 215 historical blobs; checked again with Gitleaks 8.30.1 and the project's OpenRouter rule |
| Known local credential comparison | No match in historical Git blobs; values were kept in process memory and were not printed |
| Current source and built package scan | No credential findings in the candidate snapshot or expanded wheel/source-distribution contents |
| Independent scanner | One unverified URI finding: the intentionally invalid `user:password@localhost` URL in a security rejection test; no real credential identified |
| GitHub surfaces | All 36 existing completed workflow logs scanned without credential findings; there were no issues, comments, releases, tags or uploaded workflow artifacts at audit time |
| Dependency advisories | No known advisories for 56 locked registry package/version pairs, including both platform-dependent NumPy versions; pinned VCS source is outside this registry advisory check |
| Tests | 108 passed; one upstream Starlette/httpx deprecation warning |
| Static checks | Ruff, frozen lock consistency, release metadata, provider examples, JSON evidence and local documentation links passed |
| Packaging | Wheel and source distribution built; MIT/license notices included; private/local paths excluded |
| Compose | Default and NVIDIA override configurations validated with the example environment, without using production credentials |

These are point-in-time results. The **Checks** and **Secret scan** workflows must pass on the final candidate commit. A clean scan does not prove that every possible secret or vulnerability has been recognized.

## Corrections

- Added the owner-approved MIT license, package author/maintainer/license metadata, third-party attribution, changelog and community/release guidance.
- Added pinned-action CI, full-history and checkout secret scans, package-boundary checks, and Dependabot configuration.
- Removed maintainer-project deployment defaults and updated cloud examples to require the reader's project.
- Redacted private cloud identifiers from current published benchmark metadata, while preserving measurements and recording the redacted fields. Historical non-secret infrastructure identifiers remain in Git history.
- Ignored new generated JSON reports and common credential-file formats; retained explicitly curated evidence.
- Updated public-facing installation/contribution wording and documented the current API/provider boundaries.
- Updated GitHub's About description, documentation link and topics, and enabled dependency alerts.

## Remaining launch actions

1. Confirm that any credentials exposed outside Git have been rotated at their issuer. This repository audit does not establish revocation status. Keep credentials in an ignored environment file or secret manager, not in issues or chat.
2. Review and merge the release-preparation branch after its GitHub checks pass. The audit and package changes are isolated from the main working tree.
3. Have the owner explicitly approve public visibility. Then enable private vulnerability reporting, secret scanning/push protection where available, and branch protection; verify the external reporting path. These public-release steps are detailed in [the release procedure](releasing.md).
4. Tag and publish an experimental GitHub prerelease only after those steps. No PyPI or container-registry publication was performed as part of this preparation.
