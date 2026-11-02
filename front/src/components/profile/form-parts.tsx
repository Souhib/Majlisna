import type { KeyboardEvent } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"

/**
 * Escape leaves the form without saving. A key pressed in a portalled layer of the form
 * (the country list) bubbles here through React, but that Escape only closes the list.
 */
export function escapeTo(cancel: () => void) {
  return (e: KeyboardEvent<HTMLFormElement>) => {
    if (e.key !== "Escape" || e.defaultPrevented) return
    if (!e.currentTarget.contains(e.target as Node)) return
    e.stopPropagation()
    cancel()
  }
}

/** Save and Cancel, under each of the profile's in-place forms. */
export function FormActions({ busy, onCancel }: { busy: boolean; onCancel: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap gap-2.5">
      <Button type="submit" size="sm" loading={busy}>
        {t("common.save")}
      </Button>
      <Button variant="secondary" size="sm" onClick={onCancel}>
        {t("common.cancel")}
      </Button>
    </div>
  )
}
