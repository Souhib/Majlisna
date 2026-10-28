import type { NotebookEntryView, NotebookGameType } from "@/api/generated"
import { latnLocale } from "@/components/stats/format"

/**
 * Pure helpers of the /notebook page, kept free of React so they are unit-tested on
 * their own (`__tests__/entries.test.ts`).
 */

/** The page's h1 (focusable with tabindex=-1): where focus goes when nothing else is left. */
export const NOTEBOOK_TITLE_ID = "notebook-title"

/** A run of entries kept from the same game on the same day, newest first. */
export interface EntryGroup {
  key: string
  gameType: NotebookGameType
  /** When the newest entry of the run was kept (ISO). */
  keptAt: string
  entries: NotebookEntryView[]
}

/** The local calendar day of an ISO timestamp ("2026-10-28"), "" when unreadable. */
export function localDay(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/**
 * Group the newest-first listing into runs: consecutive entries from one game, kept the
 * same day, share a heading (a Codenames board kept at once is 25 entries with the
 * same game and the same instant; saying it 25 times is noise). Order is kept as is:
 * a game whose words were kept on two days, with other words between, gives two runs.
 * An entry whose game was deleted (no `source_game_id`) groups by its game type.
 */
export function groupEntries(entries: NotebookEntryView[]): EntryGroup[] {
  const groups: EntryGroup[] = []
  for (const entry of entries) {
    const source = entry.source_game_id ?? `type:${entry.game_type}`
    const runKey = `${source}|${localDay(entry.kept_at)}`
    const last = groups.at(-1)
    if (last && last.key.startsWith(`${runKey}#`)) {
      last.entries.push(entry)
      continue
    }
    groups.push({ key: `${runKey}#${groups.length}`, gameType: entry.game_type, keptAt: entry.kept_at, entries: [entry] })
  }
  return groups
}

/** Drop repeated ids (a page boundary that moved under a concurrent keep), first one wins. */
export function uniqueEntries(entries: NotebookEntryView[]): NotebookEntryView[] {
  const seen = new Set<string>()
  return entries.filter((entry) => {
    if (seen.has(entry.id)) return false
    seen.add(entry.id)
    return true
  })
}

/** "28 October 2026" in the interface language, with Western digits like every other date. */
export function formatKeptDate(iso: string, lang: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  return new Intl.DateTimeFormat(latnLocale(lang), { day: "numeric", month: "long", year: "numeric" }).format(date)
}

/** The Arabic form to show: the vocalised one when the server has it. */
export function arabicOf(word: { word_ar?: string | null; word_ar_vocalized?: string | null }): string | undefined {
  return word.word_ar_vocalized?.trim() || word.word_ar?.trim() || undefined
}

/** How an entry reads: the Arabic headword, and the word as its game showed it (when it adds something). */
export function entryForms(entry: NotebookEntryView, arabicUi: boolean): { arabic?: string; display?: string; label: string } {
  const arabic = arabicOf(entry)
  const shown = entry.word_display?.trim() || entry.word
  // the Arabic UI reads the Arabic (no transliteration); elsewhere the game's own word, unless it is that same Arabic
  const display = (arabicUi && arabic) || shown === arabic || shown === entry.word_ar ? undefined : shown
  return { arabic, display, label: arabicUi && arabic ? arabic : shown }
}
