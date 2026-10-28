import { createFileRoute } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { GameErrorFallback } from "@/components/games/shared/GameErrorFallback"
import { PhaseTimer } from "@/components/games/shared/PhaseTimer"
import { AdhanSuggestion, PauseControl, PauseLayer, useAdhanSuggestion, usePrayerPause } from "@/components/games/shared/prayer-pause"
import { DescriptionPhase } from "@/components/games/undercover/DescriptionPhase"
import { EliminationOverlay } from "@/components/games/undercover/EliminationOverlay"
import { colophonOf } from "@/components/games/shared/ColophonMeta"
import { GameOverScreen } from "@/components/games/undercover/GameOverScreen"
import { Lawh, type LawhWord } from "@/components/games/undercover/Lawh"
import { MrWhiteGuessPanel } from "@/components/games/undercover/MrWhiteGuessPanel"
import { PhaseAnnouncer } from "@/components/games/undercover/PhaseAnnouncer"
import { RoleRevealPhase } from "@/components/games/undercover/RoleRevealPhase"
import { RoundOverPanel } from "@/components/games/undercover/RoundOverPanel"
import { UndercoverGameHeader } from "@/components/games/undercover/UndercoverGameHeader"
import { UndercoverLeaveButton } from "@/components/games/undercover/UndercoverLeaveButton"
import { UndercoverPlayerList } from "@/components/games/undercover/UndercoverPlayerList"
import { VoteHistory } from "@/components/games/undercover/VoteHistory"
import { VotingPhase } from "@/components/games/undercover/VotingPhase"
import { Panel } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { useUndercoverGame } from "@/hooks/use-undercover-game"
import { rememberReads, storedReads } from "@/lib/undercover-session"
import { useViewTransitionValue } from "@/lib/view-transition"

export const Route = createFileRoute("/_auth/game/undercover/$gameId")({
  component: () => (
    <ErrorBoundary fallback={<GameErrorFallback />}>
      <UndercoverGamePage />
    </ErrorBoundary>
  ),
})

/** Phases in which the player holds their own tablet. */
const TABLET_PHASES = new Set(["role_reveal", "describing", "playing", "mr_white_guessing"])

