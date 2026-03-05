import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  Coordinates,
  PrayerTimes,
  Prayer,
  CalculationMethod,
  SunnahTimes,
} from "adhan"

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

export function usePrayerTimes(
  coordinates: { lat: number; lng: number } | null,
): UsePrayerTimesResult {
  const [countdown, setCountdown] = useState("--:--:--")
  const [dateKey, setDateKey] = useState(() => getDateKey(new Date()))
  const [nextPrayerVersion, setNextPrayerVersion] = useState(0)
  const lastCountdownRef = useRef("")

  // Check for midnight crossing every 30s
  useEffect(() => {
    const interval = setInterval(() => {
      const currentKey = getDateKey(new Date())
      setDateKey((prev) => (prev !== currentKey ? currentKey : prev))
    }, 30_000)
    return () => clearInterval(interval)
  }, [])

  const prayerTimes = useMemo(() => {
    if (!coordinates) return null
    const coords = new Coordinates(coordinates.lat, coordinates.lng)
    const params = CalculationMethod.MuslimWorldLeague()
    return new PrayerTimes(coords, new Date(), params)
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
    return prayers[0] // wrap to next day's Fajr
  }, [prayers])

  const nextPrayer = useMemo(() => findNextPrayer(), [findNextPrayer, nextPrayerVersion])

  useEffect(() => {
    if (!nextPrayer) return
    const interval = setInterval(() => {
      const current = new Date()
      const diff = nextPrayer.time.getTime() - current.getTime()
      const formatted = formatCountdown(diff > 0 ? diff : 0)

      // When countdown hits 0, trigger recompute of nextPrayer
      if (diff <= 0 && lastCountdownRef.current !== "00:00:00") {
        setNextPrayerVersion((v) => v + 1)
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
