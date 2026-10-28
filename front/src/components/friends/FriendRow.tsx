import { Link } from "@tanstack/react-router"
import { type ReactNode } from "react"
import { Avatar } from "@/components/ui/avatar"

/**
 * One person in a friends list: avatar and name (both open their page), a second line,
 * and the row's actions at the inline end. On a phone the actions wrap under the name
 * rather than squeezing it.
 */
export function FriendRow({ userId, username, sub, actions }: { userId: string; username: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line px-4 py-3 first:border-t-0 sm:px-[22px]">
      <Link to="/players/$userId" params={{ userId }} className="group -my-1 flex min-h-11 min-w-0 flex-1 basis-48 items-center gap-3 rounded-sm py-1">
        <Avatar name={username} size={40} decorative />
        <span className="grid min-w-0">
          <span dir="auto" className="truncate font-medium underline-offset-[5px] group-hover:underline group-hover:decoration-line-brass-strong">
            {username}
          </span>
          {sub ? <span className="truncate text-[13px] text-muted-foreground">{sub}</span> : null}
        </span>
      </Link>
      {actions ? <div className="ms-auto flex shrink-0 items-center gap-2">{actions}</div> : null}
    </li>
  )
}
