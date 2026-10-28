import { type ClipboardEvent, type KeyboardEvent, useId, useRef, useState } from "react"
import { cn } from "@/lib/utils"

/**
 * Glazed letter tiles for the room code and PIN: zellige reduced to a material (sand,
 * light above, shadow below, a brass base on the active tile). ALWAYS left to right,
 * also in Arabic, because codes are read aloud across mixed tables; figures are
 * tabular. Each group is labelled.
 *
 * Display (the lobby):
 *   <CodeTiles label="Room code" value="LULIM" />
 *   <CodeTiles label="PIN" value="6981" kind="pin" />
 *
 * Input (the join form): see CodeTilesInput below.
 */
type TileSize = "sm" | "md" | "lg"

export interface CodeTilesProps {
  value: string
  /** Visible group label ("Room code", "PIN"); also names the group for assistive tech. */
  label?: string
  /** Number of tiles (pads with empty tiles). Defaults to value length. */
  length?: number
  kind?: "code" | "pin"
  size?: TileSize
  className?: string
}

export function CodeTiles({ value, label, length, kind = "code", size = "md", className }: CodeTilesProps) {
  const labelId = useId()
  const n = Math.max(length ?? value.length, value.length)
  const chars = Array.from({ length: n }, (_, i) => value[i] ?? "")
  return (
    <div className={cn("grid gap-1.5", className)}>
      {label ? (
        <span id={labelId} className="type-label">
          {label}
        </span>
      ) : null}
      <span
        role="group"
        aria-labelledby={label ? labelId : undefined}
        aria-label={label ? undefined : value}
        className="code-tiles"
        data-size={size}
        data-kind={kind}
      >
        {chars.map((c, i) => (
          <span key={i} className="code-tile" aria-hidden={label ? undefined : true}>
            {c}
          </span>
        ))}
        {label ? <span className="sr-only">{value.split("").join(" ")}</span> : null}
      </span>
    </div>
  )
}

/**
 * CodeTilesInput: the same tiles, typed into. Two modes, both keyboard-friendly and
 * paste-able:
 *
 * - single (default): ONE real <input> laid transparently over the tiles. It keeps the
 *   id you give it (the join form's `id="room-code"`, which E2E fills), takes the whole
 *   code, filters it through `charset`, and paints each character on its tile with the
 *   brass caret on the next empty one.
 *
 * - split: one <input> per tile (the PIN). Typing advances, Backspace on an empty tile
 *   steps back, arrows move, and pasting "6981" anywhere fills from that tile. Each
 *   input is named by `cellLabel(i)` (E2E fills `input[aria-label="Password digit N"]`).
 *
 *   <CodeTilesInput id="room-code" label={t("room.roomCode")} length={5}
 *                   value={code} onChange={setCode} charset="alnum" autoFocus />
 *   <CodeTilesInput split label={t("room.password")} length={4} kind="pin"
 *                   value={pin} onChange={setPin} charset="digits"
 *                   cellLabel={(i) => `Password digit ${i + 1}`} />
 *
 * `value` is the joined string in both modes.
 */
export interface CodeTilesInputProps {
  value: string
  onChange: (value: string) => void
  length: number
  label?: string
  /** Visually hide the label (it still names the input). */
  hideLabel?: boolean
  /** Id of the single input (or prefix for split inputs). */
  id?: string
  split?: boolean
  charset?: "alnum" | "digits"
  kind?: "code" | "pin"
  size?: TileSize
  /** Accessible name of split input `i` (0-based). */
  cellLabel?: (index: number) => string
  /** Placeholder read by assistive tech on the single input. */
  placeholder?: string
  autoFocus?: boolean
  disabled?: boolean
  invalid?: boolean
  /** Id of a hint or error that describes the field. */
  describedBy?: string
  className?: string
}

function clean(raw: string, charset: "alnum" | "digits") {
  return charset === "digits" ? raw.replace(/\D/g, "") : raw.replace(/[^a-zA-Z0-9]/g, "").toUpperCase()
}

