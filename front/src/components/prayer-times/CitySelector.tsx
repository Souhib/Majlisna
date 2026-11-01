import { MapPin, Search } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { currentLanguage, type LanguageCode } from "@/components/layout/language-switch"
import { Button } from "@/components/ui/button"

export interface CityCoordinates {
  city: string
  lat: number
  lng: number
  timezone?: string
}

interface CitySelectorProps {
  onSelect: (coords: CityCoordinates) => void
  initialCity?: string
}

const STORAGE_CITY_KEY = "majlisna-city"
const STORAGE_COORDS_KEY = "majlisna-coordinates"

/** When the last IP detection failed (ms since the epoch): not asked again for a day. */
export const GEO_FAILED_AT_KEY = "majlisna-geo-failed-at"
export const GEO_RETRY_AFTER_MS = 24 * 60 * 60 * 1000
const IPAPI_URL = "https://ipapi.co/json/"

export function loadStoredCity(): CityCoordinates | null {
  try {
    const city = localStorage.getItem(STORAGE_CITY_KEY)
    const coordsStr = localStorage.getItem(STORAGE_COORDS_KEY)
    if (city && coordsStr) {
      const coords = JSON.parse(coordsStr)
      return { city, lat: coords.lat, lng: coords.lng, timezone: coords.timezone }
    }
  } catch {}
  return null
}

export function storeCity(data: CityCoordinates) {
  try {
    localStorage.setItem(STORAGE_CITY_KEY, data.city)
    localStorage.setItem(STORAGE_COORDS_KEY, JSON.stringify({ lat: data.lat, lng: data.lng, timezone: data.timezone }))
  } catch {
    // blocked storage: the city holds for this page only
  }
}

async function fetchTimezone(lat: number, lng: number): Promise<string | undefined> {
  try {
    const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}&timezone=auto&forecast_days=1`)
    const data = await res.json()
    if (data.timezone) return data.timezone as string
  } catch {
    // Open-Meteo unavailable
  }
  return undefined
}

export async function refreshTimezoneIfMissing(coords: CityCoordinates): Promise<CityCoordinates | null> {
  if (coords.timezone) return null
  const timezone = await fetchTimezone(coords.lat, coords.lng)
  if (!timezone) return null
  const updated = { ...coords, timezone }
  storeCity(updated)
  return updated
}

// Free city search via Open-Meteo geocoding API
interface OpenMeteoGeoResult {
  id: number
  name: string
  latitude: number
  longitude: number
  country: string
  admin1?: string
}

async function searchCitiesFree(query: string, language: LanguageCode): Promise<OpenMeteoGeoResult[]> {
  if (query.length < 2) return []
  try {
    const res = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query)}&count=5&language=${language}&format=json`)
    const data = await res.json()
    return (data.results || []) as OpenMeteoGeoResult[]
  } catch {
    return []
  }
}

