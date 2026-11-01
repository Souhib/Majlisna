import { createFileRoute } from "@tanstack/react-router"
import { useCallback, useRef } from "react"
import { Trans, useTranslation } from "react-i18next"
import { wordQuizCategoryEnum } from "@/api/generated"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { useAchievementSeals } from "@/components/games/shared/achievement-seals"
import { ColophonMeta } from "@/components/games/shared/ColophonMeta"
import { isGameGoneError } from "@/components/games/shared/game-errors"
import { GameErrorFallback } from "@/components/games/shared/GameErrorFallback"
import { PhaseTimer } from "@/components/games/shared/PhaseTimer"
import { PlayerScoreboard } from "@/components/games/shared/PlayerScoreboard"
import { AdhanSuggestion, PauseControl, PauseLayer, useAdhanSuggestion, usePrayerPause } from "@/components/games/shared/prayer-pause"
import { QuizGameOver } from "@/components/games/shared/QuizGameOver"
import { QuizFrame, QuizGoneNotice, QuizHeader, QuizLeaveButton, QuizLoading } from "@/components/games/shared/QuizLayout"
import { useHeldForPhase } from "@/components/games/shared/quiz-utils"
import { AnswerInput } from "@/components/games/wordquiz/AnswerInput"
import { HintDisplay } from "@/components/games/wordquiz/HintDisplay"
import { LastRoundCard } from "@/components/games/wordquiz/LastRoundCard"
import { RoundResults } from "@/components/games/wordquiz/RoundResults"
import { Panel } from "@/components/ui/panel"
import { type PhaseFocusTargets, usePhaseFocus } from "@/hooks/use-phase-focus"
import { kalimatWorth, useWordQuizGame } from "@/hooks/use-wordquiz-game"
import { useViewTransitionValue } from "@/lib/view-transition"

/** Each theme's key in `game.quiz.kalimat.category` (an unknown one is not shown). */
const CATEGORIES = new Set<string>(Object.values(wordQuizCategoryEnum))

/** The answer field's prompt for a theme: a person or a place is asked for as such, any other word as a word. */
function promptKey(category: string | null | undefined): string {
  if (category === "prophets" || category === "companions") return "game.quiz.kalimat.askWho"
  if (category === "places") return "game.quiz.kalimat.askWhere"
  return "game.quiz.kalimat.askWhat"
}

const DIFFICULTIES = new Set(["easy", "medium", "hard"])

/**
 * Where focus goes when the phase on screen changes (F2, `usePhaseFocus`). Kalimat's
 * round has no title of its own, so: the hint in play at a new round (Tab then reaches
 * the field), what you found once the field is gone, "The answer was" at the round's
 * end (the word follows it), the colophon's title at the end of the game.
 */
const FOCUS_TARGETS: PhaseFocusTargets = {
  playing: ".hint-ladder [aria-current='step']",
  found: ".hint-ladder + [role='status']",
  results: "#kalimat-answer",
  game_over: "[data-colophon-title]",
}

export const Route = createFileRoute("/_auth/game/wordquiz/$gameId")({
  component: () => (
    <ErrorBoundary fallback={<GameErrorFallback />}>
      <WordQuizGamePage />
    </ErrorBoundary>
  ),
})

/**
 * Kalimat (sketch C bottom-left, D Kalimat phone): guess the word from a ladder of six
 * hints, released one by one; the sooner you find it, the more it is worth. Phases
 * swap through a view transition (no blank exit before the next phase); the end of the
 * game is the colophon, where achievements are pressed as seals. The game's logic is
 * `useWordQuizGame`; this page draws it.
 */
