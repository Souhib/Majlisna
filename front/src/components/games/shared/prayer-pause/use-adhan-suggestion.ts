import { useCallback, useEffect, useMemo, useState } from "react"
import { loadStoredCity } from "@/components/prayer-times/CitySelector"
import { type AdhanEntry, recentAdhan } from "@/hooks/use-prayer-times"

/** How long after the adhan the host is still offered the pause. */
export const ADHAN_SUGGESTION_WINDOW_MS = 20 * 60_000
/** How often a running game looks at the time (no animation: a state check). */
export const ADHAN_CHECK_MS = 15_000

const STORAGE_PREFIX = "majlisna-adhan-suggestion"

/** One prayer of one day in one game: the suggestion is made once for it. */
export function adhanSuggestionKey(gameId: string, adhan: AdhanEntry): string {
  const d = adhan.time
  const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
  return `${STORAGE_PREFIX}:${gameId}:${day}:${adhan.key}`
}

function wasAnswered(key: string): boolean {
  try {
    return sessionStorage.getItem(key) === "1"
  } catch {
    return false
  }
}

function markAnswered(key: string) {
  try {
    sessionStorage.setItem(key, "1")
  } catch {
    // private mode or blocked storage: the suggestion simply may come back on reload
  }
}

interface UseAdhanSuggestionOptions {
  gameId: string
  /** The server's `can_pause` for this caller: only the host is ever offered the pause. */
  canPause: boolean
  /** Whether the game is paused (a pause during the window answers the suggestion). */
  paused: boolean
}

/**
 * The adhan suggestion of the prayer pause: when a prayer time arrives in the host's
 * city while their game runs, they are offered to pause it, once per prayer per game
 * (remembered in sessionStorage). Nothing without a stored city (no IP guess here: a
 * game must not ask the network where its host is), nothing for anyone who cannot
 * pause, and nothing once the window after the adhan has passed.
 */
export function useAdhanSuggestion({ gameId, canPause, paused }: UseAdhanSuggestionOptions) {
  const watching = canPause || paused
  const [now, setNow] = useState(() => Date.now())
  const [, setAnswers] = useState(0)

  useEffect(() => {
    if (!watching) return
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), ADHAN_CHECK_MS)
    return () => window.clearInterval(id)
  }, [watching])

  const adhan = useMemo(() => {
    if (!watching) return null
    const city = loadStoredCity()
    if (!city || !Number.isFinite(city.lat) || !Number.isFinite(city.lng)) return null
    return recentAdhan({ lat: city.lat, lng: city.lng }, new Date(now), ADHAN_SUGGESTION_WINDOW_MS)
  }, [watching, now])
  const key = adhan ? adhanSuggestionKey(gameId, adhan) : null

  // Paused while this prayer's window is open (from the header, or from the strip): the
  // suggestion has been answered, and must not come back after the resume.
  useEffect(() => {
    if (paused && key) markAnswered(key)
  }, [paused, key])

  const answer = useCallback(() => {
    if (!key) return
    markAnswered(key)
    setAnswers((n) => n + 1)
  }, [key])

  const prayer = canPause && !paused && adhan && key && !wasAnswered(key) ? adhan : null
  return { prayer, answer }
}
