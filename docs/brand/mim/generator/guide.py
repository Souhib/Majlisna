"""The one-page usage guide (PNG + SVG) for the Mīm, drawn from the kit's own files.

Run: uv run --offline --no-project --with fonttools --with brotli python -I guide.py KITDIR
"""
import base64
import importlib.util
import subprocess
import sys

spec = importlib.util.spec_from_file_location("kit", __file__.replace("guide.py", "kit.py"))
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)
K = sys.argv[1]

W, H = 1240, 1754
F = 'font-family="Helvetica, Arial, sans-serif"'
parts = [f'<rect width="{W}" height="{H}" fill="#ffffff"/>']


def text(x, y, s, size=15, weight=400, fill="#1d1613", anchor="start"):
    parts.append(f'<text x="{x}" y="{y}" {F} font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{s}</text>')


def img(path, x, y, w, h):
    mime = "image/png" if path.endswith(".png") else "image/svg+xml"
    data = base64.b64encode(open(path, "rb").read()).decode()
    parts.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet" href="data:{mime};base64,{data}"/>')


def mark(x, y, size, fill, thread=None, g=None, extra=""):
    g = g or kit.MASTER
    s = size / 256
    parts.append(f'<g transform="translate({x} {y}) scale({s:.4f}) {extra}">{kit.mark_body(g, fill, thread)}</g>')


# header
text(60, 80, "Majlisna — the Mīm", 34, 700)
text(60, 112, "The mīm, first letter of the name in the wordmark's Kufi: its loop the halqa, its counter the nuqṭa (a lozenge), its baseline", 15, 400, "#555")
text(60, 134, "the kashida with the madder thread. It joins to the LEFT, into the name, as in the RTL flow of the wordmark.", 15, 400, "#555")

# 1 clear space
text(60, 190, "1 · Clear space", 20, 700)
x0, y0, sz = 134, 272, 240
n = 96 / 256 * sz  # one nuqṭa (the counter's diagonal) at this size
bx0, by0, bx1, by1 = 17 / 256 * sz, 36 / 256 * sz, 239 / 256 * sz, 212 / 256 * sz
parts.append(f'<rect x="{x0 + bx0 - n:.1f}" y="{y0 + by0 - n:.1f}" width="{bx1 - bx0 + 2 * n:.1f}" height="{by1 - by0 + 2 * n:.1f}" fill="#f3efe6" stroke="#c9bfa9" stroke-dasharray="5 4"/>')
parts.append(f'<rect x="{x0 + bx0:.1f}" y="{y0 + by0:.1f}" width="{bx1 - bx0:.1f}" height="{by1 - by0:.1f}" fill="none" stroke="#c9bfa9"/>')
mark(x0, y0, sz, kit.INK, kit.THREAD)
c = 48 / 256 * sz
cx, cy = x0 + 151 / 256 * sz, y0 + 121 / 256 * sz
parts.append(f'<path d="M{cx:.1f} {cy - c:.1f} L{cx + c:.1f} {cy:.1f} L{cx:.1f} {cy + c:.1f} L{cx - c:.1f} {cy:.1f} Z" fill="none" stroke="#b0402c" stroke-width="2"/>')
text(470, 250, "Keep one nuqṭa of air around the mark: the diagonal of its lozenge", 15)
text(470, 272, "counter (outlined in madder), measured at the size in use.", 15)
text(470, 306, "In the horizontal lockup the same nuqṭa separates the name from the", 15)
text(470, 328, "mark. Closer, its kashida reads as a letter joined to the name", 15)
text(470, 350, "(a second mīm). The mark always sits at the Arabic reading start, the right.", 15)
img(f"{K}/lockups/majlisna-lockup-horizontal-day.svg", 470, 380, 520, 130)

# 2 minimum sizes
text(60, 600, "2 · Minimum sizes", 20, 700)
rows = [
    ("Mark, colour (with the thread)", "48 px", "12 mm", "majlisna-mim-symbol-day.svg"),
    ("Mark, small cut (one colour, no thread)", "16–47 px", "5 mm", "majlisna-mim-small.svg"),
    ("Horizontal lockup", "80 px tall", "30 mm wide", None),
    ("Stacked lockup", "120 px tall", "25 mm wide", None),
]
y = 640
text(60, y, "Version", 13, 700, "#777")
text(560, y, "Screen", 13, 700, "#777")
text(700, y, "Print", 13, 700, "#777")
for label, screen, prnt, f in rows:
    y += 34
    text(60, y, label, 15)
    text(560, y, screen, 15)
    text(700, y, prnt, 15)
# real-size demo of the small cut
for i, s in enumerate((16, 24, 32)):
    mark(880 + i * 52, 650 + (32 - s) / 2, s, "#000", None, kit.SMALL)
for i, s in enumerate((48, 64)):
    mark(1040 + i * 70, 640 + (64 - s) / 2, s, kit.INK, kit.THREAD)
text(880, 735, "16 · 24 · 32 px (small cut)     48 · 64 px (master)", 12, 400, "#777")

