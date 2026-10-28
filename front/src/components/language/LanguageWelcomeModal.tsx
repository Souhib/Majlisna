import { type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Lockup } from "@/components/brand"
import { applyLanguage, currentLanguage, LANGUAGES, type LanguageCode } from "@/components/layout/language-switch"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

const STORAGE_KEY = "majlisna-first-visit-complete"

function readFirstVisit() {
  try {
    return !localStorage.getItem(STORAGE_KEY)
  } catch {
    return false
  }
}

function useFirstVisit() {
  const [isFirstVisit, setIsFirstVisit] = useState(readFirstVisit)

  const markComplete = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, "true")
    } catch {
      // private mode: we will ask again next visit
    }
    setIsFirstVisit(false)
  }, [])

  return { isFirstVisit, markComplete }
}

/**
 * First visit: which language? Asked once, in all three languages at the same time
 * (each line in its own language, so nobody has to read the others), then remembered.
 * Three large choices, a lozenge on the one chosen, and "Skip" keeps the detected one.
 */
export function LanguageWelcomeModal() {
  const { t, i18n } = useTranslation()
  const { isFirstVisit, markComplete } = useFirstVisit()
  const [selected, setSelected] = useState<LanguageCode | null>(null)
  const [, setLoaded] = useState(0)
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([])
  const current = currentLanguage(i18n.language)

  // The prompt is shown in every language: make sure all three are loaded.
  useEffect(() => {
    if (!isFirstVisit) return
    const loader = (i18n as { loadLanguages?: (lngs: string[]) => Promise<unknown> }).loadLanguages
    loader?.call(i18n, ["en", "fr", "ar"]).then(() => setLoaded((n) => n + 1))
  }, [isFirstVisit, i18n])

  const handleSelect = useCallback(
    (code: LanguageCode) => {
      setSelected(code)
      applyLanguage(i18n, code)
      // let the chosen lozenge register before the dialog closes
      window.setTimeout(markComplete, 320)
    },
    [i18n, markComplete],
  )

  const onKeyDown = (e: KeyboardEvent, index: number) => {
    const forward = e.key === "ArrowDown" || (e.key === "ArrowRight" && document.dir !== "rtl") || (e.key === "ArrowLeft" && document.dir === "rtl")
    const back = e.key === "ArrowUp" || (e.key === "ArrowLeft" && document.dir !== "rtl") || (e.key === "ArrowRight" && document.dir === "rtl")
    if (!forward && !back) return
    e.preventDefault()
    const next = (index + (forward ? 1 : -1) + LANGUAGES.length) % LANGUAGES.length
    optionRefs.current[next]?.focus()
  }

  const fixed = (code: LanguageCode) => {
    const getFixedT = (i18n as { getFixedT?: (lng: string) => (key: string) => string }).getFixedT
    return getFixedT ? getFixedT.call(i18n, code)("ui.chooseLanguage") : t("ui.chooseLanguage")
  }

  if (!isFirstVisit) return null
  const checked = selected ?? current

  return (
    <Dialog open onOpenChange={(open) => !open && markComplete()}>
      <DialogContent hideClose className="max-w-md gap-6 p-6 sm:p-8">
        <div className="grid justify-items-center gap-4 text-center">
          <DialogTitle className="sr-only">Majlisna</DialogTitle>
          <Lockup size={34} />
          <DialogDescription asChild>
            <div className="grid gap-1 text-muted-foreground">
              {LANGUAGES.map((lang) => (
                <span key={lang.code} lang={lang.code} dir={lang.dir} className={lang.code === "ar" ? "text-[18px]" : "text-[15px]"}>
                  {fixed(lang.code)}
                </span>
              ))}
            </div>
          </DialogDescription>
        </div>

        <div role="radiogroup" aria-label={t("nav.switchLanguage")} className="grid gap-2">
          {LANGUAGES.map((lang, index) => {
            const isChecked = checked === lang.code
            return (
              <button
                key={lang.code}
                ref={(el) => {
                  optionRefs.current[index] = el
                }}
                type="button"
                role="radio"
                aria-checked={isChecked}
                tabIndex={isChecked ? 0 : -1}
                lang={lang.code}
                dir={lang.dir}
                onClick={() => handleSelect(lang.code)}
                onKeyDown={(e) => onKeyDown(e, index)}
                className={cn(
                  "flex min-h-14 items-center gap-3 rounded-sm border px-4 text-start transition-colors duration-(--dur-state)",
                  "hover:bg-[color-mix(in_oklch,var(--brass)_8%,transparent)]",
                  isChecked ? "border-line-brass-strong bg-surface-2" : "border-line",
                )}
              >
                <span aria-hidden="true" className={cn("loz [--loz:9px]", isChecked ? "bg-brass" : "border border-line-brass-strong")} />
                <span className={cn("flex-1 font-medium", lang.code === "ar" ? "text-[20px]" : "text-[17px]")}>{lang.name}</span>
              </button>
            )
          })}
        </div>

        <Button variant="ghost" size="sm" className="justify-self-center text-muted-foreground" onClick={markComplete}>
          {t("ui.skip")}
        </Button>
      </DialogContent>
    </Dialog>
  )
}