export function CodeTilesInput({
  value,
  onChange,
  length,
  label,
  hideLabel,
  id,
  split = false,
  charset = "alnum",
  kind = "code",
  size = "md",
  cellLabel,
  placeholder,
  autoFocus,
  disabled,
  invalid,
  describedBy,
  className,
}: CodeTilesInputProps) {
  const generated = useId()
  const inputId = id ?? `code-${generated}`
  const labelId = `${inputId}-label`
  const [focused, setFocused] = useState(false)
  const cells = useRef<(HTMLInputElement | null)[]>([])
  const chars = Array.from({ length }, (_, i) => value[i] ?? "")

  const setAt = (index: number, ch: string) => {
    const next = chars.slice()
    next[index] = ch
    onChange(next.join("").slice(0, length))
  }

  const fillFrom = (index: number, text: string) => {
    const incoming = clean(text, charset).slice(0, length - index)
    if (!incoming) return
    const next = chars.slice()
    Array.from(incoming).forEach((c, k) => {
      next[index + k] = c
    })
    onChange(next.join("").slice(0, length))
    cells.current[Math.min(index + incoming.length, length - 1)]?.focus()
  }

  const onCellKeyDown = (index: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !chars[index] && index > 0) {
      e.preventDefault()
      setAt(index - 1, "")
      cells.current[index - 1]?.focus()
    } else if (e.key === "ArrowLeft" && index > 0) {
      e.preventDefault()
      cells.current[index - 1]?.focus()
    } else if (e.key === "ArrowRight" && index < length - 1) {
      e.preventDefault()
      cells.current[index + 1]?.focus()
    }
  }

  const onCellPaste = (index: number, e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault()
    fillFrom(index, e.clipboardData.getData("text"))
  }

  return (
    <div className={cn("grid gap-1.5", className)}>
      {label ? (
        <label id={labelId} htmlFor={split ? `${inputId}-0` : inputId} className={cn("type-label", hideLabel && "sr-only")}>
          {label}
        </label>
      ) : null}
      {split ? (
        <div role="group" aria-labelledby={label ? labelId : undefined} className="code-tiles" data-size={size} data-kind={kind}>
          {chars.map((c, i) => (
            <input
              key={i}
              ref={(el) => {
                cells.current[i] = el
              }}
              id={`${inputId}-${i}`}
              className="code-tile"
              data-invalid={invalid || undefined}
              type="text"
              inputMode={charset === "digits" ? "numeric" : "text"}
              pattern={charset === "digits" ? "\\d*" : undefined}
              autoComplete="off"
              maxLength={1}
              value={c}
              disabled={disabled}
              autoFocus={autoFocus && i === 0}
              aria-label={cellLabel ? cellLabel(i) : undefined}
              aria-invalid={invalid || undefined}
              aria-describedby={describedBy}
              onChange={(e) => {
                const v = clean(e.target.value, charset)
                const ch = v.slice(-1)
                if (e.target.value && !ch) return
                setAt(i, ch)
                if (ch && i < length - 1) cells.current[i + 1]?.focus()
              }}
              onKeyDown={(e) => onCellKeyDown(i, e)}
              onPaste={(e) => onCellPaste(i, e)}
              onFocus={(e) => e.currentTarget.select()}
            />
          ))}
        </div>
      ) : (
        <div className="code-tiles" data-size={size} data-kind={kind}>
          {chars.map((c, i) => (
            <span
              key={i}
              aria-hidden="true"
              className="code-tile"
              data-invalid={invalid || undefined}
              data-active={focused && !disabled && i === Math.min(value.length, length - 1) && !c ? true : undefined}
            >
              {c}
            </span>
          ))}
          <input
            id={inputId}
            className="code-tiles-input"
            type="text"
            inputMode={charset === "digits" ? "numeric" : "text"}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={length}
            value={value}
            placeholder={placeholder}
            disabled={disabled}
            autoFocus={autoFocus}
            aria-invalid={invalid || undefined}
            aria-describedby={describedBy}
            onChange={(e) => onChange(clean(e.target.value, charset).slice(0, length))}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
          />
        </div>
      )}
    </div>
  )
}
