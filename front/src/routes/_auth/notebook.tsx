import { createFileRoute, Link } from "@tanstack/react-router"
import { useEffect, useId, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { getApiErrorMessage } from "@/api/client"
import { formatKeptDate, groupEntries, NOTEBOOK_TITLE_ID } from "@/components/notebook/entries"
import { NotebookEntryRow } from "@/components/notebook/NotebookEntryRow"
import { useEntryRemoval, useNotebookEntries } from "@/components/notebook/use-notebook-entries"
import { gameName } from "@/components/stats/format"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Skeleton } from "@/components/ui/skeleton"

export const Route = createFileRoute("/_auth/notebook")({
  component: NotebookPage,
})

/** The notebook's name in Arabic, shown under the Latin title in English and French. */
const KUNNASH = "كُنّاش"

/**
 * The Kunnash (كُنّاش): the words a player kept at the end of their games, newest
 * first, read like a small dictionary. Runs of words kept from one game share a
 * heading (the game, the day); each word is its Arabic headword in Amiri, the word as
 * the game showed it, and its meaning. Removing one opens a short undo window.
 *
 * Pages load as the reader nears the end (and on "Show more words", for keyboards and
 * for when the observer is not there), over the generated client with `next_cursor`.
 * In the Arabic UI the Arabic leads: the title is الكُنّاش, no transliteration.
 */
function NotebookPage() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const arabicUi = lang.startsWith("ar")
  const list = useNotebookEntries(lang)
  const { pending, remove, undo } = useEntryRemoval(lang)
  const groups = useMemo(() => groupEntries(list.entries), [list.entries])
  const idPrefix = useId()
  const [announcement, setAnnouncement] = useState("")

  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = list
  const sentinelRef = useRef<HTMLDivElement>(null)

  // Load the next page as the reader nears the end. Not after a failed page: the
  // button under the list is then the way to try again (no silent request loop).
  useEffect(() => {
    const node = sentinelRef.current
    if (!node || !hasNextPage || isFetchingNextPage || isFetchNextPageError || typeof IntersectionObserver === "undefined") return
    const observer = new IntersectionObserver(
      (records) => {
        if (records.some((r) => r.isIntersecting)) void fetchNextPage()
      },
      { rootMargin: "0px 0px 480px 0px" },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage])

  const labelOf = (id: string) => {
    const entry = list.entries.find((e) => e.id === id)
    if (!entry) return ""
    const arabic = entry.word_ar_vocalized?.trim() || entry.word_ar?.trim()
    return arabicUi && arabic ? arabic : entry.word_display || entry.word
  }

  const handleRemove = (id: string) => {
    remove(id)
    setAnnouncement(t("notebook.removedAnnounce", { word: labelOf(id) }))
  }
  const handleUndo = (id: string) => {
    undo(id)
    setAnnouncement(t("notebook.restored", { word: labelOf(id) }))
  }

  const isEmpty = list.isSuccess && list.entries.length === 0 && !hasNextPage

  return (
    <div className="page-wrap py-[clamp(32px,5vw,72px)]">
      <div className="mx-auto max-w-[44rem]">
        <header className="mb-[clamp(28px,4vw,48px)]">
          <h1
            id={NOTEBOOK_TITLE_ID}
            tabIndex={-1}
            className="font-display text-[clamp(34px,3.2vw,50px)] leading-[1.06] text-balance outline-none rtl:leading-[1.35]"
          >
            {arabicUi ? (
              t("notebook.title")
            ) : (
              <>
                {t("notebook.title")}
                <span lang="ar" dir="rtl" className="type-arabic-name mt-2 block w-fit pt-[0.2em] text-[clamp(32px,3vw,42px)] leading-[1.4]">
                  {KUNNASH}
                </span>
              </>
            )}
          </h1>
          <p className="type-lede mt-3 max-w-[54ch]">{t("notebook.lede")}</p>
          {list.total > 0 ? <p className="num mt-3 type-meta">{t("notebook.count", { count: list.total })}</p> : null}
        </header>

        <p className="sr-only" role="status" aria-live="polite">
          {announcement}
        </p>

        {list.isPending ? (
          <EntriesSkeleton label={t("notebook.loading")} />
        ) : list.isError && list.entries.length === 0 ? (
          <div className="grid justify-items-start gap-4">
            <Alert tone="error">{getApiErrorMessage(list.error, t("notebook.loadFailed"))}</Alert>
            <Button variant="secondary" onClick={() => void list.refetch()} loading={list.isRefetching}>
              {t("notebook.retry")}
            </Button>
          </div>
        ) : isEmpty ? (
          <EmptyState
            titleAs="h2"
            title={t("notebook.emptyTitle")}
            description={t("notebook.emptyBody")}
            className="border-t border-line py-14"
            action={
              <>
                <Button asChild>
                  <Link to="/rooms/create">{t("notebook.openRoom")}</Link>
                </Button>
                <Button asChild variant="secondary">
                  <Link to="/rooms">{t("notebook.joinRoom")}</Link>
                </Button>
              </>
            }
          />
        ) : (
          <>
            <div className="grid gap-[clamp(32px,4.5vw,52px)]">
              {groups.map((group, index) => {
                const headingId = `${idPrefix}-${index}`
                return (
                  <section key={group.key} aria-labelledby={headingId}>
                    <h2 id={headingId} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-b border-line-brass pb-2.5">
                      <span aria-hidden="true" className="loz -translate-y-px bg-brass [--loz:7px]" />
                      <span className="type-panel">{gameName(group.gameType, t)}</span>
                      <span className="type-meta">
                        <time dateTime={group.keptAt}>{t("notebook.keptOn", { count: group.entries.length, date: formatKeptDate(group.keptAt, lang) })}</time>
                      </span>
                    </h2>
                    <ul>
                      {group.entries.map((entry) => (
                        <NotebookEntryRow
                          key={entry.id}
                          entry={entry}
                          arabicUi={arabicUi}
                          removed={pending.has(entry.id)}
                          onRemove={handleRemove}
                          onUndo={handleUndo}
                        />
                      ))}
                    </ul>
                  </section>
                )
              })}
            </div>

            {hasNextPage ? (
              <div ref={sentinelRef} className="mt-10 grid justify-items-center gap-3">
                {isFetchNextPageError ? <Alert tone="error">{getApiErrorMessage(list.error, t("notebook.loadMoreFailed"))}</Alert> : null}
                <Button variant="secondary" loading={isFetchingNextPage} onClick={() => void fetchNextPage()}>
                  {t("notebook.more")}
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}

/** Loading: two runs of bare warp in the shape of the entries. */
function EntriesSkeleton({ label }: { label: string }) {
  return (
    <div aria-busy="true">
      <p className="sr-only" role="status">
        {label}
      </p>
      <div className="grid gap-[clamp(32px,4.5vw,52px)]" aria-hidden="true">
        {[0, 1].map((group) => (
          <div key={group}>
            <div className="flex items-center gap-3 border-b border-line-brass pb-3">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-3 w-24" />
            </div>
            {[0, 1, 2].map((row) => (
              <div key={row} className="flex items-start gap-4 border-b border-line py-5">
                <div className="grid flex-1 gap-2.5">
                  <div className="flex items-end gap-4">
                    <Skeleton className="h-11 w-24" />
                    <Skeleton className="h-4 w-20" />
                  </div>
                  <Skeleton className="h-3.5 w-11/12" />
                  <Skeleton className="h-3.5 w-3/5" />
                </div>
                <Skeleton className="size-9 shrink-0" />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
