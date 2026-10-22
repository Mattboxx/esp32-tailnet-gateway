# Brand guide — ESP32 Tailnet Gateway, Mattboxx Edition

**Name:** ESP32 Tailnet Gateway — Mattboxx Edition (short: *Tailnet Gateway*).
**Tagline:** One ESP32. Multiple Tailnet roles. Enable only what you need.
**Description:** All-in-one ESP32-S3 Tailscale/Headscale gateway with selective
LAN-to-Tailnet access, subnet routing, remote recovery and optional automation.

Formerly *ESP32 Homelab Gateway* (Mattboxx edition of Csontikka's
*esp32-tailscale-subnet-router*). Community firmware: never present it as an
official Tailscale or Espressif product, and do not borrow their logos,
colours or typefaces. *Tailscale*, *Headscale*, *WireGuard* and *ESP32* are
trademarks of their respective owners and are used only descriptively.

## Logo

The mark is a LAN device (left dot) passing through one gateway into several
Tailnet roles. One role is lit; the others are outlined — *enable only what
you need*. It deliberately avoids a dot grid (Tailscale) and chip/red motifs
(Espressif).

| File | Use |
|---|---|
| `logo-mark.svg` | App icon, favicon, avatar (dark tile) |
| `logo-mark-light.svg` | Mark without tile, for light backgrounds |
| `logo-horizontal-dark.svg` / `-light.svg` | Mark + wordmark lockups |
| `banner.svg` | README hero, 1280×400 |
| `social-preview.svg` | GitHub / Open Graph preview, 1280×640 |
| `png/` | Raster exports rendered by `node tools/render_brand_assets.mjs` |

Keep clear space of at least one gateway width around the mark. Do not
recolour the lit role, add gradients, rotate, outline or put the dark tile on
busy photos. Minimum size: 16 px (favicon), 24 px recommended.

## Colour

| Token | Hex | Use |
|---|---|---|
| Ink 950 | `#0D1117` | Dark background |
| Ink 900 | `#11161D` | Zones, site surface |
| Ink 800 | `#161B22` | Cards, boxes |
| Line | `#30363D` | Borders, dividers |
| Muted | `#475569` | Disabled roles, inactive lines |
| Text secondary | `#8B949E` | Captions (dark theme) |
| Text primary | `#E6EDF3` | Body on dark |
| Signal teal | `#2DD4BF` | The active route, brand accent on dark |
| Signal teal (light) | `#0F766E` | Accent and links on white (≥ 4.5:1) |
| Amber | `#F5A524` | Caveats and limits, used sparingly |
| Danger | `#F85149` | Refused traffic, errors |

The firmware Web UI keeps its blue interaction colour (`#3B82F6`) for
controls; brand teal identifies the product and active routes.
Flat colour only: no decorative gradients.

## Typography

System stacks, no web-font download (fast, private, no third-party requests):

- UI/text: `Inter, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- Code: `ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace`

Wordmark: semibold (600–650), sentence case. Edition label: uppercase,
600 weight, letter-spacing ≈ 0.25 em, teal.

## Spacing and shape

4 px base grid; common steps 4, 8, 12, 16, 24, 32, 48, 64. Radius: 8 px
small elements, 10–12 px cards and zones, 14 px icon tile, 16 px diagram panels.

## Iconography and diagrams

Diagrams live in `assets/diagrams/` as editable SVG with `<title>`/`<desc>`
for accessibility. Conventions: solid white arrows = LAN/IP traffic; dashed teal
= WireGuard; dashed red with ✕ = refused; dashed grey outline = optional
module; teal-bordered box = the component doing the work. Captions state
limits, never invented metrics.

## Screenshots

Only authentic captures of a real build, labelled with the version they show.
Concept illustrations must be labelled as such. Never invent metrics,
peers, addresses or results; mask private addresses and identifiers.

## Licence

Brand assets are original work for this project and are distributed under the
repository's MIT licence. The upstream bunny artwork in `assets/logo/` belongs
to the upstream author and is kept for attribution only.
