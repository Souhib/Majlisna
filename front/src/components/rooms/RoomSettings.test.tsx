import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { RoomSettings } from "./RoomSettings"

const mutateAsync = vi.fn().mockResolvedValue({})

vi.mock("@/api/generated", () => ({
  useUpdateRoomSettingsApiV1RoomsRoomIdSettingsPatch: () => ({
    mutateAsync,
    isPending: false,
  }),
}))

vi.mock("@/api/client", () => ({
  getApiErrorMessage: (err: unknown) => String(err),
}))

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    roomId: "room-1",
    settings: null,
    gameType: "undercover" as const,
    playerCount: 5,
    ...overrides,
  }
}

function open() {
  fireEvent.click(screen.getByRole("button", { name: /room\.settingsPanel\.title/ }))
}

describe("RoomSettings", () => {
  it("renders the settings heading, closed", () => {
    render(<RoomSettings {...defaultProps()} />)
    expect(screen.getByText("room.settingsPanel.title")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /room\.settingsPanel\.title/ })).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByText("room.settingsPanel.descriptionTimer")).not.toBeInTheDocument()
  })

  it("opens and closes from its header", () => {
    render(<RoomSettings {...defaultProps()} />)
    open()
    expect(screen.getByRole("button", { name: /room\.settingsPanel\.title/ })).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText("room.settingsPanel.descriptionTimer")).toBeInTheDocument()
    open()
    expect(screen.queryByText("room.settingsPanel.descriptionTimer")).not.toBeInTheDocument()
  })

  it("shows undercover settings for undercover game type", () => {
    render(<RoomSettings {...defaultProps({ gameType: "undercover" })} />)
    open()
    expect(screen.getByText("room.settingsPanel.descriptionTimer")).toBeInTheDocument()
    expect(screen.getByText("room.settingsPanel.votingTimer")).toBeInTheDocument()
    expect(screen.getByRole("switch", { name: "room.enableMrWhite" })).toBeInTheDocument()
  })

  it("shows codenames settings for codenames game type", () => {
    render(<RoomSettings {...defaultProps({ gameType: "codenames" })} />)
    open()
    expect(screen.getByText("room.settingsPanel.clueTimer")).toBeInTheDocument()
    expect(screen.getByText("room.settingsPanel.guessTimer")).toBeInTheDocument()
  })

  it("shows word quiz settings for word_quiz game type", () => {
    render(<RoomSettings {...defaultProps({ gameType: "word_quiz" })} />)
    open()
    expect(screen.getByText("room.settingsPanel.wordQuizTurn")).toBeInTheDocument()
    expect(screen.getByText("room.settingsPanel.wordQuizRounds")).toBeInTheDocument()
    expect(screen.getByText("room.settingsPanel.wordQuizHintInterval")).toBeInTheDocument()
  })

  it("shows mcq quiz settings for mcq_quiz game type", () => {
    render(<RoomSettings {...defaultProps({ gameType: "mcq_quiz" })} />)
    open()
    expect(screen.getByText("room.settingsPanel.mcqQuizTurn")).toBeInTheDocument()
    expect(screen.getByText("room.settingsPanel.mcqQuizRounds")).toBeInTheDocument()
  })

  it.each([3, 4])("keeps Mr. White off and says why with %i players", (playerCount) => {
    render(<RoomSettings {...defaultProps({ playerCount })} />)
    open()
    const mrWhite = screen.getByRole("switch", { name: "room.enableMrWhite" })
    expect(mrWhite).toBeDisabled()
    expect(mrWhite).toHaveAttribute("aria-checked", "false")
    expect(screen.getByText("room.mrWhiteMinPlayers")).toBeInTheDocument()
  })

  it("lets the host turn Mr. White off from five players and saves the choice", async () => {
    // Prepare
    mutateAsync.mockClear()
    render(<RoomSettings {...defaultProps({ playerCount: 5 })} />)
    open()
    const mrWhite = screen.getByRole("switch", { name: "room.enableMrWhite" })
    expect(mrWhite).toHaveAttribute("aria-checked", "true")

    // Act
    fireEvent.click(mrWhite)
    fireEvent.click(screen.getByRole("button", { name: "common.save" }))

    // Assert
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        room_id: "room-1",
        data: { description_timer: 0, voting_timer: 0, enable_mr_white: false },
      }),
    )
  })

  it("keeps unsaved choices when the room pushes the same settings again", () => {
    // Prepare
    const settings = { description_timer: 30 }
    const { rerender } = render(<RoomSettings {...defaultProps({ settings })} />)
    open()
    const radio60 = screen.getAllByRole("radio")[4]

    // Act: pick 60 s, then a socket push brings an equal-but-new settings object
    fireEvent.click(radio60)
    rerender(<RoomSettings {...defaultProps({ settings: { description_timer: 30 } })} />)

    // Assert
    expect(screen.getAllByRole("radio")[4]).toBeChecked()
  })
})
