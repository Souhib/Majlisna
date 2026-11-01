import i18next from "i18next"
import LanguageDetector from "i18next-browser-languagedetector"
import resourcesToBackend from "i18next-resources-to-backend"
import { initReactI18next } from "react-i18next"

export const defaultNS = "translation"

/** The three interface languages. i18n.language is always exactly one of them. */
export const SUPPORTED_LANGUAGES = ["en", "fr", "ar"] as const

const LANGUAGE_STORAGE_KEY = "majlisna-language"
const RELOAD_GUARD_KEY = "majlisna-locale-reload"

/** "ar-SA" → "ar", "fr_CA" → "fr", "EN" → "en": the language part of a tag, lower-cased. */
function languagePart(tag: string): string {
  return tag.trim().split(/[-_]/)[0].toLowerCase()
}

function reloadPage() {
  window.location.reload()
}

/**
 * Import one locale chunk. After a deploy that changed a locale, an open tab still names the
 * old hashed chunk, which now answers 404: the language switch then stored the new language
 * and showed nothing. A failed import reloads the page once (a sessionStorage guard, like
 * TanStack Router's own chunk reload), so the fresh index.html names the new chunk; a
 * failure right after that reload is left to fail, never looped. Any successful load
 * re-arms the guard for the next deploy.
 */
export function loadLocale(language: string, reload: () => void = reloadPage) {
  const guard = RELOAD_GUARD_KEY
  return import(`./locales/${language}.json`).then(
    (locale) => {
      try {
        sessionStorage.removeItem(guard)
      } catch {
        // storage blocked: nothing to re-arm
      }
      return locale
    },
    (error: unknown) => {
      let alreadyReloaded = true
      try {
        alreadyReloaded = sessionStorage.getItem(guard) !== null
        if (!alreadyReloaded) sessionStorage.setItem(guard, "1")
      } catch {
        // storage blocked: without a guard a reload could loop, so do not reload
      }
      if (alreadyReloaded) console.warn(`Locale "${language}" failed to load again after a reload`, error)
      else reload()
      throw error
    },
  )
}

/**
 * Its own instance (react-i18next picks it up through initReactI18next), so a test can boot
 * the module afresh as a page load does.
 */
const i18n = i18next.createInstance()

/**
 * Language detection is normalised to the three interface languages. Phones send regional
 * tags (ar-SA, fr-FR), and the raw tag used to become i18n.language: an Arabic page laid
 * out left to right, `?lang=ar-SA` answered with English content, and the tag cached in
 * localStorage for good.
 *
 * - `supportedLngs` makes every changeLanguage resolve to en, fr or ar (fr-CA → fr). The
 *   planner's `load: "languageOnly"` / `nonExplicitSupportedLngs: true` are deliberately NOT
 *   set: with either, i18next counts "fr-FR" itself as supported and keeps it as
 *   i18n.language.
 * - `convertDetectedLanguage` strips the region before i18next sees it, and the detector then
 *   caches the bare code: a stored "fr-FR" from before this fix is rewritten to "fr" on the
 *   first load.
 * - Each language falls back only to itself, so a French or Arabic page never downloads the
 *   English chunk. Safe because the locale parity test fails on any key missing in fr or ar.
 *
 * `i18nReady` settles once the first locale is loaded (what a test awaits after a boot).
 */
export const i18nReady = i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .use(resourcesToBackend((language: string) => loadLocale(language)))
  .init({
    supportedLngs: [...SUPPORTED_LANGUAGES],
    fallbackLng: { fr: [], ar: [], default: ["en"] },
    defaultNS,
    interpolation: {
      escapeValue: false, // React already escapes
    },
    detection: {
      order: ["localStorage", "cookie", "navigator", "htmlTag"],
      caches: ["localStorage"],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      lookupCookie: "majlisna-lang",
      convertDetectedLanguage: languagePart,
    },
  })

export default i18n
