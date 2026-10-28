import { Eraser, Undo2 } from "lucide-react"
import { useEffect, useLayoutEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import type { NotebookEntryView } from "@/api/generated"
import { Button } from "@/components/ui/button"
import { entryForms, NOTEBOOK_TITLE_ID } from "./entries"

interface NotebookEntryRowProps {
  entry: NotebookEntryView
  arabicUi: boolean
  /** In its undo window: the row says it was removed and offers Undo. */
  removed: boolean
  onRemove: (id: string) => void
  onUndo: (id: string) => void
}

/** Focus the eraser of the nearest other entry (after this one first), else the page title. */
function focusNeighbour(from: HTMLElement) {
  const rows = [...document.querySelectorAll<HTMLElement>("[data-notebook-entry]")]
  const at = rows.indexOf(from.closest<HTMLElement>("[data-notebook-entry]") ?? from)
  const order = [...rows.slice(at + 1), ...rows.slice(0, Math.max(at, 0)).reverse()]
  const target = order.map((row) => row.querySelector<HTMLElement>("[data-remove]")).find((el) => el != null)
  ;(target ?? document.getElementById(NOTEBOOK_TITLE_ID))?.focus()
}

/**
 * One kept word, read like a dictionary entry: the Arabic headword large in Amiri
 * (vocalised when the server has it), the word as its game showed it in the
 * interface language (never a transliteration in the Arabic UI), then its meaning at a
 * reading measure. The eraser at the end removes it, with an undo window.
 *
 * Focus is never dropped: removing moves it to Undo, undoing back to the eraser.
 */
export function NotebookEntryRow({ entry, arabicUi, removed, onRemove, onUndo }: NotebookEntryRowProps) {
  const { t } = useTranslation()
  const { arabic, display, label } = entryForms(entry, arabicUi)
  const undoRef = useRef<HTMLButtonElement>(null)
  const removeRef = useRef<HTMLButtonElement>(null)
  const actedHere = useRef(false)

  useEffect(() => {
    if (!actedHere.current) return
    actedHere.current = false
    ;(removed ? undoRef : removeRef).current?.focus()
  }, [removed])

  // The undo window closed with focus on Undo: the row is about to go, so hand focus
  // to the next word's eraser (or the previous one, or the page title). Runs before
  // React takes the row out of the DOM. Not on Undo itself: focus then stays here.
  useLayoutEffect(() => {
    if (!removed) return
    const undo = undoRef.current
    return () => {
      if (actedHere.current || !undo || document.activeElement !== undo) return
      focusNeighbour(undo)
    }
  }, [removed])

  if (removed) {
    return (
      <li data-notebook-entry={entry.id} className="flex min-h-[5.5rem] flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line py-4">
        <p className="text-[1rem] leading-[1.5] text-muted-foreground">
          {t("notebook.removed", { word: label })}
        </p>
        <Button
          ref={undoRef}
          variant="secondary"
          size="sm"
          iconStart={<Undo2 className="rtl-flip" aria-hidden="true" />}
          aria-label={t("notebook.undoNamed", { word: label })}
          onClick={() => {
            actedHere.current = true
            onUndo(entry.id)
          }}
        >
          {t("notebook.undo")}
        </Button>
      </li>
    )
  }

  const removeName = t("notebook.remove", { word: label })
  return (
    <li data-notebook-entry={entry.id} className="flex items-start gap-3 border-b border-line py-4 sm:py-5">
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-baseline gap-x-4">
          {arabic ? (
            <span lang="ar" dir="rtl" className="type-word text-[clamp(2rem,3.2vw,2.5rem)] text-foreground">
              {arabic}
            </span>
          ) : null}
          {display ? (
            <span dir="auto" className="text-[1.0625rem] font-medium leading-snug [overflow-wrap:anywhere]">
              {display}
            </span>
          ) : null}
        </p>
        {entry.hint ? (
          <p dir="auto" className="mt-1 max-w-[58ch] text-[1rem] leading-[1.65] text-muted-foreground text-pretty">
            {entry.hint}
          </p>
        ) : null}
      </div>
      <Button
        ref={removeRef}
        variant="ghost"
        size="icon"
        data-remove=""
        aria-label={removeName}
        title={removeName}
        onClick={() => {
          actedHere.current = true
          onRemove(entry.id)
        }}
        className="-me-2 shrink-0 text-muted-foreground hover:text-foreground"
      >
        <Eraser aria-hidden="true" />
      </Button>
    </li>
  )
}
