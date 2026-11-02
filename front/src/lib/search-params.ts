import { parseSearchWith } from "@tanstack/react-router"

/**
 * One search value, as the router reads it: JSON, like TanStack's default parser (which
 * quotes, when it writes an address, any string that would read as JSON, so its own links
 * come back as they went), EXCEPT a number that would not come back as written, which
 * stays the text it was.
 *
 * A share link is written by hand (`/rooms/join?code=…&pin=…`), so nothing quotes its
 * code: JSON read the room code 3E182 as the number 3e+182, the join page sent "3e+182",
 * and the link opened no room. About one code in 2,000 has that shape (digits, E, digits).
 */
export function parseSearchValue(value: string): unknown {
  const parsed: unknown = JSON.parse(value)
  return typeof parsed === "number" && String(parsed) !== value ? value : parsed
}

/** The router's `parseSearch` (main.tsx). */
export const parseSearch = parseSearchWith(parseSearchValue)
