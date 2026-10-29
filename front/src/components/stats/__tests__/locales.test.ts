import i18next from "i18next"
import { describe, expect, it } from "vitest"
import ar from "@/i18n/locales/ar.json"
import en from "@/i18n/locales/en.json"
import fr from "@/i18n/locales/fr.json"

/**
 * The copy of the auth pages, About and the player's space, in its three languages.
 * The pages are tested with keys; these checks hold the strings themselves.
 */
const NAMESPACES = ["auth", "about", "rules", "profile", "stats", "achievements", "challenges", "friends", "leaderboard"] as const
const PLURAL = /_(zero|one|two|few|many|other)$/

type Tree = { [key: string]: string | Tree }

function keys(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([k, v]) => (typeof v === "string" ? [prefix + k.replace(PLURAL, "")] : keys(v, `${prefix}${k}.`)))
}

function strings(tree: Tree, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([k, v]) => (typeof v === "string" ? [[prefix + k, v] as [string, string]] : strings(v, `${prefix}${k}.`)))
}

const locales = { en, fr, ar } as unknown as Record<"en" | "fr" | "ar", Record<string, Tree>>

describe("auth, About and player's space copy", () => {
  it("has the same keys in English, French and Arabic", () => {
    for (const ns of NAMESPACES) {
      const reference = new Set(keys(locales.en[ns]))
      for (const lang of ["fr", "ar"] as const) {
        expect(new Set(keys(locales[lang][ns])), `${lang}.${ns}`).toEqual(reference)
      }
    }
  })

  it("writes the roles phonetically in Arabic, never the old translations (DESIGN.md §10)", () => {
    const old = /المتخف|متخفّ|متخفي|المدني|مدني|السيد وايت|جواسيس|العملاء|كعميل|أسماء سرية/
    for (const ns of ["rules", "stats", "achievements", "challenges"] as const) {
      const offenders = strings(locales.ar[ns], `${ns}.`).filter(([, v]) => old.test(v))
      expect(offenders, ns).toEqual([])
    }
  })

  it("never lets the old Arabic role translations back, anywhere in ar.json (DESIGN.md §10)", () => {
    // Prepare: المتخفّي/المدني/السيد وايت/رئيس الجواسيس/العميل and their plurals
    const old = /متخف|مدني|السيد\s*وايت|جاسوس|جواسيس|عميل|عملاء|عملائ|عملاؤ|قائد فريق/
    const all = strings(locales.ar as unknown as Tree)

    // Act
    const offenders = all.filter(([, v]) => old.test(v))
    const plainSpaceMrWhite = all.filter(([, v]) => /مستر وايت/.test(v))

    // Assert: the phonetic names, and Mr. White held together by a no-break space
    expect(offenders).toEqual([])
    expect(plainSpaceMrWhite).toEqual([])
    expect(locales.ar.games.undercover).toMatchObject({ roles: { civilian: "سيفيليان", undercover: "أندركفر", mrWhite: "مستر وايت" } })
    expect(locales.ar.games.codenames).toMatchObject({ roles: { spymaster: "سبايماستر", operative: "أوبريتيف" } })
  })

  it("keeps the roles' English names in French, never the old translations (DESIGN.md §10)", () => {
    // Prepare: Infiltré, Maître-espion, Civil and their plurals ("agents" stays: the cards are agents)
    const old = /infiltr|maîtres?-espions?|\bcivils?\b/i
    const all = strings(locales.fr as unknown as Tree)

    // Act
    const offenders = all.filter(([, v]) => old.test(v))

    // Assert
    expect(offenders).toEqual([])
    expect(locales.fr.games.undercover).toMatchObject({ roles: { civilian: "Civilian", undercover: "Undercover" } })
    expect(locales.fr.games.codenames).toMatchObject({ roles: { spymaster: "Spymaster", operative: "Operative" } })
  })

  it("counts games with the plural forms each language needs", async () => {
    // Prepare
    const i18n = i18next.createInstance()
    await i18n.init({ resources: { en: { translation: en }, ar: { translation: ar } }, lng: "ar", interpolation: { escapeValue: false } })

    // Act / Assert: Arabic has a dual, a plural of 3 to 10, a singular accusative from
    // 11 to 99 and a singular genitive from 100
    expect(i18n.t("stats.totalGames", { count: 1 })).toBe("لعبة واحدة معًا")
    expect(i18n.t("stats.totalGames", { count: 2 })).toBe("لعبتان معًا")
    expect(i18n.t("stats.totalGames", { count: 5 })).toBe("5 ألعاب معًا")
    expect(i18n.t("stats.totalGames", { count: 11 })).toBe("11 لعبةً معًا")
    expect(i18n.t("stats.totalGames", { count: 100 })).toBe("100 لعبة معًا")
    expect(i18n.t("stats.totalGames", { count: 103 })).toBe("103 ألعاب معًا")
    expect(i18n.t("stats.playerCount", { count: 4 })).toBe("4 لاعبين")
    expect(i18n.t("stats.totalGames", { count: 1, lng: "en" })).toBe("1 game together")
    expect(i18n.t("stats.totalGames", { count: 3, lng: "en" })).toBe("3 games together")
  })

  it("sets typography the house way in every locale: ’ and …, and no-break spaces before French : ; ? !", () => {
    // Prepare
    const all = (lang: "en" | "fr" | "ar") => strings(locales[lang] as unknown as Tree)

    // Act
    const straightApostrophe = (["en", "fr"] as const).flatMap((lang) =>
      all(lang)
        .filter(([, v]) => /\p{L}'\p{L}/u.test(v))
        .map(([k]) => `${lang}:${k}`),
    )
    const threeDots = (["en", "fr", "ar"] as const).flatMap((lang) =>
      all(lang)
        .filter(([, v]) => v.includes("..."))
        .map(([k]) => `${lang}:${k}`),
    )
    const breakableFrench = all("fr")
      .filter(([, v]) => / [:;?!]/.test(v))
      .map(([k]) => k)

    // Assert
    expect(straightApostrophe).toEqual([])
    expect(threeDots).toEqual([])
    expect(breakableFrench).toEqual([])
  })

  it("writes Arabic one way: Western digits, the tanwin on the letter before its alif (DESIGN.md §10)", () => {
    // Prepare
    const all = strings(locales.ar as unknown as Tree)

    // Act
    const easternDigits = all.filter(([, v]) => /[٠-٩۰-۹]/.test(v)).map(([k]) => k)
    const tanwinOnAlif = all.filter(([, v]) => /اً/.test(v)).map(([k]) => k)

    // Assert
    expect(easternDigits).toEqual([])
    expect(tanwinOnAlif).toEqual([])
  })

  it("stretches each game's Arabic name once, at a join Naskh allows (DESIGN.md §10)", () => {
    // Prepare: no kashida after a letter that does not join forward, nor after kaf or lam;
    // none before sad, ain, waw, heh, the hah family, feh or qaf (Afifi; Benatia et al. 2006)
    const notJoiningForward = "اأإآدذرزوؤةى"
    const noStretchAfter = "كل"
    const noStretchBefore = "صضعغوهحجخفق"
    const games = ["undercover", "codenames", "wordQuiz", "mcqQuiz"] as const

    // Act
    const offenders = games.flatMap((game) =>
      (["en", "fr", "ar"] as const).flatMap((lang) => {
        const stretched = (locales[lang].home as Tree).fihrist as Record<string, Record<string, string>>
        const name = stretched[game].arabic
        const runs = [...name.matchAll(/ـ+/g)]
        const [run] = runs
        const at = run?.index ?? 0
        const before = run ? name[at - 1] : ""
        const after = run ? name[at + run[0].length] : ""
        const plain = (locales.ar.games as Record<string, Record<string, string>>)[game].name
        const ok =
          runs.length === 1 &&
          name.replace(/ـ/g, "") === plain &&
          !notJoiningForward.includes(before) &&
          !noStretchAfter.includes(before) &&
          !noStretchBefore.includes(after)
        return ok ? [] : [`${lang}:${game}:${name}`]
      }),
    )

    // Assert
    expect(offenders).toEqual([])
  })

  it("has the same keys in English, French and Arabic, everywhere", () => {
    const reference = new Set(keys(locales.en as unknown as Tree))
    for (const lang of ["fr", "ar"] as const) {
      const other = new Set(keys(locales[lang] as unknown as Tree))
      expect(
        [...reference].filter((k) => !other.has(k)),
        `missing in ${lang}`,
      ).toEqual([])
      expect(
        [...other].filter((k) => !reference.has(k)),
        `only in ${lang}`,
      ).toEqual([])
    }
  })
})
