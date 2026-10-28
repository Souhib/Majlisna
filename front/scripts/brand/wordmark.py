"""Frozen wordmark: مجلسنا in Reem Kufi 700 with the stretched lam-seen joint (al-madd),
outlined to SVG paths so favicons, OG cards and design tools never depend on a web font.

The layout reproduces the live <Wordmark> exactly: two shaped halves that each end or start
with a tatweel, and a band of the tatweel's own height laid between them, overlapping each
tatweel end by 0.235 em (the CSS `margin-inline: -0.235em`).

Outputs, in src/assets/brand/:
  wordmark-night.svg  cream letters, woven madd band (night selvedge); >= 80 px uses
  wordmark-day.svg    ink letters, woven madd band (day selvedge);    >= 80 px uses
  wordmark-gold.svg   brass letters, ink kashida with one madder thread (nav, < 80 px)
  wordmark-ink.svg    ink letters, ink kashida with one madder thread (light, < 80 px)

Run from front/ (needs network once for the deps):
  uv run --with fonttools --with brotli --with uharfbuzz python -I scripts/brand/wordmark.py
"""
import io
import pathlib

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FRONT = pathlib.Path(__file__).resolve().parents[2]
WOFF2 = FRONT / "node_modules/@fontsource-variable/reem-kufi/files/reem-kufi-arabic-wght-normal.woff2"
OUT = FRONT / "src/assets/brand"

CREAM, INK, BRASS = "#efe7d8", "#1d1613", "#e3b56b"
MADDER_DARK, UNDYED, OCHRE, GOAT = "#9a3324", "#eadfc8", "#c08a3e", "#1d1613"


def load_font():
    f = TTFont(str(WOFF2))
    inst = instancer.instantiateVariableFont(f, {"wght": 700})
    inst.flavor = None
    buf = io.BytesIO()
    inst.save(buf)
    return inst, buf.getvalue()


def shape(hbfont, text):
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf)
    return buf.glyph_infos, buf.glyph_positions


def outline(ttfont, infos, positions, x0):
    """SVG path data for a shaped run (glyphs come back in visual order), y flipped."""
    order = ttfont.getGlyphOrder()
    gs = ttfont.getGlyphSet()
    pen = SVGPathPen(gs)
    x = x0
    for info, pos in zip(infos, positions):
        name = order[info.codepoint]
        tpen = TransformPen(pen, (1, 0, 0, -1, x + pos.x_offset, -pos.y_offset))
        gs[name].draw(tpen)
        x += pos.x_advance
    return pen.getCommands(), x - x0


def madd_rows(selvedge):
    W = 18
    s, k = selvedge, "K" if selvedge != "K" else "C"
    rows = [s * W, "".join(s if i % 2 == 0 else k for i in range(W))]
    field = [["R"] * W for _ in range(7)]
    eye = {0: range(4, 5), 1: range(3, 6), 2: range(2, 7), 3: range(1, 8), 4: range(2, 7), 5: range(3, 6), 6: range(4, 5)}
    for r, cols in eye.items():
        for c in cols:
            field[r][c] = "C"
    field[3][4] = "K"
    for r, cols in {2: [13], 3: [12, 13, 14], 4: [13]}.items():
        for c in cols:
            field[r][c] = "O"
    rows += ["".join(r) for r in field]
    rows += ["".join(k if i % 2 == 0 else s for i in range(W)), s * W]
    return rows


def woven_band(x, top, width, height, selvedge, letters):
    """One pixel-grid tile in a <pattern>, repeated a whole number of times across the band."""
    colours = {"K": GOAT, "C": UNDYED, "R": MADDER_DARK, "O": OCHRE, "N": letters}
    rows = madd_rows(selvedge)
    h, w = len(rows), len(rows[0])
    n = max(1, round(width / (height * w / h)))
    tile_w = width / n
    rects = []
    for y, row in enumerate(rows):
        xi = 0
        while xi < w:
            ch, run = row[xi], 1
            while xi + run < w and row[xi + run] == ch:
                run += 1
            rects.append(f'<rect x="{xi}" y="{y}" width="{run}" height="1" fill="{colours[ch]}"/>')
            xi += run
    sx, sy = tile_w / w, height / h
    return (
        f'<defs><pattern id="madd" patternUnits="userSpaceOnUse" x="{x:.2f}" y="{top:.2f}" '
        f'width="{tile_w:.3f}" height="{height:.2f}" shape-rendering="crispEdges">'
        f'<g transform="scale({sx:.4f} {sy:.4f})">' + "".join(rects) + "</g></pattern></defs>"
        f'<rect x="{x:.2f}" y="{top:.2f}" width="{width:.2f}" height="{height:.2f}" fill="url(#madd)"/>'
    )


def build(ttfont, hbfont, stretch_em, letters, band):
    upem = ttfont["head"].unitsPerEm
    overlap = 0.235 * upem
    # tatweel stroke: the band is exactly as tall as the letters' own kashida
    tat = ttfont.getBestCmap()[0x0640]
    from fontTools.pens.boundsPen import BoundsPen

    bp = BoundsPen(ttfont.getGlyphSet())
    ttfont.getGlyphSet()[tat].draw(bp)
    stroke = bp.bounds[3] - bp.bounds[1]

    left_i, left_p = shape(hbfont, "ـسنا")  # leftmost in RTL: ends the word
    right_i, right_p = shape(hbfont, "مجلـ")  # rightmost: starts the word
    left_d, w_left = outline(ttfont, left_i, left_p, 0)
    stretch = stretch_em * upem
    band_x = w_left - overlap
    right_x = band_x + stretch - overlap
    right_d, w_right = outline(ttfont, right_i, right_p, right_x)
    total = right_x + w_right

    asc, desc = 1000, 520  # tight box around Reem Kufi's meem tail and lam top
    vb = f"0 {-asc} {total:.0f} {asc + desc}"
    if band == "woven-night":
        band_svg = woven_band(band_x, -stroke, stretch, stroke, "N", letters)
    elif band == "woven-day":
        band_svg = woven_band(band_x, -stroke, stretch, stroke, "K", letters)
    else:
        thread = 0.047 * upem  # 1.5 px at a 32 px lockup
        band_svg = (
            f'<rect x="{band_x:.1f}" y="{-stroke:.1f}" width="{stretch:.1f}" height="{stroke:.1f}" fill="{letters}"/>'
            f'<rect x="{band_x:.1f}" y="{-stroke / 2 - thread / 2:.1f}" width="{stretch:.1f}" height="{thread:.1f}" fill="#b0402c"/>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img" aria-label="مجلسنا Majlisna">'
        f'<title>Majlisna</title>'
        f'<path fill="{letters}" d="{left_d}"/><path fill="{letters}" d="{right_d}"/>{band_svg}</svg>\n'
    )


def main():
    ttfont, data = load_font()
    hbfont = hb.Font(hb.Face(data))
    OUT.mkdir(parents=True, exist_ok=True)
    variants = {
        "wordmark-night.svg": (1.5, CREAM, "woven-night"),
        "wordmark-day.svg": (1.5, INK, "woven-day"),
        "wordmark-gold.svg": (0.95, BRASS, "ink"),
        "wordmark-ink.svg": (0.95, INK, "ink"),
    }
    for name, (stretch, letters, band) in variants.items():
        (OUT / name).write_text(build(ttfont, hbfont, stretch, letters, band))
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