function UndercoverGamePage() {
  const { gameId } = Route.useParams()
  const { t } = useTranslation()

  const {
    gameState,
    serverState,
    isLoading,
    socketConnected,
    cancelMessage,
    isPaused,
    isAlive,
    isSpectator,
    isMyTurnToDescribe,
    isMrWhiteGuesser,
    mrWhiteGuessInput,
    isSubmittingMrWhiteGuess,
    isStartingNextRound,
    setMrWhiteGuessInput,
    handleStartNextRound,
    handleSubmitMrWhiteGuess,
    hasVoted,
    selectedVote,
    isSubmittingVote,
    descriptionInput,
    descriptionError,
    isSubmittingDescription,
    showEliminationOverlay,
    eliminationData,
    roomIdRef,
    user,
    handleSelectPlayer,
    handleConfirmVote,
    handleSubmitDescription,
    handleDismissRole,
    handleHintViewed,
    handleTimerExpired,
    handleLeaveRoom,
    handleBackToRoom,
    handleDismissElimination,
    handleDescriptionInputChange,
  } = useUndercoverGame(gameId)

  // The tablet's memory lives here, not in the tablet, which is put down while a seat
  // empties and picked up again for the next round; the read count also survives a
  // reload of the tab (it used to reset to "not read yet").
  const [reads, setReads] = useState(() => storedReads(gameId))
  const [meaningSeen, setMeaningSeen] = useState(false)
  const countRead = useCallback(() => setReads((n) => n + 1), [])
  useEffect(() => {
    if (reads > 0) rememberReads(gameId, reads)
  }, [gameId, reads])

  // Phase swaps crossfade through a view transition (no blank exit between phases).
  const phase = useViewTransitionValue(gameState.phase)

  const myWord = useMemo<LawhWord | null>(() => {
    if (gameState.my_role === "mr_white" || !gameState.my_word) return null
    return { arabic: serverState?.my_word_ar_vocalized || serverState?.my_word_ar, latin: gameState.my_word }
  }, [gameState.my_role, gameState.my_word, serverState?.my_word_ar, serverState?.my_word_ar_vocalized])

  const hint = serverState?.my_word_hint ?? null
  const handleMeaningOpen = useCallback(() => {
    if (!meaningSeen && gameState.my_word) handleHintViewed(gameState.my_word)
    setMeaningSeen(true)
  }, [meaningSeen, gameState.my_word, handleHintViewed])

  // The prayer pause: the host's control, the veil over the whole game, the adhan strip.
  const prayerPause = usePrayerPause("undercover", gameId, serverState)
  const adhan = useAdhanSuggestion({ gameId, canPause: prayerPause.canPause, paused: isPaused })
  const gameRef = useRef<HTMLDivElement>(null)
  const { answer: answerAdhan } = adhan
  const { pause: pauseGame } = prayerPause
  const pauseFromStrip = useCallback(() => {
    answerAdhan()
    pauseGame()
  }, [answerAdhan, pauseGame])

  const voteHistory = useMemo(() => serverState?.vote_history ?? [], [serverState?.vote_history])
  const thisRound = useMemo(() => voteHistory.find((r) => r.round === gameState.round) ?? null, [voteHistory, gameState.round])

  if (cancelMessage) {
    return (
      <div className="uc-page">
        <Panel tone="brass" className="mx-auto mt-8 max-w-xl text-center" role="alert">
          <h2 className="type-title text-[26px]">{t("game.gameOver")}</h2>
          <p className="mt-2 text-[15px] text-muted-foreground">{cancelMessage}</p>
          <p className="mt-1 text-[14px] text-muted-foreground">{t("game.undercover.redirecting")}</p>
        </Panel>
      </div>
    )
  }

  const timerSeconds =
    serverState?.timer_config && serverState.timer_started_at && ["describing", "playing", "mr_white_guessing"].includes(gameState.phase)
      ? gameState.phase === "describing"
        ? serverState.timer_config.description_seconds
        : serverState.timer_config.voting_seconds
      : 0
  const clock =
    timerSeconds > 0 && serverState?.timer_started_at ? (
      <PhaseTimer
        timerStartedAt={serverState.timer_started_at}
        durationSeconds={timerSeconds}
        onExpired={handleTimerExpired}
        paused={isPaused}
        frozenRemaining={serverState.paused?.remaining_seconds}
      />
    ) : null

  const loading = isLoading && !gameState.my_role
  const holdsTablet = !loading && !isSpectator && !!gameState.my_role && TABLET_PHASES.has(phase)

  // The table is listed once per screen. While describing and voting the seats are the
  // phase's own list (DescriptionList: who spoke, what they wrote, who voted, the Mayor,
  // the emptied seats); the round's reveal is the verdict. The separate list of players
  // is for the phases that have no list of their own (the first reading, Mr. White's
  // guess) and the colophon.
  const listsSeats = phase === "describing" || phase === "playing" || phase === "round_over"
  const table = (
    <>
      {listsSeats ? null : (
        <UndercoverPlayerList players={gameState.players} eliminated={serverState?.eliminated_players} currentUserId={user?.id} />
      )}
      <VoteHistory history={voteHistory} expandAll={phase === "game_over"} />
    </>
  )

  return (
    <div className="uc-page relative">
      <ConnectionStatus connected={socketConnected} />
      <PhaseAnnouncer phase={phase} />

      {/* While the game is paused for the prayer everything under the veil is inert. */}
      <div ref={gameRef} inert={isPaused} tabIndex={-1} className="outline-none">
        {adhan.prayer ? (
          <AdhanSuggestion
            prayerKey={adhan.prayer.key}
            onPause={pauseFromStrip}
            onDismiss={adhan.answer}
            pausing={prayerPause.isPausing}
            className="mb-4"
          />
        ) : null}

        <UndercoverGameHeader
          round={gameState.round}
          phase={loading ? "" : phase}
          isSpectator={isSpectator}
          clock={clock}
          pauseControl={
            <PauseControl
              canPause={prayerPause.canPause}
              canResume={prayerPause.canResume}
              paused={isPaused}
              onPause={prayerPause.pause}
              onResume={prayerPause.resume}
              pending={prayerPause.isPausing || prayerPause.isResuming}
            />
          }
        />

        {loading ? (
          <div className="uc-stage" data-split="" aria-busy="true">
            <Skeleton className="mx-auto mt-[30px] h-[360px] w-full max-w-[340px]" />
            <div className="grid gap-3">
              <Skeleton className="h-8 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
              <span className="sr-only">{t("common.loading")}</span>
            </div>
          </div>
        ) : phase === "game_over" ? (
          <div className="uc-end">
            <GameOverScreen
              winner={gameState.winner}
              roomId={roomIdRef.current}
              isHost={gameState.isHost}
              myRole={gameState.my_role}
              players={gameState.players}
              voteHistory={voteHistory}
              rounds={gameState.round}
              wordExplanations={serverState?.word_explanations}
              achievements={serverState?.newly_unlocked_achievements}
              colophon={colophonOf(serverState)}
              onBackToRoom={handleBackToRoom}
              onLeaveRoom={handleLeaveRoom}
            />
            <div className="grid content-start gap-8">{table}</div>
          </div>
        ) : (
          <div className="uc-stage" data-split={holdsTablet || phase === "round_over" ? "" : undefined}>
            {holdsTablet ? (
              <div className="uc-lawh-col">
                <Lawh
                  round={gameState.round}
                  word={myWord}
                  reads={reads}
                  onRead={countRead}
                  hint={hint}
                  meaningShown={meaningSeen}
                  onMeaningOpen={handleMeaningOpen}
                />
              </div>
            ) : null}

            <div className={phase === "round_over" ? "uc-main lg:col-span-2" : "uc-main"}>
              {showEliminationOverlay && eliminationData && phase !== "round_over" && phase !== "mr_white_guessing" ? (
                <EliminationOverlay
                  round={eliminationData.round}
                  eliminatedUsername={eliminationData.username}
                  eliminatedRole={eliminationData.role}
                  eliminatedUserId={eliminationData.user_id}
                  votes={eliminationData.votes}
                  currentUserId={user?.id}
                  myWord={myWord}
                  onDismiss={handleDismissElimination}
                />
              ) : null}

              {phase === "role_reveal" && gameState.my_role && !isSpectator ? <RoleRevealPhase onDismiss={handleDismissRole} /> : null}

              {phase === "describing" ? (
                <DescriptionPhase
                  descriptionOrder={gameState.descriptionOrder}
                  currentDescriberIndex={gameState.currentDescriberIndex}
                  descriptions={gameState.descriptions}
                  currentUserId={user?.id}
                  players={gameState.players}
                  eliminated={serverState?.eliminated_players}
                  isMyTurnToDescribe={isMyTurnToDescribe}
                  isAlive={isAlive}
                  descriptionInput={descriptionInput}
                  descriptionError={descriptionError}
                  isSubmittingDescription={isSubmittingDescription}
                  onDescriptionInputChange={handleDescriptionInputChange}
                  onSubmitDescription={handleSubmitDescription}
                />
              ) : null}

              {phase === "playing" ? (
                <VotingPhase
                  players={gameState.players}
                  descriptions={gameState.descriptions}
                  descriptionOrder={gameState.descriptionOrder}
                  isAlive={isAlive}
                  isSpectator={isSpectator}
                  hasVoted={hasVoted}
                  isSubmittingVote={isSubmittingVote}
                  selectedVote={selectedVote}
                  votedPlayers={gameState.votedPlayers}
                  eliminated={serverState?.eliminated_players}
                  currentUserId={user?.id}
                  onSelectPlayer={handleSelectPlayer}
                  onConfirmVote={handleConfirmVote}
                />
              ) : null}

              {phase === "round_over" ? (
                <RoundOverPanel
                  round={thisRound}
                  roundNumber={gameState.round}
                  currentUserId={user?.id}
                  myWord={myWord}
                  isHost={gameState.isHost && !isSpectator}
                  isStarting={isStartingNextRound}
                  onNextRound={handleStartNextRound}
                />
              ) : null}

              {phase === "mr_white_guessing" ? (
                <MrWhiteGuessPanel
                  isGuesser={isMrWhiteGuesser}
                  round={thisRound}
                  currentUserId={user?.id}
                  guess={mrWhiteGuessInput}
                  isSubmitting={isSubmittingMrWhiteGuess}
                  onGuessChange={setMrWhiteGuessInput}
                  onSubmit={handleSubmitMrWhiteGuess}
                />
              ) : null}

              {table}

              {phase !== "role_reveal" ? <UndercoverLeaveButton onLeave={handleLeaveRoom} isSpectator={isSpectator} isEliminated={!isAlive && !isSpectator} /> : null}
            </div>
          </div>
        )}
      </div>

      <PauseLayer
        pause={serverState?.paused ?? null}
        canResume={prayerPause.canResume}
        onResume={prayerPause.resume}
        resuming={prayerPause.isResuming}
        isHost={gameState.isHost}
        isSpectator={isSpectator}
        currentUserId={user?.id}
        clockTotal={timerSeconds}
        onRefresh={prayerPause.refresh}
        gameRef={gameRef}
      />
    </div>
  )
}
