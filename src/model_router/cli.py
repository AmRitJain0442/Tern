"""Friendly local entry point. No credentials or network required for the demo."""

import argparse
import asyncio
import json
import os
import platform
import shutil
from contextlib import aclosing
from pathlib import Path

from model_router.adapters import (
    ChatRequest,
    LayaGPUClient,
    NoEligibleModel,
    OpenRouterAdapter,
    OpenRouterClient,
    ProviderError,
    RoutingContext,
)
from model_router.adapters.laya import LOCAL_ENDPOINT
from model_router.adapters.types import DecisionUnavailable
from model_router.connection import connection_settings
from model_router.policy import RouteRequest

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
    console.print("[accent bold]  TERN[/]  [muted]/  small router. clear decisions.[/]")
    console.print(f"  [muted]{subtitle}[/]")
    console.print()


def emit_json(console, data):
    # Console line wrapping must not insert literal newlines into JSON strings.
    console.print(json.dumps(data), markup=False, highlight=False, soft_wrap=True)


def show_demo(console, data, *, show_all=False):
    from rich.table import Table

    heading(console, "OFFLINE DEMO  ·  real adapter, synthetic responses")
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("REQUEST" if show_all else "SCENARIO", style="white")
    table.add_column("#" if show_all else "COUNT", justify="right")
    table.add_column("TRUE_TAG", no_wrap=True)
    table.add_column("OUTPUT_TAG", no_wrap=True)
    table.add_column("WHY", style="muted")
    reasons = {
        "capability_or_risk_constraint": "tool capability required",
        "router_http_503": "classifier unavailable",
    }
    labels = {
        "rewrites": "Polite rewrites",
        "coding": "Coding tasks",
        "tools": "Weather tool requests",
        "outages": "Classifier outages",
    }
    rows = (
        data["rows"]
        if show_all
        else [
            next(row for row in data["rows"] if row["category"] == category)
            for category in data["summary"]["categories"]
        ]
    )
    for row in rows:
        reason = reasons.get(row["reason"], row["reason"])
        if row["probability"] is not None:
            comparison = ">=" if row["tier"] == "economy" else "<"
            reason = f"{row['probability']:.2f} {comparison} 0.70 threshold"
        style = "accent" if row["tier"] == "economy" else "good"
        table.add_row(
            row["prompt"] if show_all else labels[row["category"]],
            str(row["id"] if show_all else data["summary"]["categories"][row["category"]]),
            row["true_tag"].upper(),
            f"[{style}]{row['tier'].upper()}[/]",
            reason,
        )
    console.print(table)
    console.print()
    console.print(
        f"  [good]{data['summary']['total_requests']} requests completed[/]  "
        f"[accent]{data['summary']['routes'].get('economy', 0)} economy[/]  "
        f"[good]{data['summary']['routes'].get('strong', 0)} strong[/]"
    )
    console.print("  [muted]No API key  ·  no GPU  ·  no network[/]")
    console.print("  [muted]Illustrative scores. Live routing defaults to the strong model.[/]")
    console.print("  [muted]TRUE_TAG: fixture expectation, not measured ground truth.[/]")
    if not show_all:
        console.print(
            "  [muted]Every request:[/] [accent]tern demo --all[/]  [muted]JSON:[/] [accent]tern demo --json[/]"
        )
    console.print()
    console.print("  Next  [accent]tern init[/]  [muted]then[/]  [accent]tern doctor[/]")
    console.print()


def show_results(console, report):
    from rich.table import Table

    from model_router.live_demo import output_tag

    heading(console, "SAVED RUN / no API requests")
    table = Table(box=None, padding=(0, 1))
    for name in ("ID", "CATEGORY", "TRUE_TAG", "OUTPUT_TAG", "STATUS"):
        table.add_column(name, no_wrap=True)
    for row in report["rows"]:
        table.add_row(
            str(row["id"]),
            row["category"],
            row.get("true_tag") or "unknown",
            row.get("output_tag") or output_tag(row, report.get("models", [])) or "unknown",
            row["status"],
        )
    console.print(table)
    console.print(
        "TRUE_TAG: fixture expectation, not measured ground truth. Older unlabeled runs: unknown."
    )


