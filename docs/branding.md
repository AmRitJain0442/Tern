# Model Router identity

The branching route mark represents one request and a deliberate choice between two model tiers. The visual language uses graphite, warm ivory and amber, with monospace terminal typography. Assets work on GitHub's light and dark README surfaces.

| Asset | File | Purpose |
|---|---|---|
| Transparent route mark | [logo.png](assets/logo.png) | Small project identity and README footer |
| Editorial hero | [hero.png](assets/hero.png) | README cover; includes the wordmark and route symbol |
| Offline terminal | [terminal-demo.png](assets/terminal-demo.png) | Real CLI output using synthetic model responses |
| Setup terminal | [terminal-doctor.png](assets/terminal-doctor.png) | Real local setup checks; credential values hidden |

Keep generous space around the mark. Do not attach unverified performance numbers, certification badges or quality claims to the identity.

## Palette

| Color | Hex | Use |
|---|---|---|
| Graphite | `#171B20` | Main background |
| Ink | `#101418` | Terminal surround |
| Ivory | `#E8E8DD` | Main text |
| Amber | `#F5B544` | Brand and economy route |
| Sage | `#9DD6AE` | Successful checks and strong route |
| Slate | `#94A3AB` | Secondary labels |

## Reproduce terminal screenshots

```sh
uv run --extra cli --with playwright python scripts/render_assets.py
```

Install Chrome, or specify `--browser /path/to/chromium`. The script starts CLI subprocesses with a 108-column, true-color console, captures their actual output and renders it in a terminal frame through headless Chromium. The frame is presentation; command output is not handwritten. Plain text transcripts are saved beside the PNGs for accessibility. It never calls inference endpoints.

The `doctor` capture reflects the machine's real configuration. Reproducing the successful screenshot requires a configured `.env` and a local gcloud installation; it fails instead of fabricating successful checks. The screenshots do not imply that local checks authenticate to a remote service.

## Generated asset provenance

The logo and hero were generated with the **built-in imagegen tool**, then copied into `docs/assets/`. The hero uses the logo as its identity reference. No CLI image-generation fallback was used. Terminal screenshots are programmatic captures, not image-generated terminal text.

### Logo prompt

> Use case: logo-brand. Create a finished, premium developer-tool logo for an open-source-style Python project called Model Router. Asset: standalone icon, 1024 square, genuinely transparent background. The symbol should communicate a single input splitting into two carefully chosen routes. Draw a bold geometric three-way switch / branching circuit monogram using warm amber (#F5B544) thick continuous paths and three small rounded-square endpoints; dark graphite (#171B20) accents only if needed. Strong simple silhouette, precise 45-degree geometry, restrained industrial wayfinding aesthetic, flat vector-like rendering, crisp edges, centered with generous transparent margin. No lettering, no gradients, no glow, no shadows, no 3D, no mockup, no surrounding frame, no watermark. It must read clearly at favicon scale and on dark or light backgrounds. Save the result as a project-ready PNG.

### Hero prompt

> Use case: logo-brand. Create a premium GitHub README hero banner for Model Router, very wide 3:1 aspect ratio. Use the attached logo as the brand identity reference: amber one-to-two branching route symbol with rounded square endpoints. Make a finished editorial technology brand composition on a solid very dark graphite #171B20 canvas with a fine subtle technical grid. Left two-thirds: small amber eyebrow 'MLX / GPU / OPENROUTER', huge immaculate warm ivory modern geometric sans-serif lettering on two lines 'MODEL' then 'ROUTER', with the small subtitle 'Choose the right model.' underneath. Right third: an elegant large amber branching route symbol matching the attached logo, integrated into thin route lines with tiny ivory labels 'ECONOMY' above and 'STRONG' below. Bottom a very fine divider and small understated text 'SMALL CLASSIFIER. DELIBERATE DECISIONS.' Wide generous safe margins so nothing is cropped. Restrained industrial wayfinding meets Swiss editorial design, beautifully kerned typography, crisp precise shapes, high contrast. Flat graphic layout. No gradients, no glow, no 3D objects, no fake statistics, no stars, no badges, no photos, no decorative nonsense. This is the final project banner, not a website screenshot or device mockup.
