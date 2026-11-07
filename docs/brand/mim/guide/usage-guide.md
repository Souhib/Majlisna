# Majlisna — the Mīm: usage guide (one page)

The picture of this page: `majlisna-mim-usage-guide.png` (SVG beside it).

## The mark
The mīm (مـ), first letter of مجلسنا in the wordmark's Kufi. Its loop is the halqa (the circle, the one
place), its counter is the nuqṭa (the lozenge, the only geometry), its baseline is the kashida with the
madder thread, exactly as in the wordmark's lām–sīn joint. It joins to the LEFT, into the name: the RTL
flow of مجلسنا. Mirrored, it would join to the right and stop being the first letter of the name.

Versions: symbol (colour with thread, one colour, thinned for dark grounds), small cut (≤ 32 px, one colour,
no thread), horizontal lockup (name, then the mark at the Arabic reading start, the right), stacked lockup
(mark over name). The wordmark alone (the live `Lockup`) stays the nav and footer identity.

## Clear space
One nuqṭa all round: the diagonal of the lozenge counter, measured at the size in use (96 units on the
256 master, about 55 % of the mark's height). In the horizontal lockup the same nuqṭa separates the name
from the mark; closer, the mark's kashida reads as a letter joined to the name.

## Minimum sizes
| Version | Screen | Print |
|---|---|---|
| Mark, colour (with the thread) | 48 px | 12 mm |
| Mark, small cut (one colour, no thread) | 16–47 px | 5 mm |
| Horizontal lockup (2.72 : 1) | 80 px tall (MAJLISNA caps ≥ 8 px) | 30 mm wide |
| Stacked lockup (1.24 : 1) | 120 px tall | 25 mm wide |

## Colours
| Name | HEX | RGB | CMYK (approximate: proof before print) | DESIGN.md token |
|---|---|---|---|---|
| Brass | `#e3b56b` | 227 181 107 | 0 20 53 11 | `--lockup` / `--brass` at night (oklch .80 .105 77 = `#e4b56d`; the frozen wordmark files use `#e3b56b`) |
| Goat-hair ink | `#1d1613` | 29 22 19 | 0 24 34 89 | `--lockup` / `--text` by day (oklch .21 .016 50 = `#1f1612`); the app icon's tile |
| Madder thread | `#b0402c` | 176 64 44 | 0 64 75 31 | the wordmark's thread (`wordmark.py`), between `--wool-madder` and `--madd-madder` |
| Tent black | `#130d0a` | 19 13 10 | 0 32 47 93 | `--bg` at night; the manifest's `background_color` |
| Gypsum | `#f8f6f3` | 248 246 243 | 0 1 2 3 | `--bg` by day |

No Pantone reference is claimed: match on a printed proof. One-colour versions: black, white, ink, brass.
On dark grounds use the thinned files (`-white`, `-mono-brass`, `-night`, `-night-transparent`): light on
dark looks heavier (each edge moved in by 1.5 units on 256).

## Approved grounds
- Night: brass + thread on tent black (`#130d0a`) or goat-hair ink (`#1d1613`).
- Afternoon: ink + thread on gypsum (`#f8f6f3`), white or sand.
- Black on white; white (thinned) on ink or tent black.
- Photographs (the hero skies): only on a calm dark area, brass or white. On Sadu bands, wool colours or
  busy patterns: the app tile (`#1d1613`, 22 % radius) as a container.

## Don't
Mirror it · rotate it · stretch it · recolour the thread (madder only) · put the thread in the small cut ·
round, fill or cover the counter (it is a lozenge, and it stays open) · outline it · add glow, shadow or
gradient (DESIGN.md bans them) · set the mark to the left of the Arabic name, or closer than one nuqṭa ·
bring back the halqa icon.

## Files and type
Masters: `docs/brand/mim/master/` (symbol), `docs/brand/mim/lockups/`. Web icons: `front/src/assets/brand/app-icon.svg`
and `front/public/favicon.svg`, their rasters in `front/public/` (`front/scripts/brand/render-icons.mjs`).
Type: Reem Kufi 700 (the frozen wordmark's outlines) and Marcellus 400 (MAJLISNA, outlined at the live
Lockup's 0.26 em tracking), both SIL Open Font License 1.1. Trademark search: not done.
