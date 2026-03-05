import { MapPin, Search, Loader2 } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { useMapsLibrary } from "@vis.gl/react-google-maps"

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

const STORAGE_CITY_KEY = "ipg-city"
const STORAGE_COORDS_KEY = "ipg-coordinates"

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

function storeCity(data: CityCoordinates) {
  localStorage.setItem(STORAGE_CITY_KEY, data.city)
  localStorage.setItem(STORAGE_COORDS_KEY, JSON.stringify({ lat: data.lat, lng: data.lng, timezone: data.timezone }))
}

async function fetchTimezone(lat: number, lng: number): Promise<string | undefined> {
  // Try Open-Meteo first (free, no API key required)
  try {
    const res = await fetch(
      `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lng}&timezone=auto&forecast_days=1`,
    )
    const data = await res.json()
    if (data.timezone) return data.timezone as string
  } catch {
    // Open-Meteo unavailable, try fallback
  }

  // Fallback to Google Timezone API
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined
  if (!apiKey) return undefined
  try {
    const timestamp = Math.floor(Date.now() / 1000)
    const res = await fetch(
      `https://maps.googleapis.com/maps/api/timezone/json?location=${lat},${lng}&timestamp=${timestamp}&key=${apiKey}`,
    )
    const data = await res.json()
    if (data.status === "OK") return data.timeZoneId as string
  } catch {
    // Google Timezone API not enabled or network error
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

export function CitySelector({ onSelect, initialCity }: CitySelectorProps) {
  const [query, setQuery] = useState("")
  const [detecting, setDetecting] = useState(false)
  const [predictions, setPredictions] = useState<google.maps.places.AutocompletePrediction[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [selectedCity, setSelectedCity] = useState(initialCity || "")
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const places = useMapsLibrary("places")

  const autocompleteService = useRef<google.maps.places.AutocompleteService | null>(null)
  const placesService = useRef<google.maps.places.PlacesService | null>(null)

  useEffect(() => {
    if (!places) return
    autocompleteService.current = new places.AutocompleteService()
    const div = document.createElement("div")
    placesService.current = new places.PlacesService(div)
  }, [places])

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

  const searchPlaces = useCallback(
    (input: string) => {
      if (!autocompleteService.current || input.length < 2) {
        setPredictions([])
        return
      }
      autocompleteService.current.getPlacePredictions(
        { input, types: ["(cities)"] },
        (results: google.maps.places.AutocompletePrediction[] | null) => {
          setPredictions(results || [])
          setShowDropdown(true)
        },
      )
    },
    [],
  )

  const selectPrediction = useCallback(
    (prediction: google.maps.places.AutocompletePrediction) => {
      if (!placesService.current) return
      placesService.current.getDetails(
        { placeId: prediction.place_id, fields: ["geometry", "name"] },
        async (place: google.maps.places.PlaceResult | null) => {
          if (!place?.geometry?.location) return
          const lat = place.geometry.location.lat()
          const lng = place.geometry.location.lng()
          const timezone = await fetchTimezone(lat, lng)
          const data: CityCoordinates = {
            city: prediction.structured_formatting.main_text,
            lat,
            lng,
            timezone,
          }
          storeCity(data)
          setSelectedCity(data.city)
          setQuery("")
          setShowDropdown(false)
          onSelect(data)
        },
      )
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

      // Reverse geocode to get city name
      const geocoder = new google.maps.Geocoder()
      const result = await geocoder.geocode({ location: { lat, lng } })
      let cityName = "My Location"
      for (const comp of result.results[0]?.address_components ?? []) {
        if (comp.types.includes("locality")) {
          cityName = comp.long_name
          break
        }
      }

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
  }, [onSelect])

  const hasGoogleMaps = !!places

  return (
    <div className="relative" ref={dropdownRef}>
      {selectedCity ? (
        <div className="flex items-center gap-2">
          <MapPin className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">{selectedCity}</span>
          <button
            type="button"
            onClick={() => {
              setSelectedCity("")
              inputRef.current?.focus()
            }}
            className="text-xs text-muted-foreground hover:text-primary transition-colors underline"
          >
            Change
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={detectLocation}
            disabled={detecting || !hasGoogleMaps}
            className="flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary/20 transition-colors disabled:opacity-50"
          >
            {detecting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <MapPin className="h-3.5 w-3.5" />
            )}
            Use my location
          </button>
          {hasGoogleMaps && (
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  searchPlaces(e.target.value)
                }}
                onFocus={() => predictions.length > 0 && setShowDropdown(true)}
                placeholder="Search city..."
                className="w-full rounded-md border bg-background py-1.5 pl-8 pr-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
              />
              {showDropdown && predictions.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-1 rounded-md border bg-popover shadow-lg z-50 max-h-48 overflow-auto">
                  {predictions.map((p) => (
                    <button
                      key={p.place_id}
                      type="button"
                      onClick={() => selectPrediction(p)}
                      className="w-full px-3 py-2 text-left text-sm hover:bg-muted transition-colors"
                    >
                      <span className="font-medium">{p.structured_formatting.main_text}</span>
                      <span className="text-muted-foreground ml-1 text-xs">
                        {p.structured_formatting.secondary_text}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {!hasGoogleMaps && (
            <span className="text-xs text-muted-foreground">
              Or set VITE_GOOGLE_MAPS_API_KEY for city search
            </span>
          )}
        </div>
      )}
    </div>
  )
}
