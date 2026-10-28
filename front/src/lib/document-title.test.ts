import { afterEach, describe, expect, it } from "vitest"
import { pushTitle, resetDocumentTitle, setFallbackTitle } from "./document-title"

describe("document title", () => {
  afterEach(() => resetDocumentTitle())

  it("names the page from its route until the page knows better", () => {
    setFallbackTitle("Rooms · Majlisna")
    expect(document.title).toBe("Rooms · Majlisna")
  })

  it("lets the page's own title win over the route's, whichever is set last", () => {
    // children's effects run before their parent's: the page pushes first
    const pop = pushTitle("Yusuf’s majlis · Majlisna")
    setFallbackTitle("Rooms · Majlisna")
    expect(document.title).toBe("Yusuf’s majlis · Majlisna")
    pop()
    expect(document.title).toBe("Rooms · Majlisna")
  })

  it("keeps the latest page title when several are pushed", () => {
    setFallbackTitle("Majlisna")
    const a = pushTitle("A")
    const b = pushTitle("B")
    expect(document.title).toBe("B")
    b()
    expect(document.title).toBe("A")
    a()
    expect(document.title).toBe("Majlisna")
  })
})
