"""Majlisna — the Mīm kit (logo-design skill, phase 7). Everything is generated from the geometry below.

The mark: مـ, the wordmark's first letter in its Kufi, joining to the LEFT on the baseline (the RTL flow
of مجلسنا). Its loop is the halqa (a disk), its counter the nuqṭa (a lozenge), its baseline the kashida.

Run: uv run --offline --no-project --with fonttools --with brotli python -I kit.py KITDIR
"""
import math
import os
import re
import subprocess
import sys

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

# The repo's front, four levels up from docs/brand/mim/generator/ (its fonts and frozen wordmark).
FRONT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "front"))
MARCELLUS = f"{FRONT}/node_modules/@fontsource/marcellus/files/marcellus-latin-400-normal.woff2"
WORDMARKS = {"gold": f"{FRONT}/src/assets/brand/wordmark-gold.svg", "ink": f"{FRONT}/src/assets/brand/wordmark-ink.svg"}

# Colours: the frozen brand assets' values (wordmark.py), with the DESIGN.md token each one stands for.
BRASS = "#e3b56b"  # --lockup / --brass at night (oklch .80 .105 77 = #e4b56d); wordmark-gold's letters
INK = "#1d1613"  # --lockup / --text by day (oklch .21 .016 50 = #1f1612); wordmark-ink's letters, the app tile
THREAD = "#b0402c"  # the wordmark's madder thread (wordmark.py); between --wool-madder and --madd-madder
NIGHT = "#130d0a"  # --bg at night (tent black), the manifest's background_color
DAY = "#f8f6f3"  # --bg by day (gypsum)
CREAM = "#efe7d8"  # --text at night (wool cream)

# ── Geometry (viewBox 0 0 256 256) ───────────────────────────────────────────────────────────
MASTER = dict(cx=151, cy=124, Ro=88, h=48, hy=121, t=36, bar_left=17)
# light on dark looks heavier (irradiation): every edge moved in by 1.5 units (≈4 % of the kashida)
REVERSED = dict(cx=151, cy=124, Ro=86.5, h=49.5, hy=121, t=33, bar_left=18.5)
# ≤ 32 px: one colour, no thread; bigger counter, thicker kashida, shorter run so the loop grows
SMALL = dict(cx=150, cy=124, Ro=92, h=54, hy=121, t=44, bar_left=30)
# the thread: a third of the kashida, centred, from the cut end to just before the loop
THREAD_RECT = dict(x=17, y=188, w=73, h=12)


def fmt(v):
    v = round(v, 2)
    return str(int(v)) if v == int(v) else str(v)


def mim(cx, cy, Ro, h, hy, t, bar_left):
    """Disk ∪ kashida (bottom on the disk's lowest point: the loop SITS on the line), lozenge counter."""
    yb = cy + Ro
    yt = yb - t
    xl = cx - math.sqrt(Ro**2 - (yt - cy) ** 2)  # kashida top meets the loop
    outer = (
        f"M{fmt(bar_left)} {fmt(yt)} L{fmt(xl)} {fmt(yt)} "
        f"A{fmt(Ro)} {fmt(Ro)} 0 1 1 {fmt(cx)} {fmt(yb)} L{fmt(bar_left)} {fmt(yb)} Z"
    )
    counter = f"M{fmt(cx)} {fmt(hy - h)} L{fmt(cx - h)} {fmt(hy)} L{fmt(cx)} {fmt(hy + h)} L{fmt(cx + h)} {fmt(hy)} Z"
    return f"{outer} {counter}"


def bbox(g):
    return (g["bar_left"], g["cy"] - g["Ro"], g["cx"] + g["Ro"], g["cy"] + g["Ro"])


def mark_body(g, fill, thread=None):
    """The mark's elements (no <svg>): one path, plus the madder thread when coloured."""
    out = f'<path fill="{fill}" d="{mim(**g)}"/>'
    if thread:
        r = THREAD_RECT
        out += f'<rect x="{r["x"]}" y="{r["y"]}" width="{r["w"]}" height="{r["h"]}" fill="{thread}"/>'
    return out


def svg_doc(body, w=256, h=256, title="Majlisna", vb=None):
    vb = vb or f"0 0 {fmt(w)} {fmt(h)}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{fmt(w)}" height="{fmt(h)}" role="img">'
        f"<title>{title}</title>{body}</svg>\n"
    )


