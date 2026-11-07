import { createFileRoute } from "@tanstack/react-router"
import { LegalPage, LegalText } from "@/components/about/LegalPage"

export const Route = createFileRoute("/privacy")({
  component: PrivacyPage,
})

/**
 * The privacy policy (`privacy.*`), a Read page shared with the terms of use
 * (components/about/LegalPage). The policy describes the code as it is: every flow it
 * names (prayer-time location services, browser storage, cookies, providers) was checked
 * in the code, and a change to one of them changes this text (front/CLAUDE.md, "Privacy").
 * Under the contact line, a link to the terms of use.
 */
function PrivacyPage() {
  return (
    <LegalPage
      ns="privacy"
      after={
        <p className="type-body text-pretty">
          <LegalText i18nKey="privacy.seeTerms" />
        </p>
      }
    />
  )
}