def init_config(path, console):
    content = (
        "# Keep this file private. Environment variables take precedence.\n"
        "OPENROUTER_API_KEY=\n"
        f"OPENROUTER_ECONOMY_MODEL={ECONOMY}\n"
        f"OPENROUTER_STRONG_MODEL={STRONG}\n"
        f"LAYA_ENDPOINT={LOCAL_ENDPOINT}\n"
        "LAYA_AUTH=auto\n"
    )
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(content)
    except FileExistsError:
        console.print("[good]Configuration already exists; kept your values.[/]")
    else:
        console.print("[good]Created configuration.[/] Add your OpenRouter key to it.")
    console.print(
        "Next: [accent]tern doctor[/]. Start local Laya with [accent]docker compose up --build --wait[/]."
    )


def local_checks(auth):
    _, auth, _ = connection_settings(auth)
    key_ok = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    auth_ok = auth in {"local", "google"} or bool(
        shutil.which("gcloud.cmd") or shutil.which("gcloud")
    )
    return [
        (
            "OpenRouter credential",
            True,
            "present (value hidden)" if key_ok else "optional; add OPENROUTER_API_KEY for chat",
        ),
        (
            "Laya endpoint",
            True,
            "local loopback configured" if auth == "local" else "HTTPS origin configured",
        ),
        (
            "Authentication",
            auth_ok,
            "local; no Google account needed"
            if auth == "local"
            else "metadata / service-account mode; verified by --live"
            if auth == "google"
            else "gcloud available; run gcloud auth login"
            if auth_ok
            else "install gcloud or use --auth google",
        ),
    ]


def make_laya(args):
    endpoint, _, options = connection_settings(args.auth)
    return LayaGPUClient(endpoint, **options)


async def doctor_live(args):
    async with make_laya(args) as laya:
        await laya.warmup()
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        async with OpenRouterClient(key) as provider:
            await provider.check_credentials()
            await provider.models(assignments())


async def route_prompt(args, console):
    async with make_laya(args) as laya:
        await laya.warmup()
        result = await laya.decide(RouteRequest(prompt=args.prompt, language=args.language))
    emit_json(console, result.model_dump())


