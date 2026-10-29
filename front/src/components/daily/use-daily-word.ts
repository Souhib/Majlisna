import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage, type ResponseErrorConfig } from "@/api/client"
import {
  type DailyWordGuessResponse,
  type DailyWordState,
  useGetDailyWordApiV1DailyWordGet,
  useGiveUpDailyWordApiV1DailyWordGiveUpPost,
  useGuessDailyWordApiV1DailyWordGuessPost,
  useKeepDailyWordApiV1DailyWordKeepPost,
  useRevealDailyWordHintApiV1DailyWordHintPost,
} from "@/api/generated"
import { invalidateNotebook, retryUnlessClientError } from "@/components/notebook/queries"
import { serverNow } from "@/lib/server-clock"
import { useAuth } from "@/providers/AuthProvider"
import { DAILY_WORD_URL_KEY, dailyWordKey, type DailyWordKey, msUntil } from "./daily"

/** A beat after the server's midnight, so the next read lands on the new day. */
const NEXT_DAY_SLACK_MS = 1500
/** setTimeout's largest delay: anything longer fires at once (a device clock far behind the server's). */
const MAX_TIMEOUT_MS = 2 ** 31 - 1

/** The 409s that mean the state on screen is out of date: read it again. */
const STALE_STATE_ERRORS = new Set(["errors.api.dailyWordNotToday", "errors.api.dailyWordAlreadyFinished", "errors.api.dailyWordNoMoreHints"])

function errorKey(error: unknown): string | undefined {
  return (error as ResponseErrorConfig<{ error_key?: string }> | null)?.response?.data?.error_key
}

/**
 * Today's word as this viewer sees it (`GET /daily-word?lang=`), for the page and the
 * home card. Public, but read only once the AuthProvider has settled: a request sent
 * with a token the provider is still refreshing answers 401, and the client answers a
 * 401 by sending the visitor to the login page. The viewer is part of the key
 * (`dailyWordKey`), and the read is taken again a beat after the next Makkah midnight.
 */
export function useDailyWordQuery() {
  const { i18n } = useTranslation()
  const lang = i18n.language
  const { user, isAuthenticated, isLoading: authLoading } = useAuth()
  const queryClient = useQueryClient()
  const viewer = isAuthenticated ? (user?.id ?? "signed-in") : null
  const queryKey = useMemo(() => dailyWordKey(lang, viewer), [lang, viewer])

  const query = useGetDailyWordApiV1DailyWordGet<DailyWordState, DailyWordState, DailyWordKey>(
    { lang },
    { query: { queryKey, enabled: !authLoading, staleTime: 60_000, refetchOnWindowFocus: true, retry: retryUnlessClientError } },
  )

  const nextDayAt = query.data?.next_day_at
  useEffect(() => {
    if (!nextDayAt) return
    const delay = Math.min(msUntil(nextDayAt, serverNow()) + NEXT_DAY_SLACK_MS, MAX_TIMEOUT_MS)
    const id = setTimeout(() => void queryClient.invalidateQueries({ queryKey: DAILY_WORD_URL_KEY }), delay)
    return () => clearTimeout(id)
  }, [nextDayAt, queryClient])

  return { query, queryKey, lang, signedIn: viewer !== null, authLoading }
}

/**
 * The page's moves on today's word: reveal a hint, guess, give up, keep it in the
 * Kunnash. Each answers the new state, written straight into the read's cache (the
 * home card shares it). Every move names the day the page shows (`day`): one left open
 * past midnight in Makkah is refused (409 `dailyWordNotToday`) and the new day is read.
 * A failure is the player's own action, so it is a toast; the state is re-read when
 * the server says the page is behind.
 */
export function useDailyWord() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const read = useDailyWordQuery()
  const state = read.query.data
  const { queryKey, lang } = read

  const hintMutation = useRevealDailyWordHintApiV1DailyWordHintPost()
  const guessMutation = useGuessDailyWordApiV1DailyWordGuessPost()
  const giveUpMutation = useGiveUpDailyWordApiV1DailyWordGiveUpPost()
  const keepMutation = useKeepDailyWordApiV1DailyWordKeepPost()

  const day = state?.day
  const params = useMemo(() => ({ lang, day }), [lang, day])

  const write = useCallback((next: DailyWordState) => queryClient.setQueryData<DailyWordState>(queryKey, next), [queryClient, queryKey])

  const fail = useCallback(
    (error: unknown) => {
      const key = errorKey(error)
      if (key && STALE_STATE_ERRORS.has(key)) void queryClient.invalidateQueries({ queryKey: DAILY_WORD_URL_KEY })
      const message = getApiErrorMessage(error, t("daily.play.failed"))
      if (key === "errors.api.dailyWordNotToday") toast(message)
      else toast.error(message)
    },
    [queryClient, t],
  )

  const revealHint = useCallback(async (): Promise<DailyWordState | null> => {
    try {
      const next = await hintMutation.mutateAsync({ params })
      write(next)
      return next
    } catch (error) {
      fail(error)
      return null
    }
  }, [hintMutation, params, write, fail])

  const guess = useCallback(
    async (answer: string): Promise<DailyWordGuessResponse | null> => {
      try {
        const result = await guessMutation.mutateAsync({ data: { answer }, params })
        write(result.state)
        return result
      } catch (error) {
        fail(error)
        return null
      }
    },
    [guessMutation, params, write, fail],
  )

  const giveUp = useCallback(async (): Promise<DailyWordState | null> => {
    try {
      const next = await giveUpMutation.mutateAsync({ params })
      write(next)
      return next
    } catch (error) {
      fail(error)
      return null
    }
  }, [giveUpMutation, params, write, fail])

  const keep = useCallback(async () => {
    try {
      const result = await keepMutation.mutateAsync({ params })
      queryClient.setQueryData<DailyWordState>(queryKey, (prev) =>
        prev?.answer ? { ...prev, answer: { ...prev.answer, kept: true, entry_id: result.entries[0]?.id ?? prev.answer.entry_id } } : prev,
      )
      invalidateNotebook(queryClient, { gameWords: false })
    } catch (error) {
      fail(error)
    }
  }, [keepMutation, params, queryClient, queryKey, fail])

  return {
    ...read,
    state,
    revealHint,
    guess,
    giveUp,
    keep,
    revealing: hintMutation.isPending,
    givingUp: giveUpMutation.isPending,
    keeping: keepMutation.isPending,
  }
}