# ── Type ────────────────────────────────────────────────────────────────────────────────────
def latin(text="MAJLISNA", tracking_em=0.26):
    f = TTFont(MARCELLUS)
    gs, cmap, upm, hmtx = f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm, f["hmtx"]
    x, pen = 0.0, SVGPathPen(gs)
    for i, ch in enumerate(text):
        g = cmap[ord(ch)]
        gs[g].draw(TransformPen(pen, (1, 0, 0, -1, x, 0)))
        x += hmtx[g][0] + (tracking_em * upm if i < len(text) - 1 else 0)
    bp = BoundsPen(gs)
    gs[cmap[ord("M")]].draw(bp)
    return pen.getCommands(), x, bp.bounds[3]


def wordmark(kind, fill=None, thread=None):
    """Inner markup + viewBox of a frozen wordmark; fill/thread recolour it (one-colour versions)."""
    raw = open(WORDMARKS[kind], encoding="utf-8").read()
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', raw).group(1).split()]
    inner = re.sub(r"^.*?</title>", "", raw, flags=re.S).replace("</svg>", "")
    if fill:
        inner = re.sub(r'fill="#(?!b0402c)[0-9a-fA-F]{6}"', f'fill="{fill}"', inner)
        inner = inner.replace('fill="#b0402c"', f'fill="{thread or fill}"')
    return inner, vb


# the wordmark's letters span y -830 (stem tops) .. +215 (the jīm's dot) around its baseline y = 0
WM_TOP, WM_BOT = -830, 215


def lockup_horizontal(scheme):
    """[مجلسنا over MAJLISNA] then the Mīm at the RTL start (right), its kashida on the name's baseline,
    at the wordmark's own baseline stroke thickness."""
    wm, vb = wordmark(scheme["wm"], scheme.get("wm_fill"), scheme.get("wm_thread"))
    s_ar = 118 / 830
    ar_w = vb[2] * s_ar
    lat_d, lat_adv, cap = latin()
    s_lat = 26 / cap
    lat_w = lat_adv * s_lat
    text_w = max(ar_w, lat_w)
    pad, ar_base, lat_base = 8, 146, 214
    k = 0.6  # 36 × 0.6 = 21.6 ≈ the wordmark's baseline stroke (140 × 118/830 = 19.9)
    g = scheme["geom"]
    gap = 2 * MASTER["h"] * k  # one nuqṭa (the counter's diagonal) between the name and the mark: less and
    # the mark's kashida reads as a letter joined to the word (ممجلسنا)
    sx = pad + text_w + gap - g["bar_left"] * k
    ty = ar_base - (g["cy"] + g["Ro"]) * k
    W = math.ceil(sx + (g["cx"] + g["Ro"]) * k + pad)
    body = (
        (f'<rect width="{fmt(W)}" height="256" fill="{scheme["bg"]}"/>' if scheme.get("bg") else "")
        + f'<g transform="translate({fmt(pad + text_w - ar_w)} {ar_base}) scale({s_ar:.5f})">{wm}</g>'
        + f'<path fill="{scheme["lat"]}" transform="translate({fmt(pad + text_w - lat_w)} {lat_base}) scale({s_lat:.5f})" d="{lat_d}"/>'
        + f'<g transform="translate({fmt(sx)} {fmt(ty)}) scale({k})">{mark_body(g, scheme["mark"], scheme.get("thread"))}</g>'
    )
    return svg_doc(body, W, 256, "Majlisna — horizontal lockup")


