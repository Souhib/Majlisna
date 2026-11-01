import { describe, expect, it } from "vitest"
import ar from "../locales/ar.json"
import en from "../locales/en.json"
import fr from "../locales/fr.json"

/**
 * About → How the games play is Kalimat's rulebook (review F7): it described the scoring
 * before owner rule (e) — a wrong try costs one point, five tries a round — and read as if
 * guessing were free.
 */
describe("Kalimat's rules on /about", () => {
  it.each([
    ["en", en, ["wrong try costs a point", "five tries"]],
    ["fr", fr, ["essai faux coûte un point", "cinq essais"]],
    ["ar", ar, ["محاولة خاطئة", "خمس محاولات"]],
  ] as const)("say what a wrong try costs and how many a round allows in %s", (_lang, locale, phrases) => {
    // Act
    const rules = Object.values(locale.rules.wordQuiz).join(" ")

    // Assert
    for (const phrase of phrases) expect(rules).toContain(phrase)
  })

  it.each([
    ["en", en, "Play 3 different games this week"],
    ["fr", fr, "Jouer à 3 jeux différents cette semaine"],
    ["ar", ar, "العب 3 ألعاب مختلفة هذا الأسبوع"],
  ] as const)("names the distinct-games challenge for what it counts in %s (review R7)", (_lang, locale, text) => {
    // Assert
    expect(JSON.stringify(locale.challenges)).toContain(text)
  })
})
