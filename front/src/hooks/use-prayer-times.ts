import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Coordinates, PrayerTimes, Prayer, CalculationMethod, SunnahTimes } from "adhan"

type PrayerValue = (typeof Prayer)[keyof typeof Prayer]

interface PrayerTimeEntry {
  name: string
  key: string
  time: Date
}

interface UsePrayerTimesResult {
  prayers: PrayerTimeEntry[]
  tahajjud: Date | null
  nextPrayer: PrayerTimeEntry | null
  countdown: string
  loading: boolean
}

const PRAYER_KEYS: { prayer: PrayerValue; key: string; name: string }[] = [
  { prayer: Prayer.Fajr, key: "fajr", name: "Fajr" },
  { prayer: Prayer.Sunrise, key: "sunrise", name: "Sunrise" },
  { prayer: Prayer.Dhuhr, key: "dhuhr", name: "Dhuhr" },
  { prayer: Prayer.Asr, key: "asr", name: "Asr" },
  { prayer: Prayer.Maghrib, key: "maghrib", name: "Maghrib" },
  { prayer: Prayer.Isha, key: "isha", name: "Isha" },
]

function getDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}

function formatCountdown(ms: number): string {
  if (ms <= 0) return "00:00:00"
  const totalSeconds = Math.floor(ms / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
}

/** A prayer whose time has come: its key (`fajr`, `dhuhr`, `asr`, `maghrib`, `isha`) and adhan time. */
export interface AdhanEntry {
  key: string
  time: Date
}

/**
 * The prayer whose adhan came at most `windowMs` before `now`, or null (sunrise is a
 * time, not a prayer). Pure and computed on the device like the nav's times (Muslim
 * World League), so a game page can ask it on its own schedule: the prayer pause's
 * suggestion to the host.
 */
export function recentAdhan(coordinates: { lat: number; lng: number }, now: Date, windowMs: number): AdhanEntry | null {
  const times = new PrayerTimes(new Coordinates(coordinates.lat, coordinates.lng), now, CalculationMethod.MuslimWorldLeague())
  for (const { prayer, key } of PRAYER_KEYS) {
    if (key === "sunrise") continue
    const time = times.timeForPrayer(prayer)
    if (!time) continue
    const since = now.getTime() - time.getTime()
    if (since >= 0 && since <= windowMs) return { key, time }
  }
  return null
}

export function usePrayerTimes(coordinates: { lat: number; lng: number } | null): UsePrayerTimesResult {
  const [countdown, setCountdown] = useState("--:--:--")
  const [dateKey, setDateKey] = useState(() => getDateKey(new Date()))
  const [nextPrayerVersion, setNextPrayerVersion] = useState(0)
  const lastCountdownRef = useRef("")

  // Check for midnight crossing every 30s + on tab refocus
  useEffect(() => {
    const checkDateChange = () => {
      const currentKey = getDateKey(new Date())
      setDateKey((prev) => {
        if (prev !== currentKey) {
          setNextPrayerVersion((v) => v + 1)
          return currentKey
        }
        return prev
      })
    }
    const interval = setInterval(checkDateChange, 30_000)

    // When tab comes back from background, recompute immediately
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        checkDateChange()
        setNextPrayerVersion((v) => v + 1)
      }
    }
    document.addEventListener("visibilitychange", handleVisibility)

    return () => {
      clearInterval(interval)
      document.removeEventListener("visibilitychange", handleVisibility)
    }
  }, [])

  const prayerTimes = useMemo(() => {
    if (!coordinates) return null
    const coords = new Coordinates(coordinates.lat, coordinates.lng)
    const params = CalculationMethod.MuslimWorldLeague()
    return new PrayerTimes(coords, new Date(), params)
  }, [coordinates, dateKey])

  const tomorrowPrayerTimes = useMemo(() => {
    if (!coordinates) return null
    const coords = new Coordinates(coordinates.lat, coordinates.lng)
    const params = CalculationMethod.MuslimWorldLeague()
    const tomorrow = new Date()
    tomorrow.setDate(tomorrow.getDate() + 1)
    return new PrayerTimes(coords, tomorrow, params)
  }, [coordinates, dateKey])

  const sunnahTimes = useMemo(() => {
    if (!prayerTimes) return null
    return new SunnahTimes(prayerTimes)
  }, [prayerTimes])

  const prayers: PrayerTimeEntry[] = useMemo(() => {
    if (!prayerTimes) return []
    return PRAYER_KEYS.map(({ key, name, prayer }) => ({
      name,
      key,
      time: prayerTimes.timeForPrayer(prayer) as Date,
    }))
  }, [prayerTimes])

  const tahajjud = useMemo(() => {
    return sunnahTimes?.lastThirdOfTheNight ?? null
  }, [sunnahTimes])

  const findNextPrayer = useCallback((): PrayerTimeEntry | null => {
    if (!prayers.length) return null
    const current = new Date()
    for (const p of prayers) {
      if (p.time > current) return p
    }
    // All today's prayers have passed — return tomorrow's Fajr
    if (tomorrowPrayerTimes) {
      return {
        name: "Fajr",
        key: "fajr",
        time: tomorrowPrayerTimes.timeForPrayer(Prayer.Fajr) as Date,
      }
    }
    return null
  }, [prayers, tomorrowPrayerTimes])

  const nextPrayer = useMemo(() => findNextPrayer(), [findNextPrayer, nextPrayerVersion])

  useEffect(() => {
    if (!nextPrayer) return
    // Reset the guard so a fresh countdown can trigger recompute when it hits 0
    lastCountdownRef.current = ""
    const interval = setInterval(() => {
      const current = new Date()
      const diff = nextPrayer.time.getTime() - current.getTime()
      const formatted = formatCountdown(diff > 0 ? diff : 0)

      // When countdown hits 0, trigger recompute of nextPrayer
      // and force dateKey update in case we crossed midnight
      if (diff <= 0 && lastCountdownRef.current !== "00:00:00") {
        setNextPrayerVersion((v) => v + 1)
        setDateKey(getDateKey(new Date()))
      }
      lastCountdownRef.current = formatted
      setCountdown(formatted)
    }, 1000)
    return () => clearInterval(interval)
  }, [nextPrayer])

  return {
    prayers,
    tahajjud,
    nextPrayer,
    countdown,
    loading: !coordinates,
  }
}
