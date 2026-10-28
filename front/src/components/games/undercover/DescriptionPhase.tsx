import { ArrowRight } from "lucide-react"
import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Field, Input } from "@/components/ui/field"
import { DescriptionList, type DescriptionOrderEntry, type TableSeat } from "./DescriptionList"

interface DescriptionPhaseProps {
  descriptionOrder: DescriptionOrderEntry[]
  currentDescriberIndex: number
  descriptions: Record<string, string>
  currentUserId?: string
  /** Every seat (the Mayor, the seats that emptied): the list is the whole table. */
  players?: TableSeat[]
  eliminated?: { user_id: string; role: string }[]
  isMyTurnToDescribe: boolean
  isAlive: boolean
  descriptionInput: string
  descriptionError: string
  isSubmittingDescription: boolean
  onDescriptionInputChange: (value: string) => void
  onSubmitDescription: () => void
}

/**
 * One word each, in turn (sketch D third phone, under the tablet). The heading says whose
 * turn it is ("Your turn to describe" / "Bilal is describing": the E2E helpers wait for
 * those words); the list is the table itself (who spoke, what they wrote, the Mayor, the
 * seats that emptied); the describer gets the composer (#description-input, submit on
 * Enter).
 */
export const DescriptionPhase = memo(function DescriptionPhase({
  descriptionOrder,
  currentDescriberIndex,
  descriptions,
  currentUserId,
  players,
  eliminated,
  isMyTurnToDescribe,
  isAlive,
  descriptionInput,
  descriptionError,
  isSubmittingDescription,
  onDescriptionInputChange,
  onSubmitDescription,
}: DescriptionPhaseProps) {
  const { t } = useTranslation()

  const currentDescriber =
    descriptionOrder.length > 0 && currentDescriberIndex < descriptionOrder.length
      ? descriptionOrder[currentDescriberIndex]
      : null

  const title = isMyTurnToDescribe
    ? t("game.undercover.yourTurnToDescribe")
    : currentDescriber
      ? t("game.undercover.describingTitle", { username: currentDescriber.username })
      : t("game.undercover.allDescriptionsIn")

  return (
    <section aria-labelledby="uc-describe-title" className="grid gap-5">
      <div aria-live="polite">
        <h2
          id="uc-describe-title"
          className={isMyTurnToDescribe ? "type-title text-[26px] text-brass sm:text-[30px]" : "type-title text-[26px] sm:text-[30px]"}
        >
          {title}
        </h2>
      </div>

      {isMyTurnToDescribe && isAlive ? (
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault()
            onSubmitDescription()
          }}
        >
          <Field
            id="description-input"
            label={t("game.undercover.describeInOneWord")}
            hint={t("game.undercover.oneWordHint")}
            error={descriptionError || undefined}
          >
            <div className="flex gap-2.5">
              <Input
                value={descriptionInput}
                onChange={(e) => onDescriptionInputChange(e.target.value)}
                maxLength={50}
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
                enterKeyHint="send"
                disabled={isSubmittingDescription}
                className="min-w-0 flex-1"
              />
              <Button
                type="submit"
                loading={isSubmittingDescription}
                disabled={!descriptionInput.trim()}
                iconEnd={<ArrowRight className="rtl-flip" aria-hidden="true" />}
              >
                {t("game.undercover.submitDescription")}
              </Button>
            </div>
          </Field>
        </form>
      ) : null}

      <DescriptionList
        order={descriptionOrder}
        descriptions={descriptions}
        currentIndex={currentDescriberIndex}
        currentUserId={currentUserId}
        mode="describing"
        players={players}
        eliminated={eliminated}
      />
    </section>
  )
})
