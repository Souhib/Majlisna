import { useLocation } from "@tanstack/react-router"
import type { NotebookGameType } from "@/api/generated"

/**
 * Which finished game a colophon belongs to, read from the game page's URL
 * (`/game/undercover/<id>`, `/game/codenames/<id>`, `/game/wordquiz/<id>`). The
 * game-over components are rendered by the game routes without the game id, and the
 * MCQ page (`/game/mcqquiz/<id>`) has no words to keep, so it maps to nothing.
 */
const PATH_GAME: Record<string, NotebookGameType> = {
  undercover: "undercover",
  codenames: "codenames",
  wordquiz: "word_quiz",
}

export interface NotebookGameRef {
  gameType: NotebookGameType
  gameId: string
}

export function notebookGameFromPath(pathname: string): NotebookGameRef | null {
  const match = /^\/game\/([a-z]+)\/([^/?#]+)\/?$/.exec(pathname)
  if (!match) return null
  const gameType = PATH_GAME[match[1]]
  if (!gameType) return null
  return { gameType, gameId: decodeURIComponent(match[2]) }
}

/** The id of the game on screen when it is a game of `gameType`, otherwise null. */
export function useRouteNotebookGameId(gameType: NotebookGameType): string | null {
  const pathname = useLocation({ select: (location) => location.pathname })
  const ref = notebookGameFromPath(pathname)
  return ref?.gameType === gameType ? ref.gameId : null
}
