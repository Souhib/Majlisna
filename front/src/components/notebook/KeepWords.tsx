import { Link } from "@tanstack/react-router"
import { Book, BookCheck, BookmarkCheck, BookmarkPlus } from "lucide-react"
import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { ColophonWordList, type ColophonWord } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { arabicOf } from "./entries"
import type { ColophonNotebook } from "./use-colophon-notebook"

/**
 * "Keep the words" (sketch H): the colophon's primary brass action while some word of
 * the game is not in the notebook yet; once all are, it becomes "Kept in your
 * kunnash", a link to /notebook. Nothing at all for a spectator, an MCQ game, or
 * while the game's words are not loaded.
 *
 * When the player kept them from here, focus follows the button to the link that
 * replaces it, so a keyboard user is not dropped on <body>.
 */
export function KeepWordsAction({ notebook }: { notebook: ColophonNotebook }) {
  const { t } = useTranslation()
  const linkRef = useRef<HTMLAnchorElement>(null)
  const keptFromHere = useRef(false)

  useEffect(() => {
    if (!notebook.allKept || !keptFromHere.current) return
    keptFromHere.current = false
    linkRef.current?.focus()
  }, [notebook.allKept])

  if (!notebook.available) return null

  if (notebook.allKept) {
    return (
      <Button asChild variant="secondary" iconStart={<BookCheck aria-hidden="true" />}>
        <Link ref={linkRef} to="/notebook">
          {t("notebook.colophon.kept")}
        </Link>
      </Button>
    )
  }

  return (
    <Button
      iconStart={<Book aria-hidden="true" />}
      loading={notebook.keepingAll}
      onClick={() => {
        keptFromHere.current = true
        void notebook.keepAll()
      }}
    >
      {t("notebook.colophon.keep")}
    </Button>
  )
}

/**
 * One word's keep toggle at the end of its colophon row: a bookmark, brass once kept.
 * A real toggle (`aria-pressed`) whose name says which word it keeps; un-keeping
 * deletes the notebook entry by its id.
 */
export function KeepWordToggle({
  notebook,
  word,
  label,
}: {
  notebook: ColophonNotebook
  /** The word as the game names it (the Latin key the notebook matches on). */
  word: string | null | undefined
  /** The word as the player reads it, for the accessible name. */
  label: string
}) {
  const { t } = useTranslation()
  const entry = notebook.find(word)
  if (!notebook.available || !entry) return null
  const busy = notebook.isBusy(entry.word)
  const name = t("notebook.colophon.keepWord", { word: label })
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-pressed={entry.kept}
      aria-label={name}
      title={name}
      aria-busy={busy || undefined}
      data-testid="notebook-keep-word"
      onClick={() => {
        if (!busy) void notebook.toggle(entry)
      }}
      className={cn("-me-2", entry.kept ? "text-brass" : "text-muted-foreground hover:text-foreground")}
    >
      {entry.kept ? <BookmarkCheck aria-hidden="true" /> : <BookmarkPlus aria-hidden="true" />}
    </Button>
  )
}

/**
 * The colophon's word list built from the notebook's read (Kalimat: the game state
 * only ever holds the current round's answer). Amiri Arabic, the word as the game
 * showed it in the player's language (never a transliteration in the Arabic UI), its
 * meaning, and the keep toggle. Bare warp rows while it loads.
 */
export function GameWordsList({ notebook, className }: { notebook: ColophonNotebook; className?: string }) {
  const { t, i18n } = useTranslation()
  const arabicUi = (i18n.language ?? "").startsWith("ar")

  if (notebook.isLoading) {
    return (
      <div className={className} aria-busy="true">
        <p className="sr-only" role="status">
          {t("notebook.colophon.loadingWords")}
        </p>
        <div className="border-t border-line-brass">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-[18px] border-b border-line py-3">
              <Skeleton className="h-10 w-16" />
              <div className="grid flex-1 gap-2">
                <Skeleton className="h-3.5 w-28" />
                <Skeleton className="h-3 w-3/4" />
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!notebook.words?.length) return null

  const rows: ColophonWord[] = notebook.words.map((w) => {
    const ar = arabicOf(w)
    const display = w.word_display?.trim() || w.word
    // the Arabic UI reads the Arabic; elsewhere the word as the game showed it, unless it is that same Arabic
    const showDisplay = !(arabicUi && ar) && display !== ar && display !== w.word_ar
    return {
      word: ar,
      translit: showDisplay ? display : undefined,
      meaning: w.hint ? <span dir="auto">{w.hint}</span> : undefined,
      action: <KeepWordToggle notebook={notebook} word={w.word} label={arabicUi && ar ? ar : display} />,
    }
  })

  return <ColophonWordList words={rows} className={className} />
}
