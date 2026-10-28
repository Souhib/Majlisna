import { useNavigate } from "@tanstack/react-router"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { CodeTilesInput } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const CODE_LENGTH = 5
const PIN_LENGTH = 4
const CODE_INPUT_ID = "home-room-code"

/** Put the caret in the hero's room code (the example halqa's "Take your seat"). */
export function focusHeroJoin() {
  const input = document.getElementById(CODE_INPUT_ID) as HTMLInputElement | null
  if (!input) return
  input.focus({ preventScroll: true })
  input.scrollIntoView({ block: "center", behavior: "smooth" })
}

/**
 * The hero's join row: room code (5 tiles), PIN (4 tiles), Join. Always left to right,
 * as one continuous row, in every language (codes are read aloud at mixed tables).
 *
 * It does not join by itself: it hands the code and PIN to /rooms/join, the share-link
 * route, which performs the join and opens the lobby. That route sits behind the auth
 * gate, so a visitor who is not signed in goes through the login and lands in the room.
 */
export function HeroJoinForm({ className }: { className?: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [code, setCode] = useState("")
  const [pin, setPin] = useState("")
  const [showError, setShowError] = useState(false)
  const complete = code.length === CODE_LENGTH && pin.length === PIN_LENGTH

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!complete) {
      setShowError(true)
      return
    }
    navigate({ to: "/rooms/join", search: { code, pin } })
  }

  const invalid = showError && !complete

  return (
    <div className={className}>
      <form
        className="home-join [&_label]:text-[12px] [&_label]:font-normal max-[760px]:[&_label]:text-[13px] min-[2200px]:[&_label]:text-[13.5px]"
        onSubmit={onSubmit}
        aria-label={t("home.join.label")}
        noValidate
      >
        <CodeTilesInput
          id={CODE_INPUT_ID}
          label={t("home.join.code")}
          length={CODE_LENGTH}
          size="sm"
          value={code}
          onChange={(v) => {
            setCode(v)
            if (showError) setShowError(false)
          }}
          charset="alnum"
          invalid={invalid && code.length !== CODE_LENGTH}
          describedBy={invalid ? "home-join-error" : undefined}
        />
        <CodeTilesInput
          id="home-pin"
          split
          kind="pin"
          label={t("home.join.pin")}
          length={PIN_LENGTH}
          size="sm"
          value={pin}
          onChange={(v) => {
            setPin(v)
            if (showError) setShowError(false)
          }}
          charset="digits"
          cellLabel={(i) => t("home.join.pinDigit", { n: i + 1 })}
          invalid={invalid && pin.length !== PIN_LENGTH}
          describedBy={invalid ? "home-join-error" : undefined}
        />
        <Button
          type="submit"
          variant="secondary"
          size="sm"
          className={cn("join-submit h-9 px-3.5 pointer-coarse:h-12 max-[760px]:h-12 min-[2200px]:h-11 min-[2200px]:text-[15.5px]")}
        >
          {t("home.join.submit")}
        </Button>
      </form>
      {invalid ? (
        <p id="home-join-error" role="alert" className="home-join-error">
          {t("home.join.incomplete")}
        </p>
      ) : null}
    </div>
  )
}
