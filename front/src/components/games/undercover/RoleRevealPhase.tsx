import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Chip } from "@/components/ui/chip"
import { RoleMark } from "./Lawh"

interface RoleRevealPhaseProps {
  onDismiss: () => void
}

/**
 * The first reading. The same words for every role, so nobody's screen gives them away:
 * Civilians and Undercovers are never told which side they hold (the canonical rule),
 * only their word, which they read on the tablet beside this. Mr. White learns on his
 * tablet that he has none. The legend says how a role shows once a seat empties.
 *
 * "I understand" (E2E: dismissRoleRevealAll) puts the first reading away.
 */
export const RoleRevealPhase = memo(function RoleRevealPhase({ onDismiss }: RoleRevealPhaseProps) {
  const { t } = useTranslation()
  return (
    <section aria-labelledby="uc-first-reading" className="grid gap-5">
      <div>
        <h2 id="uc-first-reading" className="type-title text-[26px] sm:text-[30px]">
          {t("game.undercover.firstReading.title")}
        </h2>
        <p className="mt-2.5 max-w-[52ch] type-body text-muted-foreground">{t("game.undercover.firstReading.body")}</p>
      </div>
      <div className="grid gap-2.5">
        <p className="text-[14px] leading-normal text-muted-foreground">{t("game.undercover.firstReading.legend")}</p>
        <ul className="flex flex-wrap gap-2" aria-label={t("game.undercover.firstReading.rolesLabel")}>
          {(["civilian", "undercover", "mr_white"] as const).map((role) => (
            <li key={role}>
              <Chip mark={<RoleMark role={role} size={11} />}>
                {t(
                  role === "civilian"
                    ? "games.undercover.roles.civilian"
                    : role === "undercover"
                      ? "games.undercover.roles.undercover"
                      : "games.undercover.roles.mrWhite",
                )}
              </Chip>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <Button size="lg" className="w-full sm:w-auto" onClick={onDismiss}>
          {t("game.undercover.iUnderstand")}
        </Button>
      </div>
    </section>
  )
})
