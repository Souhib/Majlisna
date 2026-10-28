import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  pauseCodenamesGameApiV1CodenamesGamesGameIdPausePost,
  pauseMcqquizGameApiV1McqquizGamesGameIdPausePost,
  pauseUndercoverGameApiV1UndercoverGamesGameIdPausePost,
  pauseWordquizGameApiV1WordquizGamesGameIdPausePost,
  resumeCodenamesGameApiV1CodenamesGamesGameIdResumePost,
  resumeMcqquizGameApiV1McqquizGamesGameIdResumePost,
  resumeUndercoverGameApiV1UndercoverGamesGameIdResumePost,
  resumeWordquizGameApiV1WordquizGamesGameIdResumePost,
} from "@/api/generated"
import { queryKeys } from "@/api/queryKeys"
import { roomErrorMessage } from "@/components/rooms/errors"
import type { PauseFields, PauseGame } from "./pause-utils"

const PAUSE: Record<PauseGame, (params: { game_id: string }) => Promise<unknown>> = {
  undercover: pauseUndercoverGameApiV1UndercoverGamesGameIdPausePost,
  codenames: pauseCodenamesGameApiV1CodenamesGamesGameIdPausePost,
  wordquiz: pauseWordquizGameApiV1WordquizGamesGameIdPausePost,
  mcqquiz: pauseMcqquizGameApiV1McqquizGamesGameIdPausePost,
}

const RESUME: Record<PauseGame, (params: { game_id: string }) => Promise<unknown>> = {
  undercover: resumeUndercoverGameApiV1UndercoverGamesGameIdResumePost,
  codenames: resumeCodenamesGameApiV1CodenamesGamesGameIdResumePost,
  wordquiz: resumeWordquizGameApiV1WordquizGamesGameIdResumePost,
  mcqquiz: resumeMcqquizGameApiV1McqquizGamesGameIdResumePost,
}

/**
 * The prayer pause of one game (وقفة الصلاة): what the server says about it (`paused`,
 * `can_pause`, `can_resume`, all per caller) and the two requests. Success needs no toast:
 * the veil appearing or lifting is the answer, for the host as for everyone (the route
 * notifies the table). A refusal is the host's own action, so it is told, translated
 * through the server's `error_key`.
 */
export function usePrayerPause(game: PauseGame, gameId: string, state: PauseFields | null | undefined) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const refresh = useCallback(() => {
    const queryKey =
      game === "undercover"
        ? queryKeys.game.undercover(gameId)
        : game === "codenames"
          ? queryKeys.game.codenames(gameId)
          : game === "wordquiz"
            ? queryKeys.game.wordquiz(gameId)
            : queryKeys.game.mcqquiz(gameId)
    return queryClient.invalidateQueries({ queryKey })
  }, [game, gameId, queryClient])

  const pauseMutation = useMutation({
    mutationFn: () => PAUSE[game]({ game_id: gameId }),
    onError: (err) => toast.error(roomErrorMessage(err, t("pause.errors.pause"))),
    onSettled: () => refresh(),
  })
  const resumeMutation = useMutation({
    mutationFn: () => RESUME[game]({ game_id: gameId }),
    onError: (err) => toast.error(roomErrorMessage(err, t("pause.errors.resume"))),
    onSettled: () => refresh(),
  })

  const { mutate: mutatePause, isPending: isPausing } = pauseMutation
  const { mutate: mutateResume, isPending: isResuming } = resumeMutation
  const pause = useCallback(() => {
    if (!isPausing) mutatePause()
  }, [isPausing, mutatePause])
  const resume = useCallback(() => {
    if (!isResuming) mutateResume()
  }, [isResuming, mutateResume])

  return {
    paused: state?.paused ?? null,
    canPause: !!state?.can_pause && !state?.paused,
    canResume: !!state?.can_resume && !!state?.paused,
    pause,
    resume,
    isPausing,
    isResuming,
    refresh,
  }
}
