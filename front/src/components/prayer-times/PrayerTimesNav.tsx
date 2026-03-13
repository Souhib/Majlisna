import { Clock, MapPin, Moon, ChevronDown } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { usePrayerTimes } from "@/hooks/use-prayer-times"
import { CitySelector, autoDetectLocationByIP, loadStoredCity, refreshTimezoneIfMissing, type CityCoordinates } from "./CitySelector"

const PRAYER_ICONS: Record<string, string> = {
  fajr: "\u{1F305}",
  sunrise: "\u{2600}\uFE0F",
  dhuhr: "\u{1F31E}",
  asr: "\u{26C5}",
  maghrib: "\u{1F307}",
  isha: "\u{1F319}",
}

function formatTime(date: Date, timezone?: string): string {
  const options: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" }
  if (timezone) options.timeZone = timezone
  return date.toLocaleTimeString([], options)
}

export function PrayerTimesNav() {
  const { t } = useTranslation()
  const [coordinates, setCoordinates] = useState<CityCoordinates | null>(() => loadStoredCity())
  const [open, setOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

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

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [])

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-muted-foreground hover:text-primary hover:bg-secondary transition-colors"
      >
        {coordinates && nextPrayer ? (
          <>
            <Clock className="h-3.5 w-3.5" />
            <span>{nextPrayer.name}</span>
            <span className="tabular-nums font-bold text-primary">{countdown}</span>
            <ChevronDown className="h-3 w-3 opacity-50" />
          </>
        ) : (
          <>
            <MapPin className="h-3.5 w-3.5" />
            <span>{t("prayer.prayerTimes")}</span>
          </>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute top-full mt-2 w-[min(20rem,calc(100vw-2rem))] rounded-xl border bg-popover p-4 shadow-lg z-50 right-0">
          {/* Header with city */}
          {coordinates && (
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-1.5 text-sm">
                <MapPin className="h-3.5 w-3.5 text-primary" />
                <span className="font-medium">{coordinates.city}</span>
              </div>
              {nextPrayer && (
                <span className="text-xs text-muted-foreground">
                  {t("prayer.next")}: <span className="font-medium text-primary">{nextPrayer.name}</span>
                </span>
              )}
            </div>
          )}

          {/* Prayer times grid */}
          {coordinates && prayers.length > 0 && (
            <div className="grid grid-cols-3 gap-2 mb-3">
              {prayers.map((prayer) => {
                const isNext = nextPrayer?.key === prayer.key
                return (
                  <div
                    key={prayer.key}
                    className={`rounded-lg p-2 text-center transition-colors ${
                      isNext
                        ? "bg-primary/10 ring-1 ring-primary/30"
                        : "bg-muted/50"
                    }`}
                  >
                    <span className="text-sm">{PRAYER_ICONS[prayer.key] || ""}</span>
                    <p className={`text-xs font-medium ${isNext ? "text-primary" : "text-muted-foreground"}`}>
                      {prayer.name}
                    </p>
                    <p className={`text-xs font-bold tabular-nums ${isNext ? "text-primary" : ""}`}>
                      {formatTime(prayer.time, timezone)}
                    </p>
                  </div>
                )
              })}
            </div>
          )}

          {/* Tahajjud */}
          {coordinates && tahajjud && (
            <div className="rounded-lg bg-primary/5 border border-primary/10 p-3 mb-3">
              <div className="flex items-start gap-2">
                <Moon className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                <div>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-xs font-bold">{t("prayer.tahajjud")}</span>
                    <span className="text-xs font-bold tabular-nums text-primary">
                      {formatTime(tahajjud, timezone)}
                    </span>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-1 leading-relaxed italic">
                    "{t("prayer.tahajjudHadith")}"
                    <span className="not-italic ml-0.5 opacity-70">— {t("prayer.tahajjudSource")}</span>
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* City selector */}
          <div className="border-t pt-3">
            <CitySelector onSelect={handleCitySelect} initialCity={coordinates?.city} />
          </div>
        </div>
      )}
    </div>
  )
}