# 3 colours
text(60, 830, "3 · Colours", 20, 700)
swatches = [
    ("Brass", "#e3b56b", "227 181 107", "--lockup / --brass at night", "0 20 53 11"),
    ("Goat-hair ink", "#1d1613", "29 22 19", "--lockup / --text by day", "0 24 34 89"),
    ("Madder thread", "#b0402c", "176 64 44", "the wordmark's thread", "0 64 75 31"),
    ("Tent black", "#130d0a", "19 13 10", "--bg at night", "0 32 47 93"),
    ("Gypsum", "#f8f6f3", "248 246 243", "--bg by day", "0 1 2 3"),
]
for i, (name, hx, rgb, token, cmyk) in enumerate(swatches):
    x = 60 + i * 226
    parts.append(f'<rect x="{x}" y="860" width="206" height="90" fill="{hx}" stroke="#ddd"/>')
    text(x, 976, name, 15, 700)
    text(x, 996, f"HEX {hx} · RGB {rgb}", 12, 400, "#555")
    text(x, 1014, f"CMYK ≈ {cmyk} (proof it)", 12, 400, "#555")
    text(x, 1032, token, 12, 400, "#555")
text(60, 1062, "One colour: black, white, ink or brass. On dark grounds use the thinned files (-white, -mono-brass, -night): light on dark looks heavier.", 13, 400, "#555")

# 4 approved grounds
text(60, 1120, "4 · Approved grounds", 20, 700)
grounds = [
    ("#130d0a", kit.BRASS, kit.THREAD, kit.REVERSED, "Night: brass + thread on tent black"),
    ("#f8f6f3", kit.INK, kit.THREAD, kit.MASTER, "Afternoon: ink + thread on gypsum"),
    ("#ffffff", "#000000", None, kit.MASTER, "Black on white"),
    ("#1d1613", "#ffffff", None, kit.REVERSED, "White (thinned) on ink"),
]
for i, (bg, fill, thread, g, label) in enumerate(grounds):
    x = 60 + i * 282
    parts.append(f'<rect x="{x}" y="1145" width="262" height="150" fill="{bg}" stroke="#ddd"/>')
    mark(x + 71, 1155, 120, fill, thread, g)
    text(x, 1318, label, 13)
text(60, 1345, "Over photographs (the hero skies), only on a calm dark area, brass or white. On Sadu bands, wool colours or busy patterns, use the app tile.", 13, 400, "#555")

# 5 misuse
text(60, 1405, "5 · Don't", 20, 700)
donts = [
    ("mirror it (it would join right:", "no longer the mīm of the name)", 'translate(256 0) scale(-1 1)', kit.INK, kit.THREAD),
    ("rotate it", "", 'rotate(-20 128 128)', kit.INK, kit.THREAD),
    ("recolour the thread", "", None, kit.INK, "#2f6fb0"),
    ("round the counter", "(it is a lozenge)", "ROUND", kit.INK, kit.THREAD),
    ("stretch it", "", 'translate(0 40) scale(1 0.7)', kit.INK, kit.THREAD),
    ("add effects", "(glow, shadow, gradient)", "GLOW", kit.BRASS, kit.THREAD),
]
for i, (l1, l2, tf, fill, thread) in enumerate(donts):
    x = 60 + i * 190
    parts.append(f'<rect x="{x}" y="1430" width="170" height="150" fill="{"#130d0a" if tf == "GLOW" else "#ffffff"}" stroke="#ddd"/>')
    s = 120 / 256
    if tf == "ROUND":
        body = (f'<path fill="{fill}" d="{kit.mim(**kit.MASTER).split(" M151")[0]}"/>'
                f'<circle cx="151" cy="121" r="44" fill="#ffffff"/>'
                f'<rect x="17" y="188" width="73" height="12" fill="{thread}"/>')
        parts.append(f'<g transform="translate({x + 25} {1445}) scale({s:.4f})">{body}</g>')
    elif tf == "GLOW":
        parts.append('<defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14"/></filter></defs>')
        parts.append(f'<g transform="translate({x + 25} {1445}) scale({s:.4f})"><g filter="url(#glow)" opacity=".8">{kit.mark_body(kit.MASTER, "#ffcf6e")}</g>{kit.mark_body(kit.MASTER, fill, thread)}</g>')
    elif tf:
        parts.append(f'<g transform="translate({x + 25} {1445}) scale({s:.4f})"><g transform="{tf}">{kit.mark_body(kit.MASTER, fill, thread)}</g></g>')
    else:
        parts.append(f'<g transform="translate({x + 25} {1445}) scale({s:.4f})">{kit.mark_body(kit.MASTER, fill, thread)}</g>')
    parts.append(f'<path d="M{x + 8} {1572} L{x + 162} {1438}" stroke="#d0342c" stroke-width="3"/>')
    text(x, 1602, l1, 13)
    if l2:
        text(x, 1620, l2, 13, 400, "#555")
text(60, 1668, "Also: no outline, no thread in the small cut, nothing in or over the counter, never the old halqa icon. The mark never sits to the left of the Arabic name.", 13, 400, "#555")
text(60, 1700, "Masters: docs/brand/mim/master (symbol), docs/brand/mim/lockups. Web icons: front/src/assets/brand/app-icon.svg, front/public/favicon.svg.", 12, 400, "#777")
text(60, 1718, "Rasters: front/scripts/brand/render-icons.mjs. Fonts: Reem Kufi 700 and Marcellus 400 outlined (SIL OFL 1.1). Trademark search: not done.", 12, 400, "#777")

svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">{"".join(parts)}</svg>'
out = f"{K}/guide/majlisna-mim-usage-guide"
import os

os.makedirs(f"{K}/guide", exist_ok=True)
open(out + ".svg", "w", encoding="utf-8").write(svg)
subprocess.run(["rsvg-convert", out + ".svg", "-o", out + ".png"], check=True)
print("wrote", out + ".png")
