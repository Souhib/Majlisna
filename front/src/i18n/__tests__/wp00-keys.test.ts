import i18next from "i18next"
import { describe, expect, it } from "vitest"
import ar from "@/i18n/locales/ar.json"
import en from "@/i18n/locales/en.json"
import fr from "@/i18n/locales/fr.json"

/**
 * The keys the audit's shared contracts (WP-00) declared ahead of the screens that read
 * them. Wave-1 packages reference these names verbatim, so a rename breaks here first.
 * (Key parity across the three locales is `components/stats/__tests__/locales.test.ts`.)
 */
const CONTRACT_KEYS = [
  "errors.network",
  "errors.api.clueMustBeOneWord",
  "errors.api.descriptionRevealsWord",
  "errors.api.answerAttemptsExhausted",
  "errors.api.roomBanned",
  "errors.api.roomBanNotFound",
  "errors.api.passwordTooLong",
  "errors.api.sessionRevoked",
  "errors.api.notAnAlivePlayer",
  "errors.api.invalidAvatarUrl",
  "errors.api.googleAccountMismatch",
  "common.loadFailed",
  "common.retry",
  "game.errors.answerFailed",
  "game.errors.moveFailed",
  "game.errors.startFailed",
  "game.errors.nextRoundFailed",
  "game.quiz.sharedWin",
  "game.quiz.noWinner",
  "game.undercover.verdict.imReady",
  // a count: its plural forms (review F4), "_other" in every language
  "game.undercover.verdict.readyCount_other",
  "game.undercover.verdict.youAreReady",
  "room.joinPage.alreadyInRoom",
  "room.joinPage.leaveAndJoin",
  "room.lobbyPage.joinThisRoom",
  "room.lobbyPage.kickConfirmTitle",
  "room.lobbyPage.kickConfirmBody",
  "room.lobbyPage.kickConfirmAction",
  // kick and ban, two host actions (owner decision, 2 November 2026)
  "room.lobbyPage.ban",
  "room.lobbyPage.banFailed",
  "room.lobbyPage.banConfirmTitle",
  "room.lobbyPage.banConfirmBody",
  "room.lobbyPage.banConfirmAction",
  "room.lobbyPage.activityRemoved",
  "room.lobbyPage.activityBanned",
  "room.youWereKicked",
  "room.youWereBanned",
  "room.youWereRemoved",
  "room.invite.banned",
  "errors.api.inviteeBanned",
  "errors.api.cannotBanYourself",
  "room.lobbyPage.bans.title",
  "room.lobbyPage.bans.liftBan",
  "room.lobbyPage.bans.empty",
  "room.lobbyPage.bans.liftFailed",
  "prayer.myLocation",
  "profile.deleteAccountConfirmWithGoogle",
  "auth.sessionRevoked",
  // privacy.googleScriptSignInPagesOnly shipped with WP-05: its text is now
  // privacy.sections[6].body[0] (the Google script loads on the sign-in pages only).
] as const

type Tree = { [key: string]: string | Tree }
const LOCALES = { en, fr, ar } as unknown as Record<"en" | "fr" | "ar", Tree>

function lookup(tree: Tree, path: string): string | Tree | undefined {
  return path.split(".").reduce<string | Tree | undefined>((node, part) => (typeof node === "object" ? node[part] : undefined), tree)
}

