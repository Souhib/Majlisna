import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { GameCardInput } from "../model"

const renderCardFile = vi.hoisted(() => vi.fn())
vi.mock("../render", () => ({ renderCardFile }))

const { ShareCardAction } = await import("../ShareCardAction")

/**
 * "Share" on a colophon (spec 11): the card as a PNG through the share sheet where the
 * browser can share files, otherwise today's line copied (or set in a read-only field
 * when the clipboard is refused). Generated on demand only, and never over the network.
 */

const card: GameCardInput = { kind: "game", dir: "ltr", arabicName: "أندركفـــر", meta: ["Undercover"], footer: "majlisna.app", words: [] }
const png = new File(["png"], "majlisna-undercover.png", { type: "image/png" })

function domError(name: string) {
  return Object.assign(new Error(name), { name })
}

function stubShare({ canShare = true, share = vi.fn(async () => {}) }: { canShare?: boolean; share?: ReturnType<typeof vi.fn> } = {}) {
  const canShareFn = vi.fn(() => canShare)
  Object.defineProperty(navigator, "canShare", { value: canShareFn, configurable: true })
  Object.defineProperty(navigator, "share", { value: share, configurable: true })
  return { canShare: canShareFn, share }
}

function stubClipboard(writeText = vi.fn(async () => {})) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true })
  return writeText
}

const makeCard = vi.fn(() => card)

function renderAction() {
  return render(
    <ShareCardAction
      copy="game.colophon.share"
      line="Majlisna · Undercover · majlisna.app"
      title="Undercover"
      fileName="majlisna-undercover.png"
      card={makeCard}
      fieldId="share-line"
    />,
  )
}

const fetchSpy = vi.fn()

beforeEach(() => {
  renderCardFile.mockReset()
  renderCardFile.mockResolvedValue(png)
  makeCard.mockClear()
  fetchSpy.mockReset()
  vi.stubGlobal("fetch", fetchSpy)
})

afterEach(() => {
  vi.unstubAllGlobals()
  for (const key of ["canShare", "share", "clipboard"]) delete (navigator as unknown as Record<string, unknown>)[key]
})

describe("ShareCardAction", () => {
  it("makes the card only when pressed, then hands the PNG to the share sheet with the line", async () => {
    // Prepare
    const { share } = stubShare()
    const writeText = stubClipboard()
    renderAction()
    expect(makeCard).not.toHaveBeenCalled()
    expect(renderCardFile).not.toHaveBeenCalled()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "game.colophon.share.action" }))

    // Assert
    await waitFor(() => expect(share).toHaveBeenCalledTimes(1))
    expect(renderCardFile).toHaveBeenCalledWith(card, "majlisna-undercover.png")
    expect(share).toHaveBeenCalledWith({ files: [png], title: "Undercover", text: "Majlisna · Undercover · majlisna.app" })
    expect(writeText).not.toHaveBeenCalled()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("says nothing when the player closes the share sheet", async () => {
    // Prepare
    const { share } = stubShare({ share: vi.fn(async () => Promise.reject(domError("AbortError"))) })
    const writeText = stubClipboard()
    renderAction()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "game.colophon.share.action" }))

    // Assert
    await waitFor(() => expect(share).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByRole("button", { name: "game.colophon.share.action" })).not.toHaveAttribute("aria-busy"))
    expect(writeText).not.toHaveBeenCalled()
    expect(screen.getByRole("status")).toHaveTextContent("")
  })

  it("keeps a card the browser would not share without a fresh tap, and shares that same card on the next one", async () => {
    // Prepare: the tap's activation ran out while the card was being drawn
    const share = vi.fn().mockRejectedValueOnce(domError("NotAllowedError")).mockResolvedValueOnce(undefined)
    stubShare({ share })
    renderAction()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "game.colophon.share.action" }))

    // Assert: said on the page, in a polite status
    expect(await screen.findByText("game.colophon.share.ready")).toHaveAttribute("role", "status")

    // Act: the second tap shares at once, without drawing again
    fireEvent.click(screen.getByRole("button", { name: "game.colophon.share.action" }))

    // Assert
    await waitFor(() => expect(share).toHaveBeenCalledTimes(2))
    expect(renderCardFile).toHaveBeenCalledTimes(1)
    expect(share.mock.calls[1][0]).toMatchObject({ files: [png] })
    await waitFor(() => expect(screen.queryByText("game.colophon.share.ready")).not.toBeInTheDocument())
  })

  it("copies the line where the browser cannot share files (today's behaviour), and draws nothing", async () => {
    // Prepare
    const writeText = stubClipboard()
    renderAction()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "game.colophon.share.action" }))

    // Assert
    expect(await screen.findByRole("button", { name: "game.colophon.share.copied" })).toBeInTheDocument()
    expect(writeText).toHaveBeenCalledWith("Majlisna · Undercover · majlisna.app")
    expect(screen.getByRole("status")).toHaveTextContent("game.colophon.share.copiedSr")
    expect(renderCardFile).not.toHaveBeenCalled()
    expect(makeCard).not.toHaveBeenCalled()
  })

  it("copies the line when the browser says it cannot share this file", async () => {
    // Prepare
    const { share } = stubShare({ canShare: false })
    const writeText = stubClipboard()
    renderAction()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "game.colophon.share.action" }))

    // Assert
    await waitFor(() => expect(writeText).toHaveBeenCalled())
    expect(share).not.toHaveBeenCalled()
  })

  it("copies the line when the card cannot be drawn", async () => {
    // Prepare
    const { share } = stubShare()
    const writeText = stubClipboard()
    const failure = new Error("no 2D context")
    renderCardFile.mockRejectedValue(failure)
    const said = vi.spyOn(console, "error").mockImplementation(() => {})
    renderAction()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "game.colophon.share.action" }))

    // Assert
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Majlisna · Undercover · majlisna.app"))
    expect(share).not.toHaveBeenCalled()
    // not swallowed: said, and reported (lib/report-error)
    expect(said).toHaveBeenCalledWith("Share card not drawn:", failure)
    said.mockRestore()
  })

  it("sets the line in a read-only field, selected, when the clipboard is refused", async () => {
    // Prepare
    stubClipboard(vi.fn(async () => Promise.reject(new Error("denied"))))
    renderAction()

    // Act
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "game.colophon.share.action" }))
    })

    // Assert
    const field = await screen.findByLabelText("game.colophon.share.manual")
    expect(field).toHaveValue("Majlisna · Undercover · majlisna.app")
    expect(field).toHaveAttribute("readonly")
    expect(field).toHaveAttribute("id", "share-line")
  })
})
