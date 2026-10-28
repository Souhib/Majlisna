import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import type { ColophonSeal } from "@/components/brand"
import { listFormat } from "./quiz-utils"

interface UnlockedAchievement {
  code: string
  name: string
  tier: number
}

interface AchievementNotification {
  user_id: string
  achievements: UnlockedAchievement[]
}

interface SealDraft {
  code: string
  name: string
  tier: number
  you: boolean
  others: string[]
  seen: Set<string>
}

/**
 * Achievements unlocked in this game, as colophon seals: ONE seal per achievement,
 * captioned with everyone at the table who earned it, you first, in the reader's
 * language, then the tier ("Taste of Victory · you and Maryam · Bronze"). Seals you
 * earned come first. DESIGN.md: achievements are sealed at the end of the game, never
 * toasted in the middle of it. Shared by the four games' colophons.
 */
export function useAchievementSeals(
  notifications: AchievementNotification[] | null | undefined,
  players: { user_id: string; username: string }[] | undefined,
  currentUserId: string | undefined,
): ColophonSeal[] {
  const { t, i18n } = useTranslation()
  const language = i18n.language
  return useMemo(() => {
    if (!notifications?.length) return []
    const names = new Map((players ?? []).map((p) => [p.user_id, p.username]))
    const byCode = new Map<string, SealDraft>()
    for (const entry of notifications) {
      for (const achievement of entry.achievements) {
        let draft = byCode.get(achievement.code)
        if (!draft) {
          draft = { code: achievement.code, name: achievement.name, tier: achievement.tier, you: false, others: [], seen: new Set() }
          byCode.set(achievement.code, draft)
        }
        if (draft.seen.has(entry.user_id)) continue
        draft.seen.add(entry.user_id)
        if (entry.user_id === currentUserId) draft.you = true
        else {
          const name = names.get(entry.user_id)
          if (name) draft.others.push(name)
        }
      }
    }
    return [...byCode.values()]
      .sort((a, b) => Number(b.you) - Number(a.you))
      .map((draft) => {
        const who = [...(draft.you ? [t("game.quiz.you")] : []), ...draft.others]
        const tier = t(`achievements.tiers.${draft.tier}`, { defaultValue: "" })
        const caption = [who.length > 0 ? listFormat(who, language) : "", tier].filter(Boolean).join(" · ")
        return {
          title: t(`achievements.items.${draft.code}.name`, { defaultValue: draft.name }),
          caption: caption || undefined,
        }
      })
  }, [notifications, players, currentUserId, t, language])
}
