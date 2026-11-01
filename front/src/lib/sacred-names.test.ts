import { describe, expect, it } from "vitest"
import { holdsSacredName } from "./sacred-names"

/**
 * What this app never sweeps, strikes or wipes across (DESIGN.md §7, "nothing ever passes over
 * a sacred name"): a name of Allah, the Prophet ﷺ, a prophet, Jibril, the Qur'an or the
 * Kaaba, in the three languages. One list for every writing gesture that would pass over a
 * text: the samar riddle's line and the Codenames clue. Such a text fades in instead.
 */
describe("holdsSacredName: a line that is never swept", () => {
  it.each([
    "A believer's direct line to Allah",
    "Something every creature receives from Allah",
    "Un lien direct entre le croyant et Allah",
    "شيء يتلقاه كل مخلوق من الله",
    "دعا اللَّهَ بولد في شيخوخته",
    "Begun with Bismillah",
    "Said after Alhamdulillah",
    "Servant of Abdullah's line",
    "Ar-Rahman's mercy",
    "الرحمن الرحيم",
    "The Messenger ﷺ",
    "Muhammad's city",
    "مدينة محمد",
    "The Lord of the worlds",
    "Revealed to comfort the Prophet during a difficult time",
    "Father of Ismail and Ishaq",
    "Le père d’Ismaïl et d’Isaac",
    "والد إسماعيل وإسحاق",
    "A prophet, son and grandson of prophets",
    "Brought the revelation down: Jibril",
    "Its first word in the Qur’an",
    "من أقصر سور القرآن",
  ])("holds a sacred name: %s", (line) => {
    expect(holdsSacredName(line)).toBe(true)
  })

  it.each(["A great patriarch", "Un grand patriarche", "أب عظيم", "A decisive early event in Islamic history", "A unit of time"])("holds none: %s", (line) => {
    expect(holdsSacredName(line)).toBe(false)
  })
})

describe("holdsSacredName: a Codenames clue, one word in any case or script", () => {
  it.each(["Allah", "ALLAH", "allah", "الله", "اللَّه", "Rahman", "Muhammad", "محمد", "Musa", "موسى", "Ibrahim", "Quran", "Coran", "قرآن", "Kaaba", "Jibril"])(
    "is a sacred name: %s",
    (clue) => {
      expect(holdsSacredName(clue)).toBe(true)
    },
  )

  it.each(["knowledge", "mercy", "ilm", "صبر", "Sabr", "Hajj", "Makkah"])("is not: %s", (clue) => {
    expect(holdsSacredName(clue)).toBe(false)
  })

  it("answers the same on every call (no stateful regular expression)", () => {
    expect([holdsSacredName("Allah"), holdsSacredName("Allah"), holdsSacredName("Allah")]).toEqual([true, true, true])
  })
})