def serve(args, console):
    """First startup downloads the pinned checkpoint; later starts reuse the HF cache."""
    if not 1 <= args.port <= 65535:
        raise ValueError("Port must be 1..65535")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    try:
        import laya_mlx  # noqa: F401
        import mlx.core  # noqa: F401
    except ImportError:
        raise ValueError(
            "MLX is not installed. Use docker compose up --build --wait, or "
            "uv run --extra cli --extra mlx-metal tern serve on Apple Silicon."
        ) from None
    import uvicorn

    device = args.device
    if device == "auto":
        device = "gpu" if platform.system() == "Darwin" else "cpu"
    os.environ["MLX_DEVICE"] = device
    os.environ["MLX_DTYPE"] = "float32" if device == "cpu" else "float16"
    os.environ.setdefault("MAX_INFERENCE_MS", "30000" if device == "cpu" else "2000")
    console.print("Loading pinned Laya weights; the first run downloads the model.")
    console.print(
        "Readiness requires a real forward pass. Keep this terminal open; Ctrl+C stops Laya."
    )
    uvicorn.run("model_router.app:app", host="127.0.0.1", port=args.port, access_log=False)


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
            heading(console, "LIVE  ·  Laya routing + OpenRouter")
            console.print("  [muted]Checking Laya readiness...[/]")
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
        prog="tern", description="Small router. Clear decisions. Start with a free offline demo."
    )
    result.add_argument(
        "--env-file", type=Path, default=Path(".env"), help="local configuration (default: .env)"
    )
    commands = result.add_subparsers(dest="command", required=True)
    server = commands.add_parser("serve", help="download/load real Laya and serve locally")
    server.add_argument("--device", choices=["auto", "cpu", "gpu"], default="auto")
    server.add_argument("--port", type=positive_int, default=8080)
    route = commands.add_parser(
        "route", help="classify a prompt with real Laya; no OpenRouter key needed"
    )
    route.add_argument("prompt")
    route.add_argument("--language", default="en")
    route.add_argument("--auth", choices=["auto", "local", "gcloud", "google"], default="auto")
    results = commands.add_parser("results", help="view saved live-run tags without API calls")
    results.add_argument("path", type=Path, help="saved live-run JSON file")
    demo = commands.add_parser(
        "demo", help="route 100 requests offline, or use --live for real GPU/OpenRouter calls"
    )
    demo.add_argument(
        "--live", action="store_true", help="make 100 paid requests through GCP and OpenRouter"
    )
    demo.add_argument(
        "--output", type=Path, help="live results file (default: timestamped file in artifacts/)"
    )
    demo.add_argument(
        "--max-tokens",
        type=positive_int,
        default=2048,
        help="live output cap per attempt (default: 2048)",
    )
    demo.add_argument(
        "--concurrency",
        type=positive_int,
        default=4,
        help="live generation concurrency, 1..8 (default: 4)",
    )
    demo.add_argument(
        "--experimental-threshold",
        type=threshold,
        help="explicit live economy threshold; default respects shadow mode",
    )
    demo.add_argument("--auth", choices=["auto", "local", "gcloud", "google"], default="auto")
    demo_output = demo.add_mutually_exclusive_group()
    demo_output.add_argument(
        "--json", action="store_true", help="emit all 100 results and summary as JSON"
    )
    demo_output.add_argument(
        "--all", action="store_true", help="show every request instead of the compact summary"
    )
    commands.add_parser("init", help="create .env without replacing existing values")
    doctor = commands.add_parser(
        "doctor", help="check local configuration without exposing credentials"
    )
    doctor.add_argument(
        "--live",
        action="store_true",
        help="also wake the GPU and verify the model catalog (GCP charges may apply)",
    )
    doctor.add_argument("--auth", choices=["auto", "local", "gcloud", "google"], default="auto")
    live = commands.add_parser(
        "chat", help="route one prompt through your GPU service and OpenRouter (paid)"
    )
    live.add_argument("prompt", help="one text prompt; quote it in your shell")
    live.add_argument("--auth", choices=["auto", "local", "gcloud", "google"], default="auto")
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
        if args.command == "serve":
            serve(args, console)
            return 0
        if args.command == "results":
            try:
                report = json.loads(args.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise ValueError(
                    "Cannot read results; supply an existing live-run JSON file"
                ) from None
            if not isinstance(report, dict) or not isinstance(report.get("rows"), list):
                raise ValueError("Results must contain a rows list")
            show_results(console, report)
            return 0
        if args.command == "demo":
            if args.live:
                from dotenv import load_dotenv

                from model_router.live_demo import run_live_demo

                load_dotenv(args.env_file, override=False)
                progress_console = make_console(stderr=True) if args.json else console
                report, path = asyncio.run(
                    run_live_demo(
                        output=args.output,
                        max_tokens=args.max_tokens,
                        concurrency=args.concurrency,
                        experimental_threshold=args.experimental_threshold,
                        auth=args.auth,
                        progress=lambda text: progress_console.print(
                            text, markup=False, highlight=False
                        ),
                    )
                )
                emit_json(console, report if args.json else report["summary"])
                if not args.json:
                    console.print(f"Results saved: {path}", markup=False)
                return 1 if report["summary"]["failed"] else 0
            from model_router.demo import run_demo

            data = asyncio.run(run_demo())
            if args.json:
                emit_json(console, data)
            else:
                show_demo(console, data, show_all=args.all)
            return 0
        if args.command == "init":
            init_config(args.env_file, console)
            return 0
        from dotenv import load_dotenv

        load_dotenv(args.env_file, override=False)
        if args.command == "route":
            asyncio.run(route_prompt(args, console))
            return 0
        if args.command == "doctor":
            heading(console, "SETUP CHECK  ·  credential values are never printed")
            checks = local_checks(args.auth)
            for label, ok, note in checks:
                console.print(f"  {'[good]OK  [/]' if ok else '[accent]FIX [/]'} {label}: {note}")
            if not all(ok for _, ok, _ in checks):
                return 1
            if args.live:
                console.print(
                    "\n  [muted]Checking Laya; checking OpenRouter only if a key is configured...[/]"
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
            "Connection failed. Run tern doctor; check that Laya is running and credentials are valid.",
            style="red",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
