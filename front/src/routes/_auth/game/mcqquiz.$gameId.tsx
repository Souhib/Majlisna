import { createFileRoute } from "@tanstack/react-router"
import { type ReactNode, useCallback, useRef } from "react"
import { useTranslation } from "react-i18next"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { ChoiceButtons } from "@/components/games/mcqquiz/ChoiceButtons"
import { McqRoundResults } from "@/components/games/mcqquiz/McqRoundResults"
import { choiceNotes, QUIZ_ROUND_MAX, tallyWeaveMs } from "@/components/games/mcqquiz/reveal"
import { QuestionDisplay } from "@/components/games/mcqquiz/QuestionDisplay"
import { ScoreBands } from "@/components/games/mcqquiz/ScoreBands"
import { useAchievementSeals } from "@/components/games/shared/achievement-seals"
import { ColophonMeta } from "@/components/games/shared/ColophonMeta"
import { isGameGoneError } from "@/components/games/shared/game-errors"
import { GameErrorFallback } from "@/components/games/shared/GameErrorFallback"
import { PhaseTimer } from "@/components/games/shared/PhaseTimer"
import { PlayerScoreboard } from "@/components/games/shared/PlayerScoreboard"
import { AdhanSuggestion, elapsedAtPause, PauseControl, PauseLayer, useAdhanSuggestion, usePrayerPause } from "@/components/games/shared/prayer-pause"
import { QuizGameOver } from "@/components/games/shared/QuizGameOver"
import { QuizFrame, QuizGoneNotice, QuizHeader, QuizLeaveButton, QuizLoading } from "@/components/games/shared/QuizLayout"
import { Figure, useHeldForPhase } from "@/components/games/shared/quiz-utils"
import { gameRiddleScope } from "@/components/rooms/samar-riddle"
import { SamarRiddle } from "@/components/rooms/SamarRiddle"
import { Button } from "@/components/ui/button"
import { Panel } from "@/components/ui/panel"
import { useMcqQuizGame } from "@/hooks/use-mcqquiz-game"
import { type PhaseFocusTargets, usePhaseFocus } from "@/hooks/use-phase-focus"
import { useViewTransitionValue } from "@/lib/view-transition"

/**
 * Where focus goes when the phase on screen changes (F2, `usePhaseFocus`): the new
 * question (its h2), the note that you locked in while the others answer, the reveal's
 * first heading (the explanation, else "This question"), the colophon's title.
 */
const FOCUS_TARGETS: PhaseFocusTargets = {
  playing: "h2",
  locked: "[data-phase-focus='locked']",
  results: "h3",
  game_over: "[data-colophon-title]",
}

export const Route = createFileRoute("/_auth/game/mcqquiz/$gameId")({
  component: () => (
    <ErrorBoundary fallback={<GameErrorFallback />}>
      <McqQuizGamePage />
    </ErrorBoundary>
  ),
})

/**
 * The Quiz (sketch C bottom-right, D Arabic phone): four choices, one answer, and the
 * story behind it. The three score bands say what a right answer is worth as the clock
 * runs; the reveal brasses the right choice and strikes a wrong pick on its letter.
 * Phases swap through a view transition; the end of the game is the colophon. The
 * game's logic is `useMcqQuizGame`; this page draws it.
 */