function WordQuizGamePage() {
  const { gameId } = Route.useParams()
  const { t } = useTranslation()
  const {
    user,
    state,
    isLoading,
    queryError,
    socketConnected,
    cancelMessage,
    roomIdRef,
    isPaused,
    hintClock,
    lastRound,
    isAdvancing,
    handleSubmitAnswer,
    handleTimerExpired,
    handleNextRound,
    handleLeaveRoom,
    handleBackToRoom,
  } = useWordQuizGame(gameId)

  // The phase on screen follows the server's through a view transition (180 ms crossfade).
  const phase = useViewTransitionValue(state?.round_phase ?? null)
  // ...and is drawn from the state it belongs to, so the outgoing frame stays true.
  const held = useHeldForPhase(state, phase)
  // Focus follows the phase on screen: finding the word is a phase of its own (the
  // field goes), and the page's first state is not a change.
  const gameRef = useRef<HTMLDivElement>(null)
  const focusKey = phase === "playing" && (held ?? state)?.my_answered ? "found" : phase
  usePhaseFocus(state ? focusKey : null, gameRef, { targets: FOCUS_TARGETS })

  // The prayer pause: the host's control, the veil over the whole game, the adhan strip.
  const prayerPause = usePrayerPause("wordquiz", gameId, state)
  const adhan = useAdhanSuggestion({ gameId, canPause: prayerPause.canPause, paused: isPaused })
  const { answer: answerAdhan } = adhan
  const { pause: pauseGame } = prayerPause
  const pauseFromStrip = useCallback(() => {
    answerAdhan()
    pauseGame()
  }, [answerAdhan, pauseGame])

  const seals = useAchievementSeals(state?.newly_unlocked_achievements, state?.leaderboard, user?.id)

  const gameName = t("games.wordQuiz.name")

  if (cancelMessage) return <QuizGoneNotice message={cancelMessage} />
  if (!state) {
    // a game that is gone gets its notice (set by the hook), not a crash screen
    if (queryError && !isLoading && !isGameGoneError(queryError)) return <GameErrorFallback error={queryError} />
    return <QuizLoading title={gameName} />
  }
  const view = held ?? state

  // Never claim to reveal a hint we haven't been given: the local clock can run a
  // beat ahead of the fetch that brings the next one in.
  const localRevealed = Math.min(hintClock.revealed, view.hints.length)
  const effectiveHintsRevealed = view.round_phase === "playing" ? localRevealed : view.hints_revealed
  const maxHints = view.max_hints ?? 6
  // what a right answer pays now: the rung on screen, less the rungs this player's misses cost
  const worth = kalimatWorth(maxHints, effectiveHintsRevealed, view.my_rungs_lost ?? 0)
  // nothing is priced for a player who can no longer answer: found it, or out of tries (F5)
  const canStillEarn = !view.my_answered && view.my_attempts_left !== 0
  const answeredCount = view.players.filter((p) => p.current_round_answered).length
  const answeredNote = t("game.quiz.answeredCount", { answered: answeredCount, total: view.players.length })
  // The header names the word's theme ("Round 3 of 7 · a prophet"); the difficulty stands
  // in only for a state that carries no theme.
  const category = view.category && CATEGORIES.has(view.category) ? view.category : null
  const difficulty = !category && view.difficulty && DIFFICULTIES.has(view.difficulty) ? view.difficulty : null
  const prompt = promptKey(category)
  const showLastRound = lastRound != null && lastRound.round === view.current_round - 1
  const pauseControl =
    prayerPause.canPause || prayerPause.canResume ? (
      <PauseControl
        canPause={prayerPause.canPause}
        canResume={prayerPause.canResume}
        paused={isPaused}
        onPause={prayerPause.pause}
        onResume={prayerPause.resume}
        pending={prayerPause.isPausing || prayerPause.isResuming}
      />
    ) : null

  const sub = (
    <>
      {t("game.quiz.kalimat.roundOf", { current: view.current_round, total: view.total_rounds })}
      {category ? ` · ${t(`game.quiz.kalimat.category.${category}`)}` : null}
      {difficulty ? ` · ${t(`room.difficulty${difficulty.charAt(0).toUpperCase()}${difficulty.slice(1)}`)}` : null}
    </>
  )

  if (phase === "game_over") {
    return (
      <>
        <ConnectionStatus connected={socketConnected} />
        <QuizFrame>
          {/* the game region at its end: where focus lands on the colophon's title */}
          <div ref={gameRef}>
            <h1 className="sr-only">{gameName}</h1>
            <QuizGameOver
              winner={view.winner}
              leaderboard={view.leaderboard}
              onBackToRoom={handleBackToRoom}
              onLeaveRoom={handleLeaveRoom}
              winnerI18nKey="game.wordQuiz.winner"
              finalScoresI18nKey="game.wordQuiz.finalScores"
              currentUserId={user?.id}
              roomId={roomIdRef.current}
              isHost={view.is_host}
              seals={seals}
              meta={
                <ColophonMeta
                  game={gameName}
                  host={view.host_username}
                  count={t("game.quiz.roundsCount", { count: view.total_rounds })}
                  startedAt={view.started_at}
                  endedAt={view.ended_at}
                />
              }
            />
          </div>
        </QuizFrame>
      </>
    )
  }

  return (
    <>
      <ConnectionStatus connected={socketConnected} />
      <QuizFrame
        aside={
          // the scores are under the veil too (display: contents keeps the column's gaps)
          <div inert={isPaused} className="contents">
            <PlayerScoreboard players={view.players} currentUserId={user?.id} showAnswered={phase === "playing"} />
            <QuizLeaveButton onLeave={handleLeaveRoom} />
          </div>
        }
      >
        <div ref={gameRef} inert={isPaused} tabIndex={-1} className="outline-none">
          {adhan.prayer ? (
            <AdhanSuggestion prayerKey={adhan.prayer.key} onPause={pauseFromStrip} onDismiss={adhan.answer} pausing={prayerPause.isPausing} className="mb-4" />
          ) : null}
          <Panel>
            <QuizHeader
              title={gameName}
              sub={sub}
              spectating={view.is_spectator}
              end={
                phase === "playing" || pauseControl ? (
                  <>
                    {phase === "playing" ? <span className="text-[13px] text-muted-foreground">{answeredNote}</span> : null}
                    {pauseControl}
                  </>
                ) : undefined
              }
            />

            {phase === "playing" ? (
              <>
                <div className="mb-3.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  {canStillEarn ? (
                    <p className="text-[14px] leading-snug text-muted-foreground">
                      <Trans i18nKey="game.quiz.kalimat.worthNow" count={worth} components={{ b: <b className="font-medium text-foreground" /> }} />
                    </p>
                  ) : (
                    // keeps the clock on its side of the row
                    <span aria-hidden="true" />
                  )}
                  {/* the thread clock: PhaseTimer hands ThreadClock the round's start and
                      length, one compositor animation per round (WP-18) */}
                  {view.round_started_at && view.turn_duration_seconds > 0 ? (
                    <PhaseTimer
                      timerStartedAt={view.round_started_at}
                      durationSeconds={view.turn_duration_seconds}
                      onExpired={handleTimerExpired}
                      paused={isPaused}
                      frozenRemaining={state.paused?.remaining_seconds}
                      className="w-[150px] sm:w-[220px]"
                    />
                  ) : null}
                </div>
                <HintDisplay hints={view.hints} hintsRevealed={effectiveHintsRevealed} maxHints={maxHints} nextHintIn={hintClock.nextIn} />
                {view.is_spectator ? (
                  <p className="mt-4 text-[14px] text-muted-foreground">{t("game.spectatorView")}</p>
                ) : (
                  <AnswerInput
                    onSubmit={handleSubmitAnswer}
                    disabled={view.is_spectator || isPaused}
                    answered={view.my_answered}
                    pointsEarned={view.my_points}
                    answeredNote={t("game.quiz.kalimat.waitingNote")}
                    placeholder={t(prompt)}
                    attemptsLeft={view.my_attempts_left}
                    maxAttempts={view.max_attempts}
                  />
                )}
                {showLastRound ? <LastRoundCard last={lastRound} /> : null}
              </>
            ) : null}

            {phase === "results" ? (
              <RoundResults
                correctAnswer={view.correct_answer || ""}
                explanation={view.explanation}
                roundResults={view.round_results}
                isHost={view.is_host}
                isReady={!!user && (view.ready_players ?? []).includes(user.id)}
                readyCount={view.ready_count ?? 0}
                readyTotal={view.total_players}
                isLastRound={view.current_round >= view.total_rounds}
                onNextRound={handleNextRound}
                isAdvancing={isAdvancing}
                currentUserId={user?.id}
                isSpectator={view.is_spectator}
              />
            ) : null}
          </Panel>
        </div>
        <PauseLayer
          pause={state.paused ?? null}
          canResume={prayerPause.canResume}
          onResume={prayerPause.resume}
          resuming={prayerPause.isResuming}
          isHost={state.is_host}
          isSpectator={state.is_spectator}
          currentUserId={user?.id}
          clockTotal={state.turn_duration_seconds}
          onRefresh={prayerPause.refresh}
          gameRef={gameRef}
        />
      </QuizFrame>
    </>
  )
}
