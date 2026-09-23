"""Friendly local entry point. No credentials or network required for the demo."""

import argparse
import asyncio
import json
import os
import shutil
from contextlib import aclosing
from pathlib import Path
from urllib.parse import urlsplit

from model_router.adapters import (
    ChatRequest,
    GcloudIDTokenProvider,
    LayaGPUClient,
    NoEligibleModel,
    OpenRouterAdapter,
    OpenRouterClient,
    ProviderError,
    RoutingContext,
)
from model_router.adapters.laya import DEFAULT_ENDPOINT
from model_router.adapters.types import DecisionUnavailable

ECONOMY = "google/gemini-2.5-flash-lite"
STRONG = "google/gemini-2.5-pro"


def make_console(**kwargs):
    try:
        from rich.console import Console
        from rich.theme import Theme
    except ImportError:
        raise SystemExit("Install the CLI first: uv sync --extra cli") from None
    return Console(
        theme=Theme({"accent": "#e9985f", "muted": "#94a3ab", "good": "#9dd6ae"}), **kwargs
    )


def heading(console, subtitle):
    console.print()
    console.print("[accent bold]  TERN[/]  [muted]/  choose the right model[/]")
    console.print(f"  [muted]{subtitle}[/]")
    console.print()


def emit_json(console, data):
    # Console line wrapping must not insert literal newlines into JSON strings.
    console.print(json.dumps(data), markup=False, highlight=False, soft_wrap=True)


def show_demo(console, data):
    from rich.table import Table

    heading(console, "OFFLINE DEMO  ·  real adapter, synthetic responses")
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("REQUEST", style="white")
    table.add_column("ROUTE")
    table.add_column("WHY", style="muted")
    reasons = [
        "0.82 >= 0.70 threshold",
        "0.41 < 0.70 threshold",
        "tool capability required",
        "classifier unavailable",
    ]
    for row, reason in zip(data["rows"], reasons):
        style = "accent" if row["tier"] == "economy" else "good"
        table.add_row(row["prompt"], f"[{style}]{row['tier'].upper()}[/]", reason)
    console.print(table)
    console.print()
    console.print(
        "  [good]4 routes completed[/]  [muted]·  no API key  ·  no GPU  ·  no network[/]"
    )
    console.print("  [muted]Illustrative scores. Live routing defaults to the strong model.[/]")
    console.print()
    console.print(
        "  Next  [accent]tern init[/]  [muted]then[/]  [accent]tern doctor[/]"
    )
    console.print()


def init_config(path, console):
    content = (
        "# Keep this file private. Environment variables take precedence.\n"
        "OPENROUTER_API_KEY=\n"
        f"OPENROUTER_ECONOMY_MODEL={ECONOMY}\n"
        f"OPENROUTER_STRONG_MODEL={STRONG}\n"
        f"LAYA_ENDPOINT={DEFAULT_ENDPOINT}\n"
    )
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(content)
    except FileExistsError:
        console.print("[good]Configuration already exists; kept your values.[/]")
    else:
        console.print("[good]Created configuration.[/] Add your OpenRouter key to it.")
    console.print(
        "Next: [accent]tern doctor[/]. The default GPU endpoint requires Cloud Run invoker access."
    )


def local_checks(auth):
    endpoint = os.environ.get("LAYA_ENDPOINT", DEFAULT_ENDPOINT)
    url = urlsplit(endpoint)
    endpoint_ok = bool(
        url.scheme == "https"
        and url.hostname
        and not url.username
        and not url.password
        and not url.query
        and not url.fragment
        and url.path in ("", "/")
    )
    key_ok = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    auth_ok = auth == "google" or bool(shutil.which("gcloud.cmd") or shutil.which("gcloud"))
    return [
        (
            "OpenRouter credential",
            key_ok,
            "present (value hidden)" if key_ok else "add OPENROUTER_API_KEY to .env",
        ),
        (
            "GPU endpoint",
            endpoint_ok,
            "HTTPS origin configured" if endpoint_ok else "set LAYA_ENDPOINT to an HTTPS origin",
        ),
        (
            "Google authentication",
            auth_ok,
            "metadata / service-account mode; verified by --live"
            if auth == "google"
            else "gcloud available; run gcloud auth login"
            if auth_ok
            else "install gcloud or use --auth google",
        ),
    ]


def make_laya(args):
    return LayaGPUClient(
        os.environ.get("LAYA_ENDPOINT", DEFAULT_ENDPOINT),
        token_provider=GcloudIDTokenProvider() if args.auth == "gcloud" else None,
    )


async def doctor_live(args):
    async with OpenRouterClient(os.environ["OPENROUTER_API_KEY"]) as provider:
        await provider.check_credentials()
        await provider.models(assignments())
    async with make_laya(args) as laya:
        await laya.warmup()


def assignments():
    economy = os.environ.get("OPENROUTER_ECONOMY_MODEL", ECONOMY)
    strong = os.environ.get("OPENROUTER_STRONG_MODEL", STRONG)
    if economy == strong:
        raise ValueError("Economy and strong model IDs must differ")
    return {economy: "economy", strong: "strong"}


