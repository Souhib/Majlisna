import * as AvatarPrimitive from "@radix-ui/react-avatar"
import { type ComponentProps } from "react"
import { cn } from "@/lib/utils"

/**
 * Avatar: a player's real profile photo (Google sign-in, uploads) when there is one,
 * otherwise their initials on --surface-2 inside a hairline. Initials are taken from
 * the name's first two words (or its first two letters), so Arabic names work too.
 * Generated faces or illustrations are never a fallback (imagery rules, DESIGN.md).
 *
 * <Avatar name={user.username} src={user.profile_picture_url} size={40} />
 */
export interface AvatarProps extends Omit<ComponentProps<typeof AvatarPrimitive.Root>, "children"> {
  name: string
  src?: string | null
  /** Pixel size (square). Default 36. */
  size?: number
  /** A brass ring: the host, the current speaker. */
  ring?: boolean
  /** The name is already written next to it: hide the avatar from assistive tech (no repeated name). */
  decorative?: boolean
}

export function initialsOf(name: string) {
  const words = name
    .trim()
    .split(/[\s_.-]+/u)
    .filter(Boolean)
  const chars = (s: string) => Array.from(s)
  if (words.length >= 2) return (chars(words[0])[0] + chars(words[1])[0]).toUpperCase()
  return chars(words[0] ?? "?")
    .slice(0, 2)
    .join("")
    .toUpperCase()
}

export function Avatar({ name, src, size = 36, ring = false, decorative = false, className, style, ...props }: AvatarProps) {
  return (
    <AvatarPrimitive.Root
      data-slot="avatar"
      aria-hidden={decorative || undefined}
      className={cn(
        "relative inline-flex shrink-0 overflow-hidden rounded-full border border-line bg-surface-2 align-middle",
        ring && "outline-[1.5px] outline-offset-2 outline-brass",
        className,
      )}
      style={{ width: size, height: size, ...style }}
      {...props}
    >
      {src ? <AvatarPrimitive.Image src={src} alt="" referrerPolicy="no-referrer" className="size-full object-cover" /> : null}
      <AvatarPrimitive.Fallback
        delayMs={src ? 400 : 0}
        className="grid size-full place-items-center font-medium text-muted-foreground num"
        style={{ fontSize: Math.max(11, Math.round(size * 0.36)) }}
        aria-hidden="true"
      >
        {initialsOf(name)}
      </AvatarPrimitive.Fallback>
      {decorative ? null : <span className="sr-only">{name}</span>}
    </AvatarPrimitive.Root>
  )
}
