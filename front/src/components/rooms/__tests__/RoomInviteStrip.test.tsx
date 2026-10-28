import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { RoomInviteStrip } from "../RoomInviteStrip"

const invite = { roomId: "r1", publicId: "LULIM", password: "6981", invitedBy: "Yusuf" }

describe("RoomInviteStrip (a friend's invite, never a toast)", () => {
  it("is a named strip with a polite status line, and takes no focus", () => {
    const before = document.activeElement
    render(<RoomInviteStrip invite={invite} onJoin={vi.fn()} onDismiss={vi.fn()} />)
    expect(screen.getByRole("region", { name: "room.inviteLabel" })).toBeInTheDocument()
    expect(screen.getByRole("status")).toBeInTheDocument()
    expect(document.activeElement).toBe(before)
  })

  it("joins or waits", () => {
    const onJoin = vi.fn()
    const onDismiss = vi.fn()
    render(<RoomInviteStrip invite={invite} onJoin={onJoin} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByRole("button", { name: "room.joinInvite" }))
    fireEvent.click(screen.getByRole("button", { name: "room.inviteLater" }))
    expect(onJoin).toHaveBeenCalledOnce()
    expect(onDismiss).toHaveBeenCalledOnce()
  })
})
