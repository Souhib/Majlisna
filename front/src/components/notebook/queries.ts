import type { QueryClient } from "@tanstack/react-query"
import type { ResponseErrorConfig } from "@/api/client"
import { deleteNotebookEntryApiV1NotebookEntriesEntryIdDelete, listNotebookEntriesApiV1NotebookGetQueryKey } from "@/api/generated"

/**
 * Query keys of the Kunnash. The generated keys start with `{ url }`, so a key holding
 * only that object matches every query of the endpoint (any `lang`, any cursor):
 * TanStack Query matches query-key prefixes, and objects by the keys they name.
 */
export const NOTEBOOK_LIST_URL_KEY = [{ url: "/api/v1/notebook" }] as const
export const NOTEBOOK_GAME_WORDS_URL_KEY = [{ url: "/api/v1/notebook/games/:game_id" }] as const

/** Entries per page of the notebook listing (the server allows up to 100). */
export const NOTEBOOK_PAGE_SIZE = 30

/**
 * The infinite listing's key: the generated key for `{ lang, limit }`, tagged so it
 * never shares a cache entry with the plain (single-page) query of the same URL.
 */
export function notebookListKey(lang: string) {
  return [...listNotebookEntriesApiV1NotebookGetQueryKey({ lang, limit: NOTEBOOK_PAGE_SIZE }), "infinite"] as const
}

/** After a keep or a removal: the listing and every colophon's kept state are stale. */
export function invalidateNotebook(queryClient: QueryClient, { gameWords = true, list = true } = {}) {
  if (list) void queryClient.invalidateQueries({ queryKey: NOTEBOOK_LIST_URL_KEY })
  if (gameWords) void queryClient.invalidateQueries({ queryKey: NOTEBOOK_GAME_WORDS_URL_KEY })
}

/** The HTTP status of a failed generated-client call, when there is one. */
export function errorStatus(error: unknown): number | undefined {
  return (error as ResponseErrorConfig | null)?.response?.status
}

/**
 * The app's one retry for a read (QueryProvider's default), skipped on a 4xx: a 403
 * (not a player, game still running) or a 400 (MCQ has no words) will not change.
 */
export function retryUnlessClientError(failureCount: number, error: unknown) {
  const status = errorStatus(error)
  if (status !== undefined && status >= 400 && status < 500) return false
  return failureCount < 1
}

/**
 * `DELETE /notebook/entries/{id}`, answered by its outcome: `{ ok: true }` when the entry
 * is gone (204, or 404: someone else's or already deleted, which is the same answer to
 * "take it out"), else the error.
 */
export async function deleteNotebookEntry(entryId: string): Promise<{ ok: true } | { ok: false; error: unknown }> {
  try {
    await deleteNotebookEntryApiV1NotebookEntriesEntryIdDelete({ entry_id: entryId })
    return { ok: true }
  } catch (error) {
    if (errorStatus(error) === 404) return { ok: true }
    return { ok: false, error }
  }
}
