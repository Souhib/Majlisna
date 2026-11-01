import { useTranslation } from "react-i18next"
import { trackEvent } from "@/lib/analytics"
import { cn } from "@/lib/utils"

/**
 * The language switch of the sketch's nav: EN FR ع, the current one framed by a brass
 * hairline. One tap changes the language (no menu to open). Each button is named by the
 * language's own name ("Français", "العربية") and the group by "Switch language".
 *
 * variant="full" (the menu sheet) spells the names out in three equal segments.
 */
export const LANGUAGES = [
  { code: "en", short: "EN", name: "English", dir: "ltr" },
  { code: "fr", short: "FR", name: "Français", dir: "ltr" },
  { code: "ar", short: "ع", name: "العربية", dir: "rtl" },
] as const

export type LanguageCode = (typeof LANGUAGES)[number]["code"]

/** One of the three interface languages, from any tag: "ar-SA" → "ar", "fr_CA" → "fr", else "en". */
export function currentLanguage(language: string | undefined): LanguageCode {
  const part = language?.trim().split(/[-_]/)[0].toLowerCase()
  return LANGUAGES.find((l) => l.code === part)?.code ?? "en"
}

/** <html dir/lang> for a language, from its normalised code (never `=== "ar"` on a raw tag). */
export function syncDocumentLanguage(language: string | undefined) {
  const lang = LANGUAGES.find((l) => l.code === currentLanguage(language)) ?? LANGUAGES[0]
  document.documentElement.dir = lang.dir
  document.documentElement.lang = lang.code
}

/** Apply a language everywhere it lives: i18next, storage, and <html dir/lang>. */
export function applyLanguage(i18n: { changeLanguage: (lng: string) => unknown }, code: LanguageCode) {
  const lang = LANGUAGES.find((l) => l.code === code)
  if (!lang) return
  i18n.changeLanguage(lang.code)
  try {
    localStorage.setItem("majlisna-language", lang.code)
  } catch {
    // private mode: the choice lasts for this visit only
  }
  syncDocumentLanguage(lang.code)
}

export function LanguageSwitch({ variant = "short", className }: { variant?: "short" | "full"; className?: string }) {
  const { t, i18n } = useTranslation()
  const current = currentLanguage(i18n.language)

  return (
    <div role="group" aria-label={t("nav.switchLanguage")} className={cn("lang-switch", className)} data-variant={variant}>
      {LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          type="button"
          lang={lang.code}
          dir={lang.dir}
          aria-pressed={current === lang.code}
          onClick={() => {
            // Only the exact code is a no-op: a regional tag left over from before the
            // detection was normalised (ar-SA) reads as current, and the tap repairs it.
            if (i18n.language === lang.code) return
            if (current !== lang.code) trackEvent("language-change", { lang: lang.code })
            applyLanguage(i18n, lang.code)
          }}
        >
          {variant === "short" ? (
            <>
              <span aria-hidden="true">{lang.short}</span>
              <span className="sr-only">{lang.name}</span>
            </>
          ) : (
            lang.name
          )}
        </button>
      ))}
    </div>
  )
}
