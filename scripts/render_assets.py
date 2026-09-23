"""Capture actual CLI output as README screenshots. No inference requests.

uv run --extra cli --with playwright python scripts/render_assets.py
Uses an installed Chrome/Chromium browser; pass --browser for a different executable.
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from rich.terminal_theme import TerminalTheme
from rich.text import Text

from model_router.cli import make_console

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
THEME = TerminalTheme(
    (23, 27, 32),
    (232, 232, 221),
    [
        (23, 27, 32),
        (233, 126, 116),
        (157, 214, 174),
        (245, 181, 68),
        (138, 176, 200),
        (186, 156, 211),
        (151, 206, 209),
        (232, 232, 221),
    ],
)


def capture(command, stem, caption, browser):
    output = io.StringIO()
    console = make_console(
        file=output, record=True, width=108, force_terminal=True, color_system="truecolor",
        legacy_windows=False,
    )
    console.print("$ uv run model-router " + " ".join(command), style="accent")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from model_router.cli import main, make_console; "
            "raise SystemExit(main(sys.argv[1:], console=make_console(width=108, "
            "force_terminal=True, color_system='truecolor', no_color=False, legacy_windows=False)))",
            *command,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env={**os.environ, "COLUMNS": "108", "FORCE_COLOR": "1", "PYTHONIOENCODING": "utf-8"},
    )
    if result.returncode:
        raise RuntimeError(
            f"Screenshot command {command[0]} failed with status {result.returncode}"
        )
    console.print(Text.from_ansi(result.stdout), end="")
    plain = console.export_text(clear=False)
    terminal = console.export_html(inline_styles=True, code_format="{code}", theme=THEME)
    transcript = "\n".join(line.rstrip() for line in plain.splitlines()) + "\n"
    (ASSETS / f"{stem}.txt").write_text(transcript, encoding="utf-8")
    html = """<!doctype html><html><head><meta charset="utf-8"><style>
      * { box-sizing: border-box; }
      body { margin: 0; background: #101418; padding: 30px; color: #e8e8dd; }
      .frame { border: 1px solid #3a4248; border-radius: 13px; overflow: hidden;
        background: #171b20; box-shadow: 0 18px 50px #0003; }
      .bar { height: 50px; border-bottom: 1px solid #323a41; display: flex;
        align-items: center; padding: 0 24px; gap: 9px; font: 13px 'Consolas', monospace; }
      .dot { width: 9px; height: 9px; border-radius: 50%; background: #657078; }
      .dot:first-child { background: #f5b544; }
      .title { margin-left: 18px; color: #a6b3bb; }
      .tag { margin-left: auto; color: #a6b3bb; letter-spacing: 1px; }
      pre { margin: 0; padding: 24px 24px 18px; font: 16px/1.85 'Consolas', 'Liberation Mono', monospace;
        white-space: pre; font-variant-ligatures: none; }
      .caption { font: 12px 'Consolas', monospace; color: #859199; padding: 17px 2px 0;
        letter-spacing: 1px; }
    </style></head><body><main><div class="frame"><div class="bar">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span class="title">model-router / terminal</span><span class="tag">PYTHON CLI</span>
      </div><pre>TERMINAL</pre></div><div class="caption">CAPTION</div></main></body></html>"""
    page = browser.new_page(viewport={"width": 1170, "height": 750}, device_scale_factor=2)
    page.set_content(html.replace("TERMINAL", terminal).replace("CAPTION", caption))
    page.screenshot(path=str(ASSETS / f"{stem}.png"), full_page=True)
    # Crop by choosing a viewport matching layout, not by editing the resulting image.
    height = page.locator("body").evaluate("el => el.getBoundingClientRect().height")
    page.set_viewport_size({"width": 1170, "height": round(height)})
    page.screenshot(path=str(ASSETS / f"{stem}.png"), full_page=True)
    page.close()
    print(f"Saved {stem}.png and text transcript")


def find_browser():
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    return next((str(p) for p in candidates if p and Path(p).is_file()), None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", default=find_browser())
    args = parser.parse_args()
    if not args.browser:
        parser.error("Install Chrome or specify --browser /path/to/chromium")
    ASSETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.browser, headless=True)
        capture(
            ["demo"],
            "terminal-demo",
            "01 / OFFLINE DEMO   -   ACTUAL CLI OUTPUT, SYNTHETIC MODEL RESPONSES",
            browser,
        )
        capture(
            ["doctor"],
            "terminal-doctor",
            "02 / SETUP CHECK   -   ACTUAL LOCAL CHECKS, CREDENTIAL VALUES HIDDEN",
            browser,
        )
        browser.close()
