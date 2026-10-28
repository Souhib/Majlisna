import { type ReactNode } from "react"

/** Arabic diacritics (harakat, tatweel) and case are ignored when looking for the term. */
const IGNORABLE = /[ؐ-ًؚ-ٰٟۖ-ۭـ]/

/**
 * Returns `text` with the first occurrence of `term` set in bold (the explanation names
 * the right answer: sketch C, "Ubayy ibn Kaʿb was among the scribes…"). Diacritics,
 * tatweel and case are ignored while matching, so "بغداد" finds "بغدادَ"; the text itself
 * is returned unchanged, character for character, only split around the match. When
 * the term is not there, the text comes back as is.
 */
export function emphasize(text: string, term: string | null | undefined): ReactNode {
  const needle = normalize(term ?? "").trim()
  if (needle.length < 2) return text

  // Build the normalised haystack and remember where each of its characters came from.
  let hay = ""
  const origin: number[] = []
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (IGNORABLE.test(ch)) continue
    hay += lower(ch)
    origin.push(i)
  }
  const at = hay.indexOf(needle)
  if (at < 0) return text

  const start = origin[at]
  let end = origin[at + needle.length - 1] + 1
  // keep the match's trailing harakat with it
  while (end < text.length && IGNORABLE.test(text[end])) end++

  return (
    <>
      {text.slice(0, start)}
      <b>{text.slice(start, end)}</b>
      {text.slice(end)}
    </>
  )
}

function normalize(value: string) {
  let out = ""
  for (let i = 0; i < value.length; i++) if (!IGNORABLE.test(value[i])) out += lower(value[i])
  return out
}

/** Lower case that never changes a character's length (the index map depends on it). */
function lower(ch: string) {
  const low = ch.toLowerCase()
  return low.length === ch.length ? low : ch
}