def lockup_stacked(scheme):
    """The Mīm centred on top, مجلسنا under it, MAJLISNA under that."""
    wm, vb = wordmark(scheme["wm"], scheme.get("wm_fill"), scheme.get("wm_thread"))
    s_ar = 150 / 830
    ar_w = vb[2] * s_ar
    lat_d, lat_adv, cap = latin()
    s_lat = 30 / cap
    lat_w = lat_adv * s_lat
    g = scheme["geom"]
    k = 1.0
    x0, y0, x1, y1 = bbox(g)
    mw, mh = (x1 - x0) * k, (y1 - y0) * k
    W = math.ceil(max(ar_w, lat_w, mw) + 48)
    top = 24
    sym_ty = top - y0 * k
    sym_tx = (W - mw) / 2 - x0 * k
    ar_base = top + mh + g["h"] * 1.0 + 150  # a nuqṭa (half-diagonal) of air, then the letters' body
    lat_base = ar_base + 215 * s_ar + 30 + 46
    H = math.ceil(lat_base + 28)
    body = (
        (f'<rect width="{fmt(W)}" height="{fmt(H)}" fill="{scheme["bg"]}"/>' if scheme.get("bg") else "")
        + f'<g transform="translate({fmt(sym_tx)} {fmt(sym_ty)}) scale({k})">{mark_body(g, scheme["mark"], scheme.get("thread"))}</g>'
        + f'<g transform="translate({fmt((W - ar_w) / 2)} {fmt(ar_base)}) scale({s_ar:.5f})">{wm}</g>'
        + f'<path fill="{scheme["lat"]}" transform="translate({fmt((W - lat_w) / 2)} {fmt(lat_base)}) scale({s_lat:.5f})" d="{lat_d}"/>'
    )
    return svg_doc(body, W, H, "Majlisna — stacked lockup")


# ── Icons (viewBox 0 0 100 100, the repo's convention: render-icons.mjs strips exactly this tile) ──
TILE = '<rect width="100" height="100" rx="22" fill="#1d1613"/>'


def placed(g, fill, thread, width, cx=50.0, cy=49.0):
    """The mark scaled to `width` (of 100) and placed by its optical centre: horizontally between the
    bbox centre and the loop's centre (the loop carries the weight), vertically a hair above centre."""
    x0, y0, x1, y1 = bbox(g)
    s = width / (x1 - x0)
    ox = ((x0 + x1) / 2 + g["cx"]) / 2  # optical x
    oy = (y0 + y1) / 2
    return f'<g transform="translate({fmt(cx - ox * s)} {fmt(cy - oy * s)}) scale({s:.3f})">{mark_body(g, fill, thread)}</g>'


def app_icon_svg():
    return svg_doc(
        TILE + placed(MASTER, BRASS, THREAD, 70),
        100,
        100,
        "Majlisna",
    ).replace(
        'role="img">',
        'role="img" aria-label="Majlisna: the mīm of majlis, its loop the halqa, its counter the nuqṭa, its kashida the woven band">',
    ).replace(' width="100" height="100" role', ' role')


def favicon_svg():
    return svg_doc(TILE + placed(SMALL, BRASS, None, 74, cy=50.0), 100, 100, "Majlisna").replace(
        'role="img">', 'role="img" aria-label="Majlisna">'
    ).replace(' width="100" height="100" role', ' role')


def bleed(width, ground="#1d1613", g=MASTER, thread=THREAD):
    return svg_doc(f'<rect width="100" height="100" fill="{ground}"/>' + placed(g, BRASS, thread, width, cy=50.0), 100, 100, "Majlisna")


def render(svg_path, png, size):
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), "-o", png, svg_path], check=True)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


