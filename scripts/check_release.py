"""Offline release checks for metadata, local documentation links and package boundaries."""

import argparse
import json
import re
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", "CONTRIBUTING.md",
    "SECURITY.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md", ".env.example",
    ".github/CODEOWNERS", ".github/workflows/secrets.yml",
)


def unsafe_path(name):
    parts = Path(name).parts
    base = Path(name).name.lower()
    return (
        any(p in {".env", ".research", ".venv", "models", "local-results", "private"} for p in parts)
        or (base.startswith(".env.") and base != ".env.example")
        or base == "providers.json"
        or base.endswith((".pem", ".key", ".p12", ".pfx", ".safetensors"))
        or base.startswith(("credentials", "service-account"))
    )


def check_sources():
    problems = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            problems.append(f"Missing release file: {name}")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    for field in ("name", "version", "description", "license", "authors", "maintainers", "urls"):
        if not project.get(field):
            problems.append(f"Missing package metadata: {field}")
    if project.get("license") != "MIT":
        problems.append("Package license must match the approved MIT license")
    if project.get("urls", {}).get("Repository") != "https://github.com/AmRitJain0442/tern":
        problems.append("Package repository URL is incorrect")

    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in filter(None, tracked):
        if unsafe_path(name):
            problems.append(f"Sensitive/local path is tracked: {name}")

    # Check files, not remote availability; network/model calls do not belong in this check.
    docs = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")]
    link_pattern = r'!?\[[^\]\n]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)'
    html_pattern = r'(?:src|href|srcset)="([^" ]+)"'
    for path in docs:
        content = path.read_text(encoding="utf-8")
        for target in re.findall(link_pattern, content) + re.findall(html_pattern, content):
            parsed = urlsplit(target.strip("<>"))
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            linked = (path.parent / unquote(parsed.path)).resolve()
            if not linked.exists():
                problems.append(f"Broken local link in {path.relative_to(ROOT)}: {target}")

    for path in (ROOT / "config").glob("*.example.json"):
        from model_router.providers import ProviderSettings

        ProviderSettings.model_validate_json(path.read_text(encoding="utf-8"))
    for path in (ROOT / "artifacts").glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    return problems


def check_distributions(directory):
    problems = []
    wheels = sorted(directory.glob("*.whl"))
    sdists = sorted(directory.glob("*.tar.gz"))
    if not wheels or not sdists:
        return ["Expected both a wheel and source distribution"]
    for archive in wheels + sdists:
        if archive.suffix == ".whl":
            with zipfile.ZipFile(archive) as source:
                names = source.namelist()
                metadata = source.read(next(n for n in names if n.endswith("/METADATA"))).decode()
                if "License-Expression: MIT" not in metadata:
                    problems.append(f"Wheel is missing MIT license metadata: {archive.name}")
        else:
            with tarfile.open(archive) as source:
                names = source.getnames()
        for name in names:
            if unsafe_path(name):
                problems.append(f"Local/private content in {archive.name}: {name}")
        if not any(Path(name).name == "LICENSE" for name in names):
            problems.append(f"License missing from {archive.name}")
        if not any(Path(name).name == "THIRD_PARTY_NOTICES.md" for name in names):
            problems.append(f"Third-party notices missing from {archive.name}")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path)
    args = parser.parse_args()
    problems = check_sources()
    if args.dist:
        problems.extend(check_distributions(args.dist))
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print("Release metadata, local links, examples and file boundaries passed.")


if __name__ == "__main__":
    main()
