import i18n from "i18next"
import LanguageDetector from "i18next-browser-languagedetector"
import resourcesToBackend from "i18next-resources-to-backend"
import { initReactI18next } from "react-i18next"

export const defaultNS = "translation"

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .use(
    resourcesToBackend(
      (language: string) => import(`./locales/${language}.json`),
    ),
  )
  .init({
    fallbackLng: "en",
    defaultNS,
    interpolation: {
      escapeValue: false, // React already escapes
    },
    detection: {
      order: ["localStorage", "cookie", "navigator", "htmlTag"],
      caches: ["localStorage"],
      lookupLocalStorage: "ipg-language",
      lookupCookie: "ipg-lang",
    },
  })

export default i18n
