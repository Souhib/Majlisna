import { Link } from "@tanstack/react-router"
import { ArrowRight } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { useDocumentTitle } from "@/hooks/use-document-title"

/**
 * 404: the Marcellus line, a sentence that says what probably happened, and the way
 * back. No giant brass "404": brass is for what is yours or actionable, which a status
 * code is not, and the sentence already says it.
 */
export function NotFound() {
  const { t } = useTranslation()
  useDocumentTitle(t("ui.notFoundTitle"))

  return (
    <div className="page-wrap grid min-h-[60vh] place-items-center py-20">
      <div className="grid max-w-md justify-items-center text-center">
        <h1 className="type-title">{t("ui.notFoundTitle")}</h1>
        <Separator className="my-6 w-40" />
        <p className="text-[16px] text-muted-foreground text-pretty">{t("ui.notFoundBody")}</p>
        <Button asChild className="mt-8" iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}>
          <Link to="/">{t("common.goHome")}</Link>
        </Button>
      </div>
    </div>
  )
}
