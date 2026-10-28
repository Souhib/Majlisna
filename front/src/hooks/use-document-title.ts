import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { pushTitle } from "@/lib/document-title"

/**
 * Name the page for the document title, "<title> · Majlisna" in the page's language
 * (lib/document-title). Pass nothing while the name is not known yet: the route's
 * fallback title stands meanwhile.
 */
export function useDocumentTitle(title: string | null | undefined): void {
  const { t } = useTranslation()
  const full = title ? t("meta.pageTitle", { title }) : null
  useEffect(() => {
    if (!full) return
    return pushTitle(full)
  }, [full])
}
