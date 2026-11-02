import { defaultStringifySearch } from "@tanstack/react-router"
import { describe, expect, it } from "vitest"
import { parseSearch } from "./search-params"

/**
 * How the router reads an address's search. A share link is written by hand
 * (`/rooms/join?code=…&pin=…`, components/rooms), not by the router, so its values arrive
 * unquoted: a room code must come back exactly as the link wrote it.
 */
describe("parseSearch", () => {
  it("keeps a room code that reads as a number in exponent form as written", () => {
    // Prepare — a share link for room 3E182 (JSON reads it as 3e+182)
    const search = "?code=3E182&pin=5796"

    // Act
    const parsed = parseSearch(search)

    // Assert — the code as the link wrote it; the PIN, a plain number, as before
    expect(parsed).toEqual({ code: "3E182", pin: 5796 })
  })

  it.each(["1E000", "0E123", "12E34", "999E9"])("keeps the room code %s as written", (code) => {
    expect(parseSearch(`?code=${code}`)).toEqual({ code })
  })

  it("still reads what the router itself writes", () => {
    // Prepare — the router quotes a string that would read as JSON, and writes numbers and objects as JSON
    const written = defaultStringifySearch({ code: "3E182", pin: "0042", page: 2, open: true, filter: { lang: "ar" } })

    // Act
    const parsed = parseSearch(written)

    // Assert
    expect(parsed).toEqual({ code: "3E182", pin: "0042", page: 2, open: true, filter: { lang: "ar" } })
  })

  it("reads plain text and plain numbers as before", () => {
    expect(parseSearch("?code=ABCDE&pin=0123&tab=friends&page=12")).toEqual({ code: "ABCDE", pin: "0123", tab: "friends", page: 12 })
  })

  it("keeps any number that would not come back as written", () => {
    expect(parseSearch("?a=1.50&b=-0&c=12345678901234567890")).toEqual({ a: "1.50", b: "-0", c: "12345678901234567890" })
  })
})
