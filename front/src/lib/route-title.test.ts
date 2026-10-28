import type { TFunction } from "i18next"
import { describe, expect, it } from "vitest"
import { titleForPath } from "./route-title"

const t = ((key: string, opts?: { title?: string }) => (key === "meta.pageTitle" ? `${opts?.title} · Majlisna` : key)) as unknown as TFunction

describe("titleForPath", () => {
  it("names each page by its own heading key", () => {
    expect(titleForPath("/notebook", t)).toBe("notebook.title · Majlisna")
    expect(titleForPath("/rooms", t)).toBe("nav.rooms · Majlisna")
    expect(titleForPath("/rooms/create", t)).toBe("room.createPage.title · Majlisna")
    expect(titleForPath("/game/codenames/g1", t)).toBe("games.codenames.name · Majlisna")
    expect(titleForPath("/game/wordquiz/g1", t)).toBe("games.wordQuiz.name · Majlisna")
  })

  it("falls back to the site's own title (the home, an unknown path)", () => {
    expect(titleForPath("/", t)).toBe("meta.defaultTitle")
    expect(titleForPath("/nope", t)).toBe("meta.defaultTitle")
  })
})
