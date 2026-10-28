import { MapPin, Moon, Sunset } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Lozenge } from "@/components/brand"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { usePrayerTimes } from "@/hooks/use-prayer-times"
import { cn } from "@/lib/utils"
import { CitySelector, autoDetectLocationByIP, loadStoredCity, refreshTimezoneIfMissing, type CityCoordinates } from "./CitySelector"

/**
 * Clock times are read aloud at mixed tables: 24-hour, Western digits, in every
 * language (DESIGN.md, "Type"). The city's own time zone when we know it.
 */
export function formatPrayerTime(date: Date, timezone?: string): string {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      ...(timezone ? { timeZone: timezone } : {}),
    }).format(date)
  } catch {
    // an unknown time zone string from an old stored city
    return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date)
  }
}

/**
 * The prayer chip of the nav ("Maghrib 18:42", the next prayer and its time) and, on
 * tap, the day's times, the last third of the night and the city picker. Times are
 * computed on the device (adhan, Muslim World League); the location comes from the
 * stored city, IP auto-detection or the browser's geolocation (CitySelector).
 */
export function PrayerTimesNav({
  className,
  align = "end",
  fallbackLabel,
}: {
  className?: string
  align?: "start" | "center" | "end"
  /** The chip's text while no prayer time is known (no city yet). Default "Prayer Times";
   *  the menu sheet, which labels the chip "Prayer Times" already, says "Choose a city". */
  fallbackLabel?: string
}) {
  const { t } = useTranslation()
  const [coordinates, setCoordinates] = useState<CityCoordinates | null>(() => loadStoredCity())

  // Auto-detect location by IP if no stored city
  useEffect(() => {
    if (!coordinates) {
      autoDetectLocationByIP().then((coords) => {
        if (coords) setCoordinates(coords)
      })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch timezone if stored city is missing it (e.g. saved before timezone fix)
  useEffect(() => {
    if (coordinates && !coordinates.timezone) {
      refreshTimezoneIfMissing(coordinates).then((updated) => {
        if (updated) setCoordinates(updated)
      })
    }
  }, [coordinates])

  const timezone = coordinates?.timezone
  const { prayers, tahajjud, nextPrayer, countdown } = usePrayerTimes(
    coordinates ? { lat: coordinates.lat, lng: coordinates.lng } : null,
  )

  const handleCitySelect = useCallback((data: CityCoordinates) => {
    setCoordinates(data)
  }, [])

  const name = (key: string) => t(`prayer.names.${key}`)
  const nextName = nextPrayer ? name(nextPrayer.key) : ""
  const nextTime = nextPrayer ? formatPrayerTime(nextPrayer.time, timezone) : ""

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className={cn("prayer-chip", className)} data-fallback={!(coordinates && nextPrayer) || undefined}>
          {coordinates && nextPrayer ? (
            <>
              <Sunset aria-hidden="true" />
              <span className="sr-only">{t("prayer.prayerTimes")}: </span>
              <span className="pn">{nextName}</span>
              <b className="num" dir="ltr">
                {nextTime}
              </b>
            </>
          ) : (
            <>
              {/* .pn: at 1440 px and below the nav keeps the pin only (the label stays for
                  assistive tech); the next prayer's name goes at 1360 (shell.css) */}
              <MapPin aria-hidden="true" />
              <span className="pn">{fallbackLabel ?? t("prayer.prayerTimes")}</span>
            </>
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent align={align} className="w-[min(22rem,calc(100vw-32px))] p-4">
        <div className="grid gap-3.5">
          {coordinates && nextPrayer ? (
            <p className="text-[14px] text-muted-foreground">
              {/* "Maghrib in" / "Maghrib dans" / "المغرب بعد": the time ends the phrase in
                  all three languages, and is drawn on its own in tabular figures. */}
              {t("prayer.nextIn", { name: nextName, time: "" }).trim()}{" "}
              <span className="num font-medium text-foreground" dir="ltr">
                {countdown}
              </span>
            </p>
          ) : null}

          {coordinates && prayers.length > 0 ? (
            <ul className="prayer-grid">
              {prayers.map((prayer) => {
                const isNext = nextPrayer?.key === prayer.key
                return (
                  <li key={prayer.key} data-next={isNext || undefined} aria-current={isNext ? "time" : undefined}>
                    <span className="pname">
                      {isNext ? <Lozenge state="brass" size={6} /> : null}
                      {name(prayer.key)}
                    </span>
                    <span className="ptime">{formatPrayerTime(prayer.time, timezone)}</span>
                  </li>
                )
              })}
            </ul>
          ) : null}

          {coordinates && tahajjud ? (
            <div className="grid gap-1.5 border-t border-line pt-3">
              <p className="flex items-center gap-2 text-[14px]">
                <Moon className="size-4 shrink-0 text-brass" aria-hidden="true" />
                <span className="font-medium text-foreground">{t("prayer.tahajjud")}</span>
                <span className="num font-medium text-foreground" dir="ltr">
                  {formatPrayerTime(tahajjud, timezone)}
                </span>
              </p>
              <p className="text-[13px] leading-relaxed text-muted-foreground">
                {t("prayer.tahajjudHadith")}
                <span className="ms-1.5 whitespace-nowrap">({t("prayer.tahajjudSource")})</span>
              </p>
            </div>
          ) : null}

          <div className="border-t border-line pt-3">
            <CitySelector onSelect={handleCitySelect} initialCity={coordinates?.city} />
          </div>
          {coordinates ? <p className="type-meta">{t("prayer.method")}</p> : null}
        </div>
      </PopoverContent>
    </Popover>
  )
}
