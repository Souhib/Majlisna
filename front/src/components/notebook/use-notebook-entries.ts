import { type InfiniteData, useInfiniteQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { getApiErrorMessage } from "@/api/client"
import { listNotebookEntriesApiV1NotebookGet, type NotebookPage } from "@/api/generated"
import { uniqueEntries } from "./entries"
import {
  deleteNotebookEntry,
  NOTEBOOK_GAME_WORDS_URL_KEY,
  NOTEBOOK_LIST_URL_KEY,
  NOTEBOOK_PAGE_SIZE,
  notebookListKey,
  retryUnlessClientError,
} from "./queries"

type Pages = InfiniteData<NotebookPage, string | null>

/**
 * The notebook, newest first, one page at a time over the generated client: each
 * page's `next_cursor` is the next page's `cursor`, null on the last page (keyset
 * pagination: a removal or a keep elsewhere never shifts a page boundary).
 */
export function useNotebookEntries(lang: string) {
  const query = useInfiniteQuery({
    queryKey: notebookListKey(lang),
    queryFn: ({ pageParam, signal }): Promise<NotebookPage> =>
      listNotebookEntriesApiV1NotebookGet({ lang, limit: NOTEBOOK_PAGE_SIZE, ...(pageParam ? { cursor: pageParam } : {}) }, { signal }),
    initialPageParam: null as string | null,
    getNextPageParam: (last: NotebookPage) => last.next_cursor ?? null,
    retry: retryUnlessClientError,
    staleTime: 30_000,
  })
  const entries = useMemo(() => uniqueEntries(query.data?.pages.flatMap((p) => p.entries) ?? []), [query.data])
  const total = query.data?.pages[0]?.total ?? 0
  return { ...query, entries, total }
}

/** How long a removed word can be brought back before it is really deleted. */
export const UNDO_WINDOW_MS = 6000

/** Take one entry out of the cached pages, and out of the count. */
export function withoutEntry(old: Pages | undefined, id: string): Pages | undefined {
  if (!old) return old
  const found = old.pages.some((p) => p.entries.some((e) => e.id === id))
  if (!found) return old
  return {
    ...old,
    pages: old.pages.map((p) => ({ ...p, entries: p.entries.filter((e) => e.id !== id), total: Math.max(0, p.total - 1) })),
  }
}

/**
 * Removing a word without a destructive surprise: the row turns into "Ṣabr was
 * removed. Undo" and the DELETE is only sent when the undo window closes (or when the
 * page is left, so nothing waits on a timer that will never fire). Undo cancels it:
 * nothing was sent, the word keeps its place.
 */
export function useEntryRemoval(lang: string) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [pending, setPending] = useState<ReadonlySet<string>>(() => new Set())
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  const setPendingId = useCallback((id: string, on: boolean) => {
    setPending((prev) => {
      const next = new Set(prev)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })
  }, [])

  const markStale = useCallback(() => {
    // the page already shows the truth; every other copy (other languages, the colophons) is stale
    void queryClient.invalidateQueries({ queryKey: NOTEBOOK_LIST_URL_KEY, refetchType: "none" })
    void queryClient.invalidateQueries({ queryKey: NOTEBOOK_GAME_WORDS_URL_KEY, refetchType: "none" })
  }, [queryClient])

  const commit = useCallback(
    async (id: string) => {
      timers.current.delete(id)
      const result = await deleteNotebookEntry(id)
      if (!result.ok) {
        toast.error(getApiErrorMessage(result.error, t("notebook.removeFailed")))
        setPendingId(id, false)
        return
      }
      queryClient.setQueryData<Pages>(notebookListKey(lang), (old) => withoutEntry(old, id))
      setPendingId(id, false)
      markStale()
    },
    [lang, markStale, queryClient, setPendingId, t],
  )

  const remove = useCallback(
    (id: string) => {
      if (timers.current.has(id)) return
      setPendingId(id, true)
      timers.current.set(
        id,
        setTimeout(() => void commit(id), UNDO_WINDOW_MS),
      )
    },
    [commit, setPendingId],
  )

  const undo = useCallback(
    (id: string) => {
      const timer = timers.current.get(id)
      if (timer === undefined) return
      clearTimeout(timer)
      timers.current.delete(id)
      setPendingId(id, false)
    },
    [setPendingId],
  )

  // Leaving the page closes every open undo window: send those deletions now.
  useEffect(() => {
    const open = timers.current
    return () => {
      const ids = [...open.keys()]
      for (const timer of open.values()) clearTimeout(timer)
      open.clear()
      if (ids.length === 0) return
      void Promise.all(ids.map(deleteNotebookEntry)).then(() => {
        void queryClient.invalidateQueries({ queryKey: NOTEBOOK_LIST_URL_KEY })
        void queryClient.invalidateQueries({ queryKey: NOTEBOOK_GAME_WORDS_URL_KEY, refetchType: "none" })
      })
    }
  }, [queryClient])

  return { pending, remove, undo }
}