function McqQuizGamePage() {
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
    now,
    selectedChoice,
    lockIn,
    hasLockedIn,
    isLockingIn,
    isAdvancing,
    handleSelectChoice,
    handleConfirmChoice,
    handleTimerExpired,
    handleNextRound,
    handleLeaveRoom,
    handleBackToRoom,
  } = useMcqQuizGame(gameId)

  // The phase on screen follows the server's through a view transition (180 ms crossfade).
  const phase = useViewTransitionValue(state?.round_phase ?? null)
  // ...and is drawn from the state it belongs to, so the outgoing frame stays true.
  const held = useHeldForPhase(state, phase)
  // Focus follows the phase on screen: locking in among others is a phase of its own
  // (the Lock in button goes), the page's first state is not a change.
  const gameRef = useRef<HTMLDivElement>(null)
  const focusKey = phase === "playing" && (held ?? state)?.my_answered ? "locked" : phase
  usePhaseFocus(state ? focusKey : null, gameRef, { targets: FOCUS_TARGETS })

  // The prayer pause: the host's control, the veil over the whole game, the adhan strip.
  const prayerPause = usePrayerPause("mcqquiz", gameId, state)
  const adhan = useAdhanSuggestion({ gameId, canPause: prayerPause.canPause, paused: isPaused })
  const { answer: answerAdhan } = adhan
  const { pause: pauseGame } = prayerPause
  const pauseFromStrip = useCallback(() => {
    answerAdhan()
    pauseGame()
  }, [answerAdhan, pauseGame])

  const seals = useAchievementSeals(state?.newly_unlocked_achievements, state?.leaderboard, user?.id)

  const gameName = t("games.mcqQuiz.name")

  if (cancelMessage) return <QuizGoneNotice message={cancelMessage} />
  if (!state) {
    // a game that is gone gets its notice (set by the hook), not a crash screen
    if (queryError && !isLoading && !isGameGoneError(queryError)) return <GameErrorFallback error={queryError} />
    return <QuizLoading title={gameName} />
  }
  const view = held ?? state

  const duration = view.turn_duration_seconds
  const startedAt = view.round_started_at ? new Date(view.round_started_at).getTime() : null
  // While paused, the band stands where the server froze the clock.
  const frozenElapsed = isPaused ? elapsedAtPause(state.paused, duration) : null
  const elapsedRatio =
    phase === "playing" && !view.my_answered && startedAt != null && duration > 0
      ? Math.max(0, Math.min(1, (frozenElapsed ?? (now - startedAt) / 1000) / duration))
      : null
  const showResults = phase === "results"
  // When you locked in: the server's measure once the answer is revealed (it survives a
  // reload); while the question is open the server keeps it, so your own tap stands in.
  const lockedElapsed = showResults
    ? view.my_answer_time_ms != null
      ? view.my_answer_time_ms / 1000
      : null
    : lockIn && lockIn.round === view.current_round
      ? lockIn.elapsed
      : null
  const lockedRatio = lockedElapsed != null && duration > 0 ? Math.max(0, Math.min(1, lockedElapsed / duration)) : null
  const lockedRemaining = lockedElapsed != null && duration > 0 ? Math.max(0, duration - lockedElapsed) : null

  const myResult = view.round_results.find((r) => r.user_id === user?.id)
  const correctIndex = view.correct_answer_index
  // Your pick: the server's once revealed (after a reload too); while open, what you tapped.
  const myIndex = view.is_spectator ? null : showResults ? (view.my_choice_index ?? null) : selectedChoice
  const answeredCount = view.players.filter((p) => p.current_round_answered).length
  const answeredNote = t("game.quiz.answeredCount", { answered: answeredCount, total: view.players.length })
  const resultsBand = showResults && myResult?.chose_correct && myResult.points >= 1 ? (Math.min(3, myResult.points) as 1 | 2 | 3) : null

  // The note at the end of each choice: "you" once you have locked in; at the reveal, how
  // many chose it ("3 players", "you and 2 others", "+2 · you"), from the server's tallies.
  const notes = choiceNotes({
    count: view.choices.length,
    revealed: showResults,
    tallies: view.choice_tallies,
    myIndex,
    myAnswered: view.my_answered,
    correctIndex,
    myPoints: myResult?.chose_correct ? myResult.points : null,
  })
  const tags: ReactNode[] = notes.map((note) => {
    if (!note) return null
    if (note.kind === "picked") {
      if (note.count > 0) return t("game.quiz.mcq.pickedBy", { count: note.count })
      return (
        <>
          <Figure>
            <span aria-hidden="true">0</span>
          </Figure>
          <span className="sr-only">{t("game.quiz.mcq.pickedBy", { count: 0 })}</span>
        </>
      )
    }
    const who = note.others > 0 ? t("game.quiz.mcq.youAndOthers", { count: note.others }) : t("game.quiz.you")
    if (note.points == null) return who
    return (
      <>
        <Figure>+{note.points}</Figure>
        {" · "}
        {who}
      </>
    )
  })

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
  const clock =
    phase === "playing" && view.round_started_at && duration > 0 ? (
      <PhaseTimer
        timerStartedAt={view.round_started_at}
        durationSeconds={duration}
        onExpired={handleTimerExpired}
        paused={isPaused}
        frozenRemaining={state.paused?.remaining_seconds}
        className="w-[138px] sm:w-[150px]"
      />
    ) : null

  const sub = t("game.quiz.mcq.questionOf", { current: view.current_round, total: view.total_rounds })

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
              winnerI18nKey="game.mcqQuiz.winner"
              finalScoresI18nKey="game.mcqQuiz.finalScores"
              currentUserId={user?.id}
              roomId={roomIdRef.current}
              isHost={view.is_host}
              seals={seals}
              share={{
                game: "mcqquiz",
                host: view.host_username,
                count: t("game.quiz.questionsCount", { count: view.total_rounds }),
                startedAt: view.started_at,
                endedAt: view.ended_at,
              }}
              meta={
                <ColophonMeta
                  game={gameName}
                  host={view.host_username}
                  count={t("game.quiz.questionsCount", { count: view.total_rounds })}
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
            <PlayerScoreboard
              players={view.players}
              currentUserId={user?.id}
              showAnswered={phase === "playing"}
              maxScore={QUIZ_ROUND_MAX * view.total_rounds}
              // the reveal's authored moment is the tally threads: the scores weave once they are drawn
              weaveAfter={showResults && view.choice_tallies ? tallyWeaveMs(view.choices.length) : 0}
            />
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
                clock || pauseControl ? (
                  <>
                    {pauseControl}
                    {clock}
                  </>
                ) : undefined
              }
            />

            {phase === "playing" || showResults ? (
              <>
                <ScoreBands
                  elapsedRatio={elapsedRatio}
                  lockedRatio={lockedRatio}
                  lockedRemaining={lockedRemaining}
                  band={resultsBand}
                  missed={showResults && !!myResult && !myResult.chose_correct}
                />
                <QuestionDisplay question={view.question} />
                <ChoiceButtons
                  choices={view.choices}
                  onSelect={showResults ? () => {} : handleSelectChoice}
                  disabled={showResults || view.is_spectator || view.my_answered || hasLockedIn || isLockingIn || isPaused}
                  selectedIndex={showResults ? myIndex : selectedChoice}
                  correctIndex={showResults ? correctIndex : null}
                  roundPhase={showResults ? "results" : "playing"}
                  tags={tags}
                  tallies={view.choice_tallies}
                  players={view.players.length}
                />
              </>
            ) : null}

            {phase === "playing" && !view.is_spectator && !view.my_answered ? (
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
                <Button onClick={handleConfirmChoice} disabled={selectedChoice === null || hasLockedIn || isPaused} loading={isLockingIn}>
                  {t("game.quiz.mcq.lockIn")}
                </Button>
                {selectedChoice === null ? <p className="text-[13px] text-muted-foreground">{t("game.quiz.mcq.chooseFirst")}</p> : null}
              </div>
            ) : null}

            {phase === "playing" && view.my_answered ? (
              <p role="status" data-phase-focus="locked" className="mt-4 text-[14px] text-muted-foreground">
                <span className="font-medium text-foreground">{t("game.quiz.mcq.lockedIn")}</span> · {answeredNote}
              </p>
            ) : null}

            {phase === "playing" && view.is_spectator ? <p className="mt-4 text-[14px] text-muted-foreground">{t("game.spectatorView")}</p> : null}

            {showResults ? (
              <McqRoundResults
                explanation={view.explanation}
                roundResults={view.round_results}
                isHost={view.is_host}
                isReady={!!user && (view.ready_players ?? []).includes(user.id)}
                readyCount={view.ready_count ?? 0}
                readyTotal={view.total_players}
                isLastRound={view.current_round >= view.total_rounds}
                onNextRound={handleNextRound}
                isAdvancing={isAdvancing}
                correctChoice={correctIndex != null ? view.choices[correctIndex] : null}
                choices={view.choices}
                currentUserId={user?.id}
                isSpectator={view.is_spectator}
              />
            ) : null}

            {/* A samar riddle while the table waits for the next question (the host, or the
                ready quorum). Its question number is its wait: the riddle of the question
                before is answered here. After the last question, only that answer. */}
            {showResults ? (
              <SamarRiddle
                key={gameId}
                roomId={view.room_id}
                scope={gameRiddleScope(gameId)}
                waitKey={String(view.current_round)}
                note="round"
                ask={view.current_round < view.total_rounds}
                className="mt-6 border-t border-line pt-4"
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
          clockTotal={duration}
          onRefresh={prayerPause.refresh}
          gameRef={gameRef}
        />
      </QuizFrame>
    </>
  )
}