describe("the WP-00 locale contract", () => {
  it.each(["en", "fr", "ar"] as const)("declares every contract key in %s, as a non-empty string", (lang) => {
    // Act
    const missing = CONTRACT_KEYS.filter((key) => {
      const value = lookup(LOCALES[lang], key)
      return typeof value !== "string" || value.trim() === ""
    })

    // Assert
    expect(missing).toEqual([])
  })

  it("keeps the interpolations each screen passes", () => {
    for (const lang of ["en", "fr", "ar"] as const) {
      // Assert
      expect(lookup(LOCALES[lang], "errors.api.answerAttemptsExhausted"), lang).toContain("{{max}}")
      expect(lookup(LOCALES[lang], "game.quiz.sharedWin"), lang).toContain("{{names}}")
      expect(lookup(LOCALES[lang], "game.undercover.verdict.readyCount_other"), lang).toMatch(/\{\{ready\}\}.*\{\{total\}\}|\{\{total\}\}.*\{\{ready\}\}/)
      expect(lookup(LOCALES[lang], "room.joinPage.leaveAndJoin"), lang).toContain("{{room}}")
      expect(lookup(LOCALES[lang], "room.lobbyPage.bans.liftBan"), lang).toContain("{{name}}")
      expect(lookup(LOCALES[lang], "room.lobbyPage.kickConfirmBody"), lang).toContain("{{name}}")
      for (const key of [
        "room.lobbyPage.ban",
        "room.lobbyPage.banConfirmTitle",
        "room.lobbyPage.banConfirmBody",
        "room.lobbyPage.activityRemoved",
        "room.lobbyPage.activityBanned",
      ]) {
        expect(lookup(LOCALES[lang], key), `${lang} ${key}`).toContain("{{name}}")
      }
    }
  })

  it("never starts an Undercover round-over line with “Waiting for” (the E2E helpers read that as a vote)", () => {
    // Prepare
    const verdict = lookup(LOCALES.en, "game.undercover.verdict") as Tree

    // Act
    const offenders = Object.entries(verdict).filter(([, v]) => typeof v === "string" && /^waiting for/i.test(v))

    // Assert
    expect(offenders).toEqual([])
  })

  it("counts the Undercover ready players with every plural form (review F4)", async () => {
    // Prepare
    const i18n = i18next.createInstance()
    await i18n.init({
      resources: { en: { translation: en }, fr: { translation: fr }, ar: { translation: ar } },
      lng: "ar",
      interpolation: { escapeValue: false },
    })
    const line = (ready: number, total: number, lng: string) => i18n.t("game.undercover.verdict.readyCount", { count: ready, ready, total, lng })

    // Act / Assert — "1 sur 2 prêts" and "1 من 2 جاهزون" were the live screens
    expect(line(1, 2, "fr")).toBe("1 sur 2 prêt")
    expect(line(0, 2, "fr")).toBe("0 sur 2 prêt")
    expect(line(2, 3, "fr")).toBe("2 sur 3 prêts")
    expect(line(1, 2, "ar")).toBe("1 من 2 جاهز")
    expect(line(2, 3, "ar")).toBe("2 من 3 جاهزان")
    expect(line(3, 4, "ar")).toBe("3 من 4 جاهزون")
    expect(line(1, 2, "en")).toBe("1 of 2 ready")
    expect(line(3, 4, "en")).toBe("3 of 4 ready")
  })

  it("counts Kalimat tries with every plural form, Arabic's six included", async () => {
    // Prepare
    const i18n = i18next.createInstance()
    await i18n.init({
      resources: { en: { translation: en }, fr: { translation: fr }, ar: { translation: ar } },
      lng: "ar",
      interpolation: { escapeValue: false },
    })

    // Act / Assert: zero, one, two, few (3-10), many (11-99), other (100+)
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 0 })).toBe("لم تبقَ محاولات")
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 1 })).toBe("بقيت محاولة واحدة")
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 2 })).toBe("بقيت محاولتان")
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 4 })).toBe("بقيت 4 محاولات")
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 11 })).toBe("بقيت 11 محاولةً")
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 100 })).toBe("بقيت 100 محاولة")
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 0, lng: "en" })).toBe("No tries left")
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 1, lng: "en" })).toBe("1 try left")
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 3, lng: "en" })).toBe("3 tries left")
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 1, lng: "fr" })).toBe("1 essai restant")
    expect(i18n.t("game.wordQuiz.triesLeft", { count: 4, lng: "fr" })).toBe("4 essais restants")
  })
})
