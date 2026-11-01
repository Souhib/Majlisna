import { Check, Copy, Share } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/field"
import { reportError } from "@/lib/report-error"
import { cn } from "@/lib/utils"
import type { CardInput } from "./model"
import { renderCardFile } from "./render"
import { canShareFiles, errorName } from "./share"

/** How long "Copied" stays on the button. */
const COPIED_MS = 2500

/** The strings' namespace: the word of the day's reveal, or a game's colophon. */
export type ShareCopy = "daily.share" | "game.colophon.share"

interface ShareCardActionProps {
  copy: ShareCopy
  /** The plain line (no emoji, never the word of the day): copied where the card cannot be shared, sent with it where it can. */
  line: string
  /** The share sheet's title. */
  title: string
  /** The PNG's name (plain ASCII). */
  fileName: string
  /** What the card says, read only when the player presses Share. */
  card: () => CardInput
  /** The id of the read-only field the line is set in when the clipboard is refused. */
  fieldId: string
  className?: string
}

/**
 * "Share" (spec 11, the colophon card). Where the browser can share files, the tap
 * draws the card (1080 × 1350 PNG, `render.ts`) and hands it to the system's share
 * sheet with the line; where it cannot, the tap copies the line, as Share always did,
 * and says so ("Copied", and to screen readers); where the clipboard is refused too, the
 * line is set in a read-only field, selected, to copy by hand.
 *
 * Generated on demand only, on the device: nothing is drawn before the tap and nothing
 * is sent anywhere. A share sheet closed without sharing says nothing. A browser that
 * refuses the sheet because the tap's activation ran out while the card was drawn
 * (`NotAllowedError`) keeps the card, says it is ready, and shares that same card on the
 * next tap; a card that cannot be drawn copies the line instead (and is reported).
 */
export function ShareCardAction({ copy, line, title, fileName, card, fieldId, className }: ShareCardActionProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const [manual, setManual] = useState(false)
  const [busy, setBusy] = useState(false)
  const [ready, setReady] = useState(false)
  // decided once for the icon; the tap asks again, at the moment it matters
  const [filesShareable] = useState(() => canShareFiles())
  const pending = useRef<File | null>(null)
  const inFlight = useRef(false)
  const fieldRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!copied) return
    const id = setTimeout(() => setCopied(false), COPIED_MS)
    return () => clearTimeout(id)
  }, [copied])

  useEffect(() => {
    if (manual) fieldRef.current?.select()
  }, [manual])

  const copyLine = async () => {
    try {
      if (!navigator.clipboard) throw new Error("no clipboard")
      await navigator.clipboard.writeText(line)
      setManual(false)
      setCopied(true)
    } catch {
      setManual(true)
    }
  }

  const shareFile = async (file: File) => {
    try {
      await navigator.share({ files: [file], title, text: line })
      pending.current = null
      setReady(false)
    } catch (err) {
      const name = errorName(err)
      if (name === "NotAllowedError") {
        pending.current = file
        setReady(true)
        return
      }
      pending.current = null
      setReady(false)
      // the player closed the sheet: nothing to say
      if (name === "AbortError") return
      await copyLine()
    }
  }

  const onShare = async () => {
    if (inFlight.current) return
    inFlight.current = true
    try {
      if (pending.current) {
        setBusy(true)
        await shareFile(pending.current)
        return
      }
      if (!canShareFiles()) {
        await copyLine()
        return
      }
      setBusy(true)
      let file: File
      try {
        file = await renderCardFile(card(), fileName)
      } catch (err) {
        reportError(err, { source: "Share card not drawn" })
        await copyLine()
        return
      }
      await shareFile(file)
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const icon = copied ? <Check aria-hidden="true" /> : filesShareable ? <Share aria-hidden="true" /> : <Copy aria-hidden="true" />

  return (
    <>
      <Button variant="secondary" className={className} onClick={() => void onShare()} loading={busy} iconStart={icon}>
        {copied ? t(`${copy}.copied`) : t(`${copy}.action`)}
      </Button>
      <p role="status" className={cn(ready ? "w-full text-[14px] text-muted-foreground" : "sr-only")}>
        {ready ? t(`${copy}.ready`) : copied ? t(`${copy}.copiedSr`) : ""}
      </p>
      {manual ? (
        <div className="grid w-full gap-1.5">
          <label htmlFor={fieldId} className="type-label">
            {t(`${copy}.manual`)}
          </label>
          <Input id={fieldId} ref={fieldRef} readOnly value={line} dir="auto" onFocus={(e) => e.currentTarget.select()} />
        </div>
      ) : null}
    </>
  )
}
