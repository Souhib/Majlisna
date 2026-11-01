import { Moon, Sun, SunMoon } from "lucide-react"
import { useId, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { loadStoredCity } from "@/components/prayer-times/CitySelector"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useResolvedTheme } from "@/hooks/use-resolved-theme"
import { trackEvent } from "@/lib/analytics"
import { formatSkyTime, NO_SKY, skyStatus, type SkyStatus } from "@/lib/sky-light"
import { cn } from "@/lib/utils"
import { type Theme, useTheme } from "@/providers/ThemeProvider"

/**
 * The light of the page: the afternoon, the night, or "Follow the sky" (the night from
 * Maghrib to sunrise, from the stored prayer-times city; ThemeProvider). The nav row shows
 * the current choice as an icon that opens a menu of the three; the menu sheet (`labelled`)
 * sets them out as three text segments, like the language switch. Until the player
 * chooses, the device decides and nothing is pressed.
 *
 * The sky's choice says what it will do: when it next turns, at what time in the city
 * ("Night comes at Maghrib, 17:45, in Makkah"), or, with no city stored, that it follows
 * the device's light until one is chosen in the prayer times. It never asks for a city
 * itself. The note is that choice's description (`aria-describedby`); its name stays the
 * choice.
 */
const CHOICES = [
  { value: "light", Icon: Sun },
  { value: "dark", Icon: Moon },
  { value: "sky", Icon: SunMoon },
] as const

type Choice = (typeof CHOICES)[number]["value"]

function isChoice(value: unknown): value is Choice {
  return CHOICES.some((c) => c.value === value)
}

/**
 * The sky choice's note: from the live status while it is chosen, else a preview of what it
 * would do, read again at each `readAt` (the nav row's menu opening: the control stays mounted
 * while a city is stored and while the computed turn passes).
 */
function useSkyNote(theme: Theme | undefined, sky: SkyStatus | undefined, readAt: number): string {
  const { t } = useTranslation()
  const following = theme === "sky" && sky !== undefined
  // readAt is the reason to read again: the stored city and the clock are not React state
  const preview = useMemo(() => (following ? null : skyStatus(loadStoredCity(), Date.now())), [following, readAt])
  const status = preview ?? sky ?? NO_SKY
  if (!status.city) return t("nav.skyNote.noCity")
  if (!status.next) return t("nav.skyNote.noTurn", { city: status.city })
  const time = formatSkyTime(status.next.at, status.timezone)
  return status.next.light === "dark" ? t("nav.skyNote.toNight", { time, city: status.city }) : t("nav.skyNote.toDay", { time, city: status.city })
}

export function ThemeToggle({ labelled = false, className }: { labelled?: boolean; className?: string }) {
  const { t } = useTranslation()
  const { theme, setTheme, sky } = useTheme()
  const resolved = useResolvedTheme()
  const chosen = isChoice(theme) ? theme : null
  // the menu sheet's variant mounts with the sheet; the nav row's reads the preview at each opening
  const [openings, setOpenings] = useState(0)
  const note = useSkyNote(theme, sky, openings)
  const noteId = useId()

  const choose = (next: Choice) => {
    if (next === theme) return
    trackEvent("theme-change", { theme: next })
    setTheme(next)
  }

  if (labelled) {
    return (
      <div className={className}>
        <div role="group" aria-label={t("nav.theme")} className="grid grid-cols-3 rounded-[2px] border border-line-brass">
          {CHOICES.map(({ value }, i) => (
            <button
              key={value}
              type="button"
              aria-pressed={chosen === value}
              aria-describedby={value === "sky" ? noteId : undefined}
              onClick={() => choose(value)}
              className={cn(
                "inline-flex min-h-11 items-center justify-center px-2 py-1.5 text-center text-[14px] leading-tight text-balance text-muted-foreground",
                "transition-colors duration-(--dur-state) ease-(--ease-out) hover:text-foreground",
                "aria-pressed:bg-surface aria-pressed:text-foreground aria-pressed:shadow-[inset_0_-2px_0_var(--primary)]",
                i > 0 && "border-s border-line-brass",
              )}
            >
              {t(`nav.themeChoices.${value}`)}
            </button>
          ))}
        </div>
        <p id={noteId} className="mt-2 text-[13px] leading-snug text-muted-foreground">
          {note}
        </p>
      </div>
    )
  }

  const Icon = chosen === "sky" ? SunMoon : (chosen ?? resolved) === "light" ? Sun : Moon
  const label = t("nav.themeCurrent", { choice: t(`nav.themeChoices.${chosen ?? "system"}`) })
  return (
    <DropdownMenu modal={false} onOpenChange={(open) => open && setOpenings((n) => n + 1)}>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label={label} title={label} className={cn("nav-iconbtn", className)}>
          <Icon aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(19rem,calc(100vw-32px))]">
        <DropdownMenuLabel>{t("nav.theme")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={chosen ?? ""} onValueChange={(value) => isChoice(value) && choose(value)}>
          {CHOICES.map(({ value, Icon: ChoiceIcon }) => (
            <DropdownMenuRadioItem
              key={value}
              value={value}
              aria-describedby={value === "sky" ? noteId : undefined}
              className={value === "sky" ? "items-start py-2 [&>svg]:mt-0.5" : undefined}
            >
              <ChoiceIcon aria-hidden="true" />
              {value === "sky" ? (
                <span className="grid gap-0.5">
                  <span>{t("nav.themeChoices.sky")}</span>
                  {/* the item's description, not part of its name */}
                  <span id={noteId} aria-hidden="true" className="text-[12.5px] leading-snug text-muted-foreground">
                    {note}
                  </span>
                </span>
              ) : (
                t(`nav.themeChoices.${value}`)
              )}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