if __name__ == "__main__":
    K = sys.argv[1]
    M = f"{K}/master"
    # symbol masters
    write(f"{M}/majlisna-mim-symbol.svg", svg_doc(mark_body(MASTER, "#000"), title="Majlisna — the Mīm"))
    write(f"{M}/majlisna-mim-symbol-night.svg", svg_doc(f'<rect width="256" height="256" fill="{NIGHT}"/>' + mark_body(MASTER, BRASS, THREAD), title="Majlisna — the Mīm, night"))
    write(f"{M}/majlisna-mim-symbol-day.svg", svg_doc(mark_body(MASTER, INK, THREAD), title="Majlisna — the Mīm, afternoon"))
    write(f"{M}/majlisna-mim-symbol-brass-thread.svg", svg_doc(mark_body(MASTER, BRASS, THREAD), title="Majlisna — the Mīm, brass (transparent)"))
    write(f"{M}/majlisna-mim-symbol-black.svg", svg_doc(mark_body(MASTER, "#000000"), title="Majlisna — the Mīm, black"))
    write(f"{M}/majlisna-mim-symbol-white.svg", svg_doc(mark_body(REVERSED, "#ffffff"), title="Majlisna — the Mīm, white (thinned)"))
    write(f"{M}/majlisna-mim-symbol-mono-ink.svg", svg_doc(mark_body(MASTER, INK), title="Majlisna — the Mīm, ink"))
    write(f"{M}/majlisna-mim-symbol-mono-brass.svg", svg_doc(mark_body(REVERSED, BRASS), title="Majlisna — the Mīm, brass (thinned, for dark grounds)"))
    write(f"{M}/majlisna-mim-symbol-reversed-night.svg", svg_doc(f'<rect width="256" height="256" fill="{NIGHT}"/>' + mark_body(REVERSED, BRASS, THREAD), title="Majlisna — the Mīm, night, thinned"))
    write(f"{M}/majlisna-mim-symbol-night-transparent.svg", svg_doc(mark_body(REVERSED, BRASS, THREAD), title="Majlisna — the Mīm, night (thinned, transparent)"))
    write(f"{M}/majlisna-mim-small.svg", svg_doc(mark_body(SMALL, "#000"), title="Majlisna — the Mīm, small cut (≤ 32 px)"))
    write(f"{M}/majlisna-mim-small-brass.svg", svg_doc(mark_body(SMALL, BRASS), title="Majlisna — the Mīm, small cut, brass"))
    # lockups
    L = f"{K}/lockups"
    schemes = {
        "night": dict(wm="gold", mark=BRASS, thread=THREAD, lat=BRASS, bg=NIGHT, geom=REVERSED),
        "night-transparent": dict(wm="gold", mark=BRASS, thread=THREAD, lat=BRASS, geom=REVERSED),
        "day": dict(wm="ink", mark=INK, thread=THREAD, lat=INK, geom=MASTER),
        "black": dict(wm="ink", wm_fill="#000000", mark="#000000", lat="#000000", geom=MASTER),
        "white": dict(wm="ink", wm_fill="#ffffff", mark="#ffffff", lat="#ffffff", geom=REVERSED),
    }
    for name, sc in schemes.items():
        write(f"{L}/majlisna-lockup-horizontal-{name}.svg", lockup_horizontal(sc))
        write(f"{L}/majlisna-lockup-stacked-{name}.svg", lockup_stacked(sc))
    # web icons, drop-in for the repo (same names and sizes). Written under KITDIR/repo/front/, NOT into
    # front/: copy the two SVGs to the same paths in front/ by hand, then render the live rasters with
    # `node front/scripts/brand/render-icons.mjs` (front/src/assets/brand/SOURCES.txt); the PNGs below are a preview.
    R = f"{K}/repo/front"
    write(f"{R}/src/assets/brand/app-icon.svg", app_icon_svg())
    write(f"{R}/public/favicon.svg", favicon_svg())
    T = f"{K}/_tmp"
    write(f"{T}/maskable.svg", bleed(56))  # the mark inside the 80 % safe circle (checked below)
    write(f"{T}/apple.svg", bleed(62))  # iOS rounds the corners itself
    os.makedirs(f"{R}/public/icons", exist_ok=True)
    render(f"{R}/src/assets/brand/app-icon.svg", f"{R}/public/icons/icon-192.png", 192)
    render(f"{R}/src/assets/brand/app-icon.svg", f"{R}/public/icons/icon-512.png", 512)
    render(f"{T}/maskable.svg", f"{R}/public/icons/icon-maskable-512.png", 512)
    render(f"{T}/apple.svg", f"{R}/public/icons/apple-touch-icon.png", 180)
    # safe-zone check for the maskable art: every corner of the mark within r = 40 % of the centre
    g, width = MASTER, 56
    x0, y0, x1, y1 = bbox(g)
    s = width / (x1 - x0)
    ox, oy = ((x0 + x1) / 2 + g["cx"]) / 2, (y0 + y1) / 2
    pts = [(x0, y1), (x0, y1 - g["t"])] + [(g["cx"] + g["Ro"] * math.cos(a / 10), g["cy"] + g["Ro"] * math.sin(a / 10)) for a in range(63)]
    far = max(math.hypot((x - ox) * s, (y - oy) * s) for x, y in pts)
    print(f"maskable: farthest point {far:.1f} of 100 from the centre (safe zone radius 40)")
    print("done")
