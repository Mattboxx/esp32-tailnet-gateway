"""Generate every brand SVG from one geometry and one black/green palette.

    python tools/brand_svg.py            # writes assets/brand/*.svg
    node tools/render_brand_assets.mjs   # then renders the PNG exports

The mark: a LAN input enters the ESP32 hub and leaves as three Tailnet roles;
one role is lit (green), the others are off (dim green on dark, black outline
on light). Only black and green are used; no white strokes or fills.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/brand'

INK = '#0A0F0C'        # brand black (slightly green-tinted)
INK_2 = '#111814'      # raised black surface
LINE = '#1C2A22'       # hairlines on black
GREEN = '#1FC97A'      # signal green: lit role, text on black
GREEN_DEEP = '#0B7A4B'  # green for light backgrounds (contrast on white)
GREEN_DIM = '#1F5C3F'  # "off" roles on black
GREEN_SOFT = '#9FDCBE'  # secondary text on black (green tint, not white)
GREEN_MUTED = '#5E9C7D'  # tertiary text on black
FONT = "Inter, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def glyph(input_, hub, off, core, lit=None):
    """64x64 mark without background. `core` fills the hub centre."""
    lit = lit or hub
    return (
        '<g fill="none" stroke-linecap="round" stroke-width="4.5">'
        f'<path d="M10 32h17" stroke="{input_}"/>'
        f'<path d="M27 32c11 0 11-15 21-15M27 32c11 0 11 15 21 15" stroke="{off}"/>'
        f'<path d="M27 32h21" stroke="{lit}"/></g>'
        f'<circle cx="27" cy="32" r="8" fill="{hub}"/>'
        f'<circle cx="27" cy="32" r="3" fill="{core}"/>'
        f'<circle cx="52" cy="32" r="5.5" fill="{lit}"/>'
        f'<circle cx="51.5" cy="17" r="3.5" fill="none" stroke="{off}" stroke-width="2.6"/>'
        f'<circle cx="51.5" cy="47" r="3.5" fill="none" stroke="{off}" stroke-width="2.6"/>')


def mark_on_dark(core=INK):
    return glyph(GREEN, GREEN, GREEN_DIM, core)


def svg(view_box, body, title, desc=None, size=None):
    wh = f' width="{size[0]}" height="{size[1]}"' if size else ''
    d = f'<desc id="d">{desc}</desc>' if desc else ''
    labelled = 't d' if desc else 't'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}"{wh} role="img" aria-labelledby="{labelled}">'
            f'<title id="t">{title}</title>{d}{body}</svg>\n')


def tile(fill=INK, stroke=None):
    s = f' stroke="{stroke}"' if stroke else ''
    return f'<rect width="64" height="64" rx="15" fill="{fill}"{s}/>'


def light_glyph():
    # Hub as a green ring (transparent core) so no white is needed on light backgrounds.
    return (
        '<g fill="none" stroke-linecap="round" stroke-width="4.5">'
        f'<path d="M10 32h11.5" stroke="{INK}"/>'
        f'<path d="M32.5 32c5.5 0 6.5-15 15.5-15M32.5 32c5.5 0 6.5 15 15.5 15" stroke="{INK}"/>'
        f'<path d="M32.5 32h15.5" stroke="{GREEN_DEEP}"/></g>'
        f'<circle cx="27" cy="32" r="6" fill="none" stroke="{GREEN_DEEP}" stroke-width="4.5"/>'
        f'<circle cx="52" cy="32" r="5.5" fill="{GREEN_DEEP}"/>'
        f'<circle cx="51.5" cy="17" r="3.5" fill="none" stroke="{INK}" stroke-width="2.6"/>'
        f'<circle cx="51.5" cy="47" r="3.5" fill="none" stroke="{INK}" stroke-width="2.6"/>')


def mono(color):
    return (
        '<g fill="none" stroke-linecap="round">'
        f'<path d="M10 32h17M27 32h21" stroke="{color}" stroke-width="4.5"/>'
        f'<path d="M27 32c11 0 11-15 21-15M27 32c11 0 11 15 21 15" stroke="{color}" stroke-width="2.6"/>'
        f'<circle cx="51.5" cy="17" r="3.5" stroke="{color}" stroke-width="2.4"/>'
        f'<circle cx="51.5" cy="47" r="3.5" stroke="{color}" stroke-width="2.4"/></g>'
        f'<circle cx="27" cy="32" r="8" fill="{color}"/><circle cx="52" cy="32" r="5.5" fill="{color}"/>')


def lockup(dark):
    if dark:
        mark = f'<g transform="translate(8 8) scale(1.25)">{tile(INK_2, LINE)}{mark_on_dark(INK_2)}</g>'
        word, edition = GREEN, GREEN_MUTED
    else:
        mark = f'<g transform="translate(8 8) scale(1.25)">{tile(INK)}{mark_on_dark(INK)}</g>'
        word, edition = INK, GREEN_DEEP
    text = (f'<g font-family="{FONT}"><text x="108" y="52" font-size="34" font-weight="650" letter-spacing="-0.4" fill="{word}">ESP32 Tailnet Gateway</text>'
            f'<text x="110" y="80" font-size="13.5" font-weight="650" letter-spacing="3.6" fill="{edition}">MATTBOXX EDITION</text></g>')
    return svg('0 0 560 96', mark + text, 'ESP32 Tailnet Gateway — Mattboxx Edition')


def compact_lockup():
    """Stacked mark + short name for small spaces (square-ish)."""
    body = (f'<rect width="200" height="200" rx="40" fill="{INK}"/>'
            f'<g transform="translate(52 22) scale(1.5)">{mark_on_dark(INK)}</g>'
            f'<g font-family="{FONT}" text-anchor="middle"><text x="100" y="146" font-size="25" font-weight="700" fill="{GREEN}" letter-spacing="-0.3">Tailnet</text>'
            f'<text x="100" y="172" font-size="25" font-weight="700" fill="{GREEN}" letter-spacing="-0.3">Gateway</text></g>')
    return svg('0 0 200 200', body, 'ESP32 Tailnet Gateway (compact)')


def roles(x0, y0, _scale, labels_x, font_size, label_lit, label_off):
    """Illustration: LAN device -> hub -> five roles, Service Gateway lit."""
    ys = [y0 - 100, y0 - 50, y0, y0 + 50, y0 + 100]
    names = ['Subnet router', 'AP gateway', 'Service Gateway', 'Exit node', 'Remote recovery']
    hx = x0 + 120
    parts = [
        f'<rect x="{x0 - 30}" y="{y0 - 22}" width="60" height="44" rx="9" fill="none" stroke="{GREEN}" stroke-width="2.5"/>',
        f'<path d="M{x0 - 12} {y0 + 30}h24" stroke="{GREEN}" stroke-width="2.5" stroke-linecap="round"/>',
        f'<text x="{x0}" y="{y0 + 58}" text-anchor="middle" font-family="{FONT}" font-size="15" fill="{GREEN_MUTED}">LAN device</text>',
        f'<path d="M{x0 + 30} {y0}H{hx}" stroke="{GREEN}" stroke-width="3" stroke-linecap="round"/>',
        '<g fill="none" stroke-linecap="round" stroke-width="3">',
    ]
    end = hx + 140
    for y in ys:
        if y == y0:
            parts.append(f'<path d="M{hx} {y0}H{end}" stroke="{GREEN}"/>')
        else:
            parts.append(f'<path d="M{hx} {y0}C{hx + 70} {y0} {hx + 70} {y} {end} {y}" stroke="{GREEN_DIM}"/>')
    parts.append('</g>')
    parts.append(f'<circle cx="{hx}" cy="{y0}" r="18" fill="{GREEN}"/><circle cx="{hx}" cy="{y0}" r="7" fill="{INK}"/>')
    parts.append(f'<text x="{hx}" y="{y0 + 48}" text-anchor="middle" font-family="{FONT}" font-size="15" fill="{GREEN_MUTED}">ESP32-S3</text>')
    for y, name in zip(ys, names):
        if y == y0:
            parts.append(f'<circle cx="{end + 10}" cy="{y}" r="9" fill="{GREEN}"/>')
            parts.append(f'<text x="{labels_x}" y="{y + 7}" font-family="{FONT}" font-size="{font_size}" font-weight="650" fill="{label_lit}">{name}</text>')
        else:
            parts.append(f'<circle cx="{end + 10}" cy="{y}" r="7" fill="none" stroke="{GREEN_DIM}" stroke-width="2.5"/>')
            parts.append(f'<text x="{labels_x}" y="{y + 7}" font-family="{FONT}" font-size="{font_size}" fill="{label_off}">{name}</text>')
    return ''.join(parts)


def grid(w, h):
    return (f'<defs><pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">'
            f'<path d="M40 0H0V40" fill="none" stroke="#0F1612" stroke-width="1"/></pattern></defs>'
            f'<rect width="{w}" height="{h}" fill="{INK}"/><rect width="{w}" height="{h}" fill="url(#grid)"/>')


def banner():
    body = grid(1280, 400)
    body += f'<g transform="translate(80 84) scale(1.5)">{tile(INK_2, LINE)}{mark_on_dark(INK_2)}</g>'
    body += (f'<g font-family="{FONT}"><text x="200" y="134" font-size="50" font-weight="650" letter-spacing="-0.6" fill="{GREEN}">ESP32 Tailnet Gateway</text>'
             f'<text x="203" y="170" font-size="15" font-weight="650" letter-spacing="4" fill="{GREEN_MUTED}">MATTBOXX EDITION</text>'
             f'<text x="80" y="268" font-size="28" font-weight="500" fill="{GREEN_SOFT}">One ESP32. Multiple Tailnet roles.</text>'
             f'<text x="80" y="308" font-size="28" font-weight="600" fill="{GREEN}">Enable only what you need.</text></g>')
    body += roles(770, 200, 1, 1060, 18, GREEN, GREEN_MUTED)
    return svg('0 0 1280 400', body, 'ESP32 Tailnet Gateway — Mattboxx Edition',
               'One ESP32. Multiple Tailnet roles. Enable only what you need. A LAN device passes through the ESP32; the Service Gateway role is lit while subnet router, AP gateway, exit node and remote recovery stay off until enabled.',
               (1280, 400))


def social():
    body = grid(1280, 640)
    body += f'<g transform="translate(96 80) scale(1.75)">{tile(INK_2, LINE)}{mark_on_dark(INK_2)}</g>'
    body += (f'<g font-family="{FONT}"><text x="232" y="146" font-size="58" font-weight="650" letter-spacing="-0.7" fill="{GREEN}">ESP32 Tailnet Gateway</text>'
             f'<text x="235" y="186" font-size="17" font-weight="650" letter-spacing="4.5" fill="{GREEN_MUTED}">MATTBOXX EDITION</text>'
             f'<text x="96" y="318" font-size="32" font-weight="500" fill="{GREEN_SOFT}">One ESP32.</text>'
             f'<text x="96" y="362" font-size="32" font-weight="500" fill="{GREEN_SOFT}">Multiple Tailnet roles.</text>'
             f'<text x="96" y="406" font-size="32" font-weight="600" fill="{GREEN}">Enable only what you need.</text></g>')
    body += roles(760, 360, 1, 1054, 20, GREEN, GREEN_MUTED)
    body += f'<path d="M96 512H1184" stroke="{LINE}" stroke-width="1"/>'
    body += (f'<g font-family="{FONT}" font-size="21" fill="{GREEN_MUTED}">'
             '<text x="96" y="550">All-in-one ESP32-S3 Tailscale/Headscale gateway with selective LAN-to-Tailnet access,</text>'
             '<text x="96" y="580">subnet routing, remote recovery and optional automation.</text></g>')
    return svg('0 0 1280 640', body, 'ESP32 Tailnet Gateway — Mattboxx Edition',
               'All-in-one ESP32-S3 Tailscale/Headscale gateway with selective LAN-to-Tailnet access, subnet routing, remote recovery and optional automation.',
               (1280, 640))


def main():
    files = {
        'logo-mark.svg': svg('0 0 64 64', tile() + mark_on_dark(), 'ESP32 Tailnet Gateway'),
        'logo-mark-dark.svg': svg('0 0 64 64', mark_on_dark('none').replace('<circle cx="27" cy="32" r="3" fill="none"/>', ''),
                                  'ESP32 Tailnet Gateway (transparent, for dark backgrounds)'),
        'logo-mark-light.svg': svg('0 0 64 64', light_glyph(), 'ESP32 Tailnet Gateway (transparent, for light backgrounds)'),
        'logo-mono.svg': svg('0 0 64 64', mono('currentColor'), 'ESP32 Tailnet Gateway (single colour, currentColor)'),
        'logo-mono-black.svg': svg('0 0 64 64', mono(INK), 'ESP32 Tailnet Gateway (black)'),
        'logo-mono-green.svg': svg('0 0 64 64', mono(GREEN_DEEP), 'ESP32 Tailnet Gateway (green)'),
        'logo-horizontal-dark.svg': lockup(True),
        'logo-horizontal-light.svg': lockup(False),
        'logo-compact.svg': compact_lockup(),
        'banner.svg': banner(),
        'social-preview.svg': social(),
    }
    for name, text in files.items():
        (OUT / name).write_text(text, encoding='utf-8')
    for stale in ('logo-mono-white.svg',):
        path = OUT / stale
        if path.exists():
            path.unlink()
    print('wrote', len(files), 'SVG files')


if __name__ == '__main__':
    main()
