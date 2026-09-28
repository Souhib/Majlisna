import { createFileRoute } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

export const Route = createFileRoute("/privacy")({
  component: PrivacyPage,
})

interface PrivacySection {
  title: string
  body: string[]
}

function PrivacyPage() {
  const { t } = useTranslation()
  const sections = t("privacy.sections", { returnObjects: true }) as PrivacySection[]

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="text-3xl font-extrabold tracking-tight">{t("privacy.title")}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("privacy.updated")}</p>
      <p className="mt-6 leading-relaxed">{t("privacy.intro")}</p>
      {sections.map((section) => (
        <section key={section.title} className="mt-8">
          <h2 className="text-xl font-bold">{section.title}</h2>
          {section.body.map((paragraph) => (
            <p key={paragraph} className="mt-3 leading-relaxed text-muted-foreground">
              {paragraph}
            </p>
          ))}
        </section>
      ))}
      <p className="mt-10 text-sm">
        {t("privacy.contact")}{" "}
        <a href="mailto:souhib.t@icloud.com" className="font-medium text-primary hover:underline">
          souhib.t@icloud.com
        </a>
      </p>
    </div>
  )
}