async def chat(args, console):
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ValueError("Set OPENROUTER_API_KEY in .env, then run tern doctor")
    if args.input_tokens is None and len(args.prompt.encode("utf-8")) > 4096:
        raise ValueError("For long prompts supply --input-tokens with a conservative token bound")
    thresholds = (
        {args.workload: args.experimental_threshold} if args.experimental_threshold else None
    )
    context = RoutingContext(
        input_tokens=args.input_tokens or 8192, language=args.language, workload=args.workload
    )
    request = ChatRequest(
        messages=[{"role": "user", "content": args.prompt}], max_tokens=args.max_tokens
    )
    async with make_laya(args) as laya, OpenRouterClient(key) as provider:
        if not args.json:
            heading(console, "LIVE  ·  private GPU routing + OpenRouter")
            console.print(
                "  [muted]Preparing the GPU service (cold startup can take about a minute)...[/]"
            )
        await laya.warmup()
        router = OpenRouterAdapter(
            await provider.models(assignments()), laya, provider, experimental_thresholds=thresholds
        )
        if args.stream:
            first = True
            async with aclosing(router.stream(request, context)) as chunks:
                async for item in chunks:
                    if first:
                        console.print(
                            f"\n  Route: {item.routing.model} ({item.routing.reason})\n",
                            markup=False,
                        )
                        first = False
                    for choice in item.chunk.get("choices", []):
                        content = choice.get("delta", {}).get("content")
                        if content:
                            console.print(content, end="", markup=False, highlight=False)
                        if choice.get("finish_reason") == "length":
                            console.print(
                                "\n[accent]Output limit reached. Increase --max-tokens for a complete answer.[/]"
                            )
            console.print()
        else:
            result = await router.complete(request, context)
            if args.json:
                emit_json(console, result.model_dump(mode="json"))
            else:
                console.print(
                    f"\n  Route: {result.routing.model} ({result.routing.reason})\n", markup=False
                )
                for choice in result.response["choices"]:
                    console.print(
                        choice.get("message", {}).get("content") or "(No text returned)",
                        markup=False,
                    )
                    if choice.get("finish_reason") == "length":
                        console.print(
                            "[accent]Output limit reached. Increase --max-tokens for a complete answer.[/]"
                        )


def parser():
    result = argparse.ArgumentParser(
        prog="tern", description="Choose the right model. Start with a free offline demo."
    )
    result.add_argument(
        "--env-file", type=Path, default=Path(".env"), help="local configuration (default: .env)"
    )
    commands = result.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="try four routes offline, without credentials")
    demo.add_argument("--json", action="store_true", help="emit machine-readable demo results")
    commands.add_parser("init", help="create .env without replacing existing values")
    doctor = commands.add_parser(
        "doctor", help="check local configuration without exposing credentials"
    )
    doctor.add_argument(
        "--live",
        action="store_true",
        help="also wake the GPU and verify the model catalog (GCP charges may apply)",
    )
    doctor.add_argument("--auth", choices=["gcloud", "google"], default="gcloud")
    live = commands.add_parser(
        "chat", help="route one prompt through your GPU service and OpenRouter (paid)"
    )
    live.add_argument("prompt", help="one text prompt; quote it in your shell")
    live.add_argument("--auth", choices=["gcloud", "google"], default="gcloud")
    live.add_argument("--language", default="en", help="trusted prompt language (default: en)")
    live.add_argument("--workload", choices=["chat", "coding", "business"], default="chat")
    live.add_argument(
        "--input-tokens",
        type=positive_int,
        help="conservative input token bound (default: 8192 for prompts <=4096 UTF-8 bytes)",
    )
    live.add_argument(
        "--max-tokens",
        type=positive_int,
        default=4096,
        help="output budget including reasoning (default: 4096)",
    )
    live.add_argument(
        "--experimental-threshold",
        type=threshold,
        help="explicit uncalibrated economy threshold in (0.5, 1]",
    )
    output = live.add_mutually_exclusive_group()
    output.add_argument("--stream", action="store_true")
    output.add_argument(
        "--json", action="store_true", help="include routing, usage and full response as JSON"
    )
    return result


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def threshold(value):
    number = float(value)
    if not 0.5 < number <= 1:
        raise argparse.ArgumentTypeError("must be in (0.5, 1]")
    return number


def main(argv=None, *, console=None):
    args = parser().parse_args(argv)
    console = console or make_console()
    try:
        if args.command == "demo":
            from model_router.demo import run_demo

            data = asyncio.run(run_demo())
            if args.json:
                emit_json(console, data)
            else:
                show_demo(console, data)
            return 0
        if args.command == "init":
            init_config(args.env_file, console)
            return 0
        from dotenv import load_dotenv

        load_dotenv(args.env_file, override=False)
        if args.command == "doctor":
            heading(console, "SETUP CHECK  ·  credential values are never printed")
            checks = local_checks(args.auth)
            for label, ok, note in checks:
                console.print(f"  {'[good]OK  [/]' if ok else '[accent]FIX [/]'} {label}: {note}")
            if not all(ok for _, ok, _ in checks):
                return 1
            if args.live:
                console.print(
                    "\n  [muted]Checking Cloud Run readiness and the OpenRouter model catalog...[/]"
                )
                asyncio.run(doctor_live(args))
                console.print("  [good]Live connectivity checks passed.[/]")
            else:
                console.print(
                    "\n  [muted]Local checks only. Run tern doctor --live to verify access.[/]"
                )
            return 0
        asyncio.run(chat(args, console))
        return 0
    except (ProviderError, DecisionUnavailable, NoEligibleModel, ValueError) as exc:
        # These messages are under our control or validation errors without request bodies.
        # Pydantic validation can echo user values, so only expose our plain ValueErrors.
        if type(exc) is ValueError or isinstance(
            exc, (ProviderError, DecisionUnavailable, NoEligibleModel)
        ):
            message = str(exc)
        else:
            message = "Invalid configuration. Run tern doctor and check your inputs."
        console.print(f"Error: {message}", style="red", markup=False)
        return 1
    except KeyboardInterrupt:
        console.print("\nCancelled.", style="muted")
        return 130
    except Exception:
        # HTTP/auth exceptions may carry sensitive headers or upstream response text.
        console.print(
            "Connection failed. Check your network, credentials and Cloud Run invoker access.",
            style="red",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
