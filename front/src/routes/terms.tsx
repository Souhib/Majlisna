import { createFileRoute } from "@tanstack/react-router"
import { LegalPage } from "@/components/about/LegalPage"

export const Route = createFileRoute("/terms")({
  component: TermsPage,
})

/**
 * The terms of use (`terms.*`, owner request of 3 November 2026), the same Read page as
 * the privacy policy (components/about/LegalPage), which its "Your data" section links.
 * They state only what the code and PRODUCT.md hold: no governing law, court, minimum age
 * or company until the owner decides them (front/CLAUDE.md, "Terms of use").
 */
function TermsPage() {
  return <LegalPage ns="terms" />
}
