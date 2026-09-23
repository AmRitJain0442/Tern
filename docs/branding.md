# Tern identity

**Tern — small router, clear decisions.**

A tern's flight gives the project its name and mark. Two angular wings meet at a junction, suggesting a choice of routes. The identity uses burnt orange with charcoal or ivory lettering. The logo and wordmarks have real alpha transparency: no rectangular banner, grid, or painted backdrop.

| Asset | File | Purpose |
|---|---|---|
| Standalone flight mark | [logo.png](assets/logo.png) | Transparent icon |
| Light-theme wordmark | [wordmark-light.png](assets/wordmark-light.png) | Orange mark and charcoal lettering |
| Dark-theme wordmark | [wordmark-dark.png](assets/wordmark-dark.png) | Orange mark and ivory lettering |
| Offline terminal | [terminal-demo.png](assets/terminal-demo.png) | Actual Tern CLI output with a transparent outer canvas |
| Setup terminal | [terminal-doctor.png](assets/terminal-doctor.png) | Actual local checks with credential values hidden |

The README selects the correct wordmark through a `picture` element and `prefers-color-scheme`. The terminal interiors stay opaque for text contrast; their surrounding canvas is transparent.

## Palette

| Color | Hex | Use |
|---|---|---|
| Burnt orange | `#D97732` | Flight mark |
| Charcoal | `#20252B` | Lettering on light pages |
| Ivory | `#F0EEE8` | Lettering on dark pages |
| Warm orange | `#E9985F` | Terminal accents |
| Graphite | `#171B20` | Terminal interior |
| Sage | `#9DD6AE` | Successful checks |
| Slate | `#94A3AB` | Secondary terminal labels |

Keep clear space around the identity. Use the supplied theme variants rather than placing a background rectangle behind the logo. Do not attach unsupported performance or quality claims to the mark.

## Reproduce terminal screenshots

```sh
uv run --extra cli --with playwright python scripts/render_assets.py
```

Install Chrome, or specify `--browser /path/to/chromium`. The script starts real CLI subprocesses, captures their output, and renders a terminal frame in Chromium with the page background omitted. Text transcripts are saved beside the PNGs. It does not call inference endpoints.

The doctor screenshot reflects actual local configuration. Reproducing its successful checks needs a configured `.env` and gcloud installation. The capture fails rather than fabricating success. Local checks do not authenticate to remote services.

## Names in code

The project and GitHub repository are **Tern**. The Python distribution is `tern-router`, and the primary command is `tern`. The `model-router` command remains a compatibility alias, and the Python import namespace remains `model_router`. Cloud service names and historical benchmark artifacts retain their original identifiers so recorded results remain reproducible.

## Asset provenance and prompts

The wordmarks and standalone mark were generated/edited with the **built-in imagegen tool**. Each PNG was copied into this repository and checked for transparent pixels. No CLI image-generation fallback or programmatic background removal was used. Terminal images come from actual CLI output.

### Light-theme wordmark

> Use case: logo-brand. Design a finished premium logo lockup for TERN, a developer tool that routes requests between AI models. Genuinely transparent RGBA background, no backdrop of any kind. Wide horizontal composition about 3:1. On the left a beautifully simple geometric tern bird in flight, constructed from two angular ribbon-like wings that also suggest a branching route. Confident distinctive silhouette, subtle negative-space junction, no eyes or illustration detail. Mark in a single flat burnt orange #D97732 that remains visible on white and dark charcoal. To its right the exact word 'tern' in lowercase, generously kerned custom geometric sans-serif, substantial medium-bold weight, precise beautifully drawn letterforms. Wordmark in solid dark charcoal #20252B, intended for a light page. Both mark and lettering vertically centered, balanced optical sizing, comfortable but not excessive transparent margins. Refined contemporary open-source tooling identity. Only the mark and the four letters t e r n. Absolutely no tagline, no rectangular panel, no grid, no texture, no gradient, no white background, no black background, no shadows, no glow, no 3D, no checkerboard baked into the image, no watermark. The empty areas must be actual alpha transparency.

### Dark-theme wordmark edit

Reference: `wordmark-light.png`.

> Edit this Tern logo lockup. Change ONLY the dark charcoal lettering of the exact word 'tern' to solid warm ivory #F0EEE8, so it works on a dark webpage. Preserve the burnt-orange bird mark exactly: same shape, color, position and size. Preserve the lettering shapes, spacing, alignment, composition and image dimensions exactly. Keep a genuinely transparent RGBA background, all negative space fully transparent, no backdrop, no rectangle, no texture, no checkerboard, no shadow or glow. The result is the dark-theme transparent wordmark.

### Standalone mark edit

Reference: `wordmark-light.png`.

> Extract the burnt-orange geometric tern bird mark from the attached Tern logo into a standalone square transparent icon. Remove all four letters completely. Preserve the bird's exact silhouette, wing shapes, negative space and color. Center the bird on a square canvas with comfortable transparent margins on every side, sized large enough to read at 32px. Genuinely transparent RGBA background, not white or black or a checkerboard pattern. Only the single burnt-orange bird mark; no type, no extra paths, no shadow, no glow, no panel.
