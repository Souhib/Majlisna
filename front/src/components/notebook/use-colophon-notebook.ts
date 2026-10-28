import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import {
  getNotebookGameWordsApiV1NotebookGamesGameIdGetQueryKey,
  keepNotebookGameWordsApiV1NotebookGamesGameIdKeepPost,
  keepNotebookWordApiV1NotebookEntriesPost,
  type NotebookGameWord,
  type NotebookGameWords,
  type NotebookKeepResponse,
  useGetNotebookGameWordsApiV1NotebookGamesGameIdGet,
} from "@/api/generated"
import { deleteNotebookEntry, invalidateNotebook, retryUnlessClientError } from "./queries"

/** The notebook's state for one finished game, as the game-over colophon uses it. */
export interface ColophonNotebook {
  /** Every word the game dealt, with whether it is kept. Undefined until loaded. */
  words: NotebookGameWord[] | undefined
  isLoading: boolean
  /** The words loaded for a player of this game: keeping is offered. */
  available: boolean
  /** Every word of the game is in the notebook. */
  allKept: boolean
  keepAll: () => Promise<void>
  keepingAll: boolean
  /** The notebook's row for a word as the game names it (the Latin key). */
  find: (word: string | null | undefined) => NotebookGameWord | undefined
  /** Keep one word, or take it out again (by its entry id). */
  toggle: (word: NotebookGameWord) => Promise<void>
  isBusy: (word: string) => boolean
}

/** Words are matched as the game stored them, forgiving case and stray spaces. */
export function wordKey(word: string): string {
  return word.trim().toLocaleLowerCase()
}

/**
 * Keep the words of a finished game from its colophon: one read
 * (`GET /notebook/games/{id}`: the words with `kept` + `entry_id`), keep them all,
 * keep or un-keep one. Every change is applied to the read's cache at once and undone
 * if the server refuses (a 429 or a 403 is said in the player's language). Off for a
 * spectator (`enabled: false`); the server refuses them anyway (403, not a player).
 */
export function useColophonNotebook(gameId: string | null | undefined, { enabled = true }: { enabled?: boolean } = {}): ColophonNotebook {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState<ReadonlySet<string>>(() => new Set())
  const [keepingAll, setKeepingAll] = useState(false)

  const params = useMemo(() => ({ lang }), [lang])
  const queryKey = useMemo(() => getNotebookGameWordsApiV1NotebookGamesGameIdGetQueryKey({ game_id: gameId ?? "" }, params), [gameId, params])

  const query = useGetNotebookGameWordsApiV1NotebookGamesGameIdGet({ game_id: gameId ?? "" }, params, {
    query: { enabled: enabled && !!gameId, retry: retryUnlessClientError, staleTime: 30_000 },
  })
  const words = enabled && gameId ? query.data?.words : undefined

  const patch = useCallback(
    (fn: (word: NotebookGameWord) => NotebookGameWord) =>
      queryClient.setQueryData<NotebookGameWords>(queryKey, (old) => (old ? { ...old, words: old.words.map(fn) } : old)),
    [queryClient, queryKey],
  )

  const setWordBusy = useCallback((key: string, on: boolean) => {
    setBusy((prev) => {
      const next = new Set(prev)
      if (on) next.add(key)
      else next.delete(key)
      return next
    })
  }, [])

  const keepAll = useCallback(async () => {
    if (!gameId || keepingAll) return
    setKeepingAll(true)
    try {
      const res: NotebookKeepResponse = await keepNotebookGameWordsApiV1NotebookGamesGameIdKeepPost({ game_id: gameId }, params)
      const ids = new Map(res.entries.map((e) => [wordKey(e.word), e.id]))
      // said in place, not by a toast: the button becomes "Kept in your kunnash" and
      // focus follows it (KeepWordsAction)
      patch((w) => ({ ...w, kept: true, entry_id: ids.get(wordKey(w.word)) ?? w.entry_id }))
      invalidateNotebook(queryClient, { gameWords: false })
    } catch (err) {
      toast.error(getApiErrorMessage(err, t("notebook.colophon.keepFailed")))
    } finally {
      setKeepingAll(false)
    }
  }, [gameId, keepingAll, params, patch, queryClient, t])

  const toggle = useCallback(
    async (word: NotebookGameWord) => {
      const key = wordKey(word.word)
      if (!gameId || busy.has(key)) return
      const same = (w: NotebookGameWord) => wordKey(w.word) === key
      setWordBusy(key, true)
      try {
        if (word.kept) {
          if (!word.entry_id) return
          patch((w) => (same(w) ? { ...w, kept: false } : w))
          const result = await deleteNotebookEntry(word.entry_id)
          if (!result.ok) {
            patch((w) => (same(w) ? { ...w, kept: true } : w))
            toast.error(getApiErrorMessage(result.error, t("notebook.colophon.unkeepFailed")))
            return
          }
          patch((w) => (same(w) ? { ...w, kept: false, entry_id: null } : w))
        } else {
          patch((w) => (same(w) ? { ...w, kept: true } : w))
          try {
            const res: NotebookKeepResponse = await keepNotebookWordApiV1NotebookEntriesPost({ game_id: gameId, word: word.word }, params)
            const entry = res.entries.find((e) => wordKey(e.word) === key) ?? res.entries[0]
            patch((w) => (same(w) ? { ...w, kept: true, entry_id: entry?.id ?? w.entry_id } : w))
          } catch (err) {
            patch((w) => (same(w) ? { ...w, kept: false } : w))
            toast.error(getApiErrorMessage(err, t("notebook.colophon.keepFailed")))
            return
          }
        }
        invalidateNotebook(queryClient, { gameWords: false })
      } finally {
        setWordBusy(key, false)
      }
    },
    [busy, gameId, params, patch, queryClient, setWordBusy, t],
  )

  const byKey = useMemo(() => new Map((words ?? []).map((w) => [wordKey(w.word), w])), [words])
  const find = useCallback((word: string | null | undefined) => (word ? byKey.get(wordKey(word)) : undefined), [byKey])
  const isBusy = useCallback((word: string) => busy.has(wordKey(word)), [busy])

  const available = !!words && words.length > 0
  return {
    words,
    isLoading: enabled && !!gameId && query.isLoading,
    available,
    allKept: !!words && words.length > 0 && words.every((w) => w.kept),
    keepAll,
    keepingAll,
    find,
    toggle,
    isBusy,
  }
}
