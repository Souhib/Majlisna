/**
 * Self-hosted web fonts for the Samar design system (see DESIGN.md, "Type").
 *
 * They used to come from the Google Fonts CDN, which sent every visitor's IP to
 * Google and forced the enforced CSP to allow fonts.googleapis.com and
 * fonts.gstatic.com. Bundling them lets the policy stay `'self'`.
 *
 * Arabic is loaded in EVERY language: Arabic game names, revealed words and the
 * wordmark appear in the English and French interfaces too. Each import declares
 * per-script `unicode-range` subsets, so a browser fetches only the files for the
 * scripts a page actually renders (an English page with no Amiri text downloads no
 * Amiri at all). Only the weights the type roles use are imported.
 *
 *   Readex Pro (variable 160–700) — every control, both scripts, every figure
 *   Reem Kufi  (variable 400–700) — the wordmark and the giant name, 700 only in use
 *   Marcellus  400                — Latin display titles and the lockup
 *   Amiri      400 / 700          — revealed words, Arabic names and titles, explanations
 *   Aref Ruqaa 700                — what players wrote (descriptions, clues, answers)
 */
import "@fontsource-variable/readex-pro"
import "@fontsource-variable/reem-kufi"
import "@fontsource/marcellus/400.css"
import "@fontsource/amiri/400.css"
import "@fontsource/amiri/700.css"
import "@fontsource/aref-ruqaa/700.css"

import readexLatinUrl from "@fontsource-variable/readex-pro/files/readex-pro-latin-wght-normal.woff2?url"

/**
 * "Samar Figures": Readex Pro's digits, registered under their own family with a
 * digits-only unicode-range and placed FIRST in the display stack (--font-display).
 *
 * Marcellus's 1 is an I with a flag: "1+" read "I+" and "4–10" read "4–IO" in the
 * sketch. With this face in front, any figure inside a Marcellus title (a score, a
 * round number, "Players (5)") is drawn by Readex, while letters stay Marcellus.
 * Registered from JS because the woff2 URL has to go through Vite's asset pipeline.
 *
 * The face is registered with ONE weight: a single-value `weight` descriptor clamps the
 * variable font's `wght` axis to it, whatever weight the title asks for. It used to
 * declare the whole 160–700 range, so a Marcellus title (400) drew its digits at Readex
 * 400 and they looked bolder than the letters around them ("Bilalbd1 wins!"); an Arabic
 * title (700) drew them at 700. Figures are Latin characters, and in every title they
 * sit in a Latin run (a username, "Players (5)") set in Marcellus, so they take
 * Marcellus's stem in every language.
 *
 * Titles set `font-synthesis-weight: none` (h1/h2, the type-* roles, `.font-display`):
 * Chrome would otherwise fake a bold on these digits for a 700 request.
 */
export const DISPLAY_FIGURES_WEIGHT = 280

function registerDisplayFigures() {
  if (typeof document === "undefined" || !("fonts" in document) || typeof FontFace === "undefined") return
  try {
    const face = new FontFace("Samar Figures", `url(${readexLatinUrl}) format("woff2")`, {
      weight: String(DISPLAY_FIGURES_WEIGHT),
      style: "normal",
      display: "swap",
      unicodeRange: "U+0030-0039",
      featureSettings: '"tnum" 1, "lnum" 1',
    })
    document.fonts.add(face)
  } catch {
    // An unsupported descriptor only costs the figure substitution; titles still render.
  }
}

registerDisplayFigures()
