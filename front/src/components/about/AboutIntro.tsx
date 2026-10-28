import { Trans, useTranslation } from "react-i18next"
import { currentLanguage } from "@/components/layout/language-switch"
import { READ_RAILS } from "./rails"

/**
 * What Majlisna is: the page title (with its Arabic echo in Amiri brass on the English
 * and French pages, as the home's section titles have), then the samar, the four games
 * and the three languages, at a reading measure.
 */
export function AboutIntro() {
  const { t, i18n } = useTranslation()
  const arabic = currentLanguage(i18n.language) === "ar"

  return (
    <header className={READ_RAILS}>
      <div className="grid content-start gap-2">
        <h1 className="type-h2">{t("about.title")}</h1>
        {arabic ? null : (
          <p className="type-arabic-name text-[clamp(26px,2.4vw,36px)]" aria-hidden="true">
            <span lang="ar" dir="rtl">
              {t("about.titleArabic")}
            </span>
          </p>
        )}
      </div>
      <div className="grid max-w-[54ch] content-start gap-5 md:pt-2">
        <p className="type-lede">
          <Trans
            i18nKey="about.lede"
            components={{
              ar: <span lang="ar" dir="rtl" className="bidi-isolate font-nass text-[1.12em] leading-none text-brass" />,
              em: <em className="text-foreground not-italic" />,
            }}
          />
        </p>
        <p className="type-body text-pretty">{t("about.games")}</p>
        <p className="type-body text-pretty">{t("about.languages")}</p>
      </div>
    </header>
  )
}