// Free reverse geocoding via Nominatim (OpenStreetMap), named in the interface language;
// null when it has no name for the place (the caller says "My location").
async function reverseGeocodeFree(lat: number, lng: number, language: LanguageCode): Promise<string | null> {
  try {
    const res = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&zoom=10`, {
      headers: { "Accept-Language": language },
    })
    const data = await res.json()
    return data.address?.city || data.address?.town || data.address?.village || data.address?.county || null
  } catch {
    return null
  }
}

function detectionFailedRecently(): boolean {
  try {
    const at = Number(localStorage.getItem(GEO_FAILED_AT_KEY))
    return at > 0 && Date.now() - at < GEO_RETRY_AFTER_MS
  } catch {
    return false
  }
}

function rememberDetection(failed: boolean) {
  try {
    if (failed) localStorage.setItem(GEO_FAILED_AT_KEY, String(Date.now()))
    else localStorage.removeItem(GEO_FAILED_AT_KEY)
  } catch {
    // blocked storage: nothing to remember the failure with
  }
}

async function askIpapi(): Promise<CityCoordinates | null> {
  try {
    const res = await fetch(IPAPI_URL)
    if (res.ok) {
      const data = await res.json()
      if (data.city && Number.isFinite(data.latitude) && Number.isFinite(data.longitude)) {
        const coords: CityCoordinates = {
          city: data.city,
          lat: data.latitude,
          lng: data.longitude,
          timezone: data.timezone,
        }
        storeCity(coords)
        rememberDetection(false)
        return coords
      }
    }
  } catch {
    // IP geolocation unavailable: ipapi.co's 429 carries no CORS header, so it lands here
  }
  rememberDetection(true)
  return null
}

let detection: Promise<CityCoordinates | null> | null = null

/**
 * The city guessed from the IP (ipapi.co), stored when found. One request per page load
 * whoever asks (the nav and a mounted chip share it), and none for a day after a failure
 * (FR-11): ipapi.co rate-limits per IP, and every visitor behind a carrier's shared IP
 * used to ask again, and fail again, on every page.
 */
export function autoDetectLocationByIP(): Promise<CityCoordinates | null> {
  if (detection) return detection
  if (detectionFailedRecently()) return Promise.resolve(null)
  detection = askIpapi().finally(() => {
    detection = null
  })
  return detection
}

export function CitySelector({ onSelect, initialCity }: CitySelectorProps) {
  const { t, i18n } = useTranslation()
  const language = currentLanguage(i18n.language)
  const [query, setQuery] = useState("")
  const [detecting, setDetecting] = useState(false)
  const [selectedCity, setSelectedCity] = useState(initialCity || "")
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const [predictions, setPredictions] = useState<OpenMeteoGeoResult[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  const handleSearch = useCallback(
    (input: string) => {
      setQuery(input)
      if (input.length < 2) {
        setPredictions([])
        setShowDropdown(false)
        return
      }

      if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current)
      searchTimeoutRef.current = setTimeout(async () => {
        const results = await searchCitiesFree(input, language)
        setPredictions(results)
        setShowDropdown(true)
      }, 300)
    },
    [language],
  )

  const selectPrediction = useCallback(
    async (result: OpenMeteoGeoResult) => {
      const timezone = await fetchTimezone(result.latitude, result.longitude)
      const data: CityCoordinates = {
        city: result.name,
        lat: result.latitude,
        lng: result.longitude,
        timezone,
      }
      storeCity(data)
      setSelectedCity(data.city)
      setQuery("")
      setShowDropdown(false)
      setPredictions([])
      onSelect(data)
    },
    [onSelect],
  )

  const detectLocation = useCallback(async () => {
    setDetecting(true)
    try {
      const position = await new Promise<GeolocationPosition>((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10000 }),
      )
      const { latitude: lat, longitude: lng } = position.coords
      const cityName = (await reverseGeocodeFree(lat, lng, language)) ?? t("prayer.myLocation")
      const timezone = await fetchTimezone(lat, lng)
      const data: CityCoordinates = { city: cityName, lat, lng, timezone }
      storeCity(data)
      setSelectedCity(data.city)
      onSelect(data)
    } catch (err) {
      console.error("Location detection failed:", err)
    } finally {
      setDetecting(false)
    }
  }, [onSelect, language, t])

  return (
    <div className="relative" ref={dropdownRef}>
      {selectedCity ? (
        <div className="flex items-center gap-2 text-[14px]">
          <MapPin className="size-4 shrink-0 text-brass" aria-hidden="true" />
          <span className="min-w-0 truncate font-medium text-foreground">{selectedCity}</span>
          <Button
            variant="link"
            size="sm"
            className="ms-auto text-[13px]"
            onClick={() => {
              setSelectedCity("")
              // the search input mounts on the next render
              requestAnimationFrame(() => inputRef.current?.focus())
            }}
          >
            {t("prayer.changeCity")}
          </Button>
        </div>
      ) : (
        <div className="grid gap-2">
          <Button variant="secondary" size="sm" block onClick={detectLocation} loading={detecting} iconStart={<MapPin aria-hidden="true" />}>
            {t("prayer.useMyLocation")}
          </Button>
          <div className="relative">
            <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <input
              ref={inputRef}
              type="search"
              value={query}
              onChange={(e) => handleSearch(e.target.value)}
              onFocus={() => predictions.length > 0 && setShowDropdown(true)}
              placeholder={t("prayer.searchCity")}
              aria-label={t("prayer.searchCity")}
              aria-expanded={showDropdown && predictions.length > 0}
              aria-controls="city-predictions"
              autoComplete="off"
              className="h-11 w-full rounded-sm border border-line-field bg-surface ps-9 pe-3 text-[15px] text-foreground outline-none transition-colors duration-(--dur-state) focus-visible:border-brass focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color-mix(in_oklch,var(--brass)_45%,transparent)]"
            />
            {showDropdown && predictions.length > 0 && (
              <ul
                id="city-predictions"
                className="absolute inset-x-0 top-full z-50 mt-1 max-h-48 overflow-auto rounded-sm border border-line-brass bg-popover p-1 shadow-[0_14px_28px_-18px_oklch(0_0_0/0.45)]"
              >
                {predictions.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => selectPrediction(r)}
                      className="flex min-h-10 w-full flex-col items-start justify-center rounded-sm px-3 py-1.5 text-start text-[14px] hover:bg-[color-mix(in_oklch,var(--brass)_12%,transparent)] focus-visible:bg-[color-mix(in_oklch,var(--brass)_12%,transparent)] pointer-coarse:min-h-11"
                    >
                      <span className="font-medium text-foreground">{r.name}</span>
                      <span className="text-[12.5px] text-muted-foreground">{[r.admin1, r.country].filter(Boolean).join(", ")}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
