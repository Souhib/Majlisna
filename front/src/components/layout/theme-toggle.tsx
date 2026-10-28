import { Moon, Sun } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { useResolvedTheme } from "@/hooks/use-resolved-theme"
import { trackEvent } from "@/lib/analytics"
import { cn } from "@/lib/utils"
import { useTheme } from "@/providers/ThemeProvider"

/**
 * Night ↔ afternoon. The icon shows where the switch takes you (a sun at night, a moon
 * in the afternoon), the label says it. `labelled` (the menu sheet) adds the text.
 */
export function ThemeToggle({ labelled = false, className }: { labelled?: boolean; className?: string }) {
  const { t } = useTranslation()
  const { setTheme } = useTheme()
  const resolved = useResolvedTheme()
  const next = resolved === "dark" ? "light" : "dark"
  const label = next === "light" ? t("nav.themeToDay") : t("nav.themeToNight")
  const Icon = next === "light" ? Sun : Moon

  const toggle = () => {
    trackEvent("theme-change", { theme: next })
    setTheme(next)
  }

  if (labelled) {
    return (
      <Button variant="secondary" block className={className} iconStart={<Icon aria-hidden="true" />} onClick={toggle}>
        {label}
      </Button>
    )
  }
  return (
    <button type="button" onClick={toggle} aria-label={label} title={label} className={cn("nav-iconbtn", className)}>
      <Icon aria-hidden="true" />
    </button>
  )
}
