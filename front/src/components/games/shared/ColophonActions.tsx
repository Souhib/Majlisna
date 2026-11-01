import { LogOut, RotateCcw } from "lucide-react"
import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { useRematchApiV1RoomsRoomIdRematchPost } from "@/api/generated"
import { type ColophonShare, gameCardFileName, gameCardInput, gameName, gameShareLine } from "@/components/brand/share-card/game-card"
import { ShareCardAction } from "@/components/brand/share-card/ShareCardAction"
import { KeepWordsAction } from "@/components/notebook/KeepWords"
import type { ColophonNotebook } from "@/components/notebook/use-colophon-notebook"
import { roomErrorMessage } from "@/components/rooms/errors"
import { Button } from "@/components/ui/button"

interface ColophonActionsProps {
  /** The game's words in the notebook (Undercover, Codenames, Kalimat); none for the Quiz. */
  notebook?: ColophonNotebook
  /** The room the game was played in; without one there is no way back to it. */
  roomId: string | null
  /** Only the host may start the next game (the server answers 403 to anyone else). */
  isHost?: boolean
  onBackToRoom: () => void
  onLeaveRoom: () => void
  /**
   * The game as its colophon names it (which game, whose majlis, its count, its start and
   * end): "Share" draws its card from that and the notebook's words. Leave it out for a
   * spectator, who gets no Share, as they get no Keep.
   */
  share?: ColophonShare
}

/**
 * The way on from every colophon, the same in the four games, in this order:
 *
 * 1. "Keep the words": the brass primary while some word of the game is not kept
 *    (then "Kept in your kunnash", a link).
 * 2. "Back to the room": secondary while there is something to keep, else the primary.
 * 3. "Play again", the host's only, secondary: the room's next game (rematch), then the
 *    lobby.
 * 4. "Share", secondary, for a player of the game (`share`): the colophon card of the
 *    evening (the arch, the game's Arabic name, the meta line, the game's words, which
 *    are public once it is over) through the share sheet, or the meta line copied where
 *    the browser cannot share an image (`ShareCardAction`). Drawn when pressed, never before.
 * 5. "Leave the room": a quiet ghost with the logout mark, the one label the player
 *    meets wherever they leave (`room.lobbyPage.leave`).
 */
export function ColophonActions({ notebook, roomId, isHost = false, onBackToRoom, onLeaveRoom, share }: ColophonActionsProps) {
  const { t, i18n } = useTranslation()
  const rematch = useRematchApiV1RoomsRoomIdRematchPost()
  const keepIsPrimary = !!notebook && notebook.available && !notebook.allKept

  const { mutateAsync: startRematch, isPending: rematchPending } = rematch
  const handlePlayAgain = useCallback(async () => {
    if (!roomId || rematchPending) return
    try {
      await startRematch({ room_id: roomId })
      onBackToRoom()
    } catch (err) {
      toast.error(roomErrorMessage(err, t("game.rematchFailed")))
    }
  }, [roomId, rematchPending, startRematch, onBackToRoom, t])

  return (
    <>
      {notebook ? <KeepWordsAction notebook={notebook} /> : null}
      {roomId ? (
        <Button variant={keepIsPrimary ? "secondary" : "primary"} onClick={onBackToRoom}>
          {t("game.backToRoom")}
        </Button>
      ) : null}
      {isHost && roomId ? (
        <Button variant="secondary" onClick={handlePlayAgain} loading={rematchPending} iconStart={<RotateCcw aria-hidden="true" />}>
          {t("game.playAgain")}
        </Button>
      ) : null}
      {share ? (
        <ShareCardAction
          copy="game.colophon.share"
          line={gameShareLine(share, t)}
          title={gameName(share.game, t)}
          fileName={gameCardFileName(share)}
          card={() => gameCardInput(share, notebook?.words, t, i18n.language ?? "en")}
          fieldId="colophon-share-line"
        />
      ) : null}
      <Button variant="ghost" onClick={onLeaveRoom} iconStart={<LogOut className="rtl-flip" aria-hidden="true" />}>
        {t("room.lobbyPage.leave")}
      </Button>
    </>
  )
}
