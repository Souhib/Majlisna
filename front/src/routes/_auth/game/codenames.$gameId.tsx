import { createFileRoute } from "@tanstack/react-router"
import { useCallback, useRef } from "react"
import { useTranslation } from "react-i18next"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { BoardLegend } from "@/components/games/codenames/BoardLegend"
import { ClueBanner } from "@/components/games/codenames/ClueBanner"
import { ClueHistory } from "@/components/games/codenames/ClueHistory"
import { ClueAnnouncer, CluePanel } from "@/components/games/codenames/CluePanel"
import { CodenamesMyInfo } from "@/components/games/codenames/CodenamesMyInfo"
import { CodenamesPlayerList } from "@/components/games/codenames/CodenamesPlayerList"
import { GameBoard } from "@/components/games/codenames/GameBoard"
import { GameOverScreen } from "@/components/games/codenames/GameOverScreen"
import { GameOverTransition } from "@/components/games/codenames/GameOverTransition"
import { playedWords, spymasterOf } from "@/components/games/codenames/model"
import { ScorePanel } from "@/components/games/codenames/ScorePanel"
import { colophonOf } from "@/components/games/shared/ColophonMeta"
import { GameErrorFallback } from "@/components/games/shared/GameErrorFallback"
import { PhaseTimer } from "@/components/games/shared/PhaseTimer"
import { AdhanSuggestion, PauseControl, PauseLayer, useAdhanSuggestion, usePrayerPause } from "@/components/games/shared/prayer-pause"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { Panel } from "@/components/ui/panel"
import { Skeleton } from "@/components/ui/skeleton"
import { useCodenamesGame } from "@/hooks/use-codenames-game"

export const Route = createFileRoute("/_auth/game/codenames/$gameId")({
  component: () => (
    <ErrorBoundary fallback={<GameErrorFallback />}>
      <CodenamesGamePage />
    </ErrorBoundary>
  ),
})

/**
 * Codenames (sketch C and D): the board panel (header, clock, the clue on the table,
 * the 5 × 5 cloth, the composer or End Turn, the legend) beside the table and the clues
 * so far; at the end the colophon (sketch H) takes the side and the board shows every
 * card. The page wrapper is `relative`: while the host has paused the game for the
 * prayer, the pause veil lies over it and everything under it is inert.
 */
function CodenamesGamePage() {
  const { gameId } = Route.useParams()
  const { t } = useTranslation()

  const {
    user,
    gameState,
    serverState,
    isLoading,
    socketConnected,
    cancelMessage,
    isPaused,
    showGameOverTransition,
    roomIdRef,
    clueWord,
    setClueWord,
    clueNumber,
    setClueNumber,
    isSubmittingClue,
    handleGiveClue,
    handleGuessCard,
    handleEndTurn,
    handleLeaveRoom,
    handleBackToRoom,
    handleHintViewed,
    handleTimerExpired,
    navigate,
  } = useCodenamesGame(gameId)

  // The prayer pause: the host's control, the veil over the whole game, the adhan strip.
  const prayerPause = usePrayerPause("codenames", gameId, serverState)
  const adhan = useAdhanSuggestion({ gameId, canPause: prayerPause.canPause, paused: isPaused })
  const gameRef = useRef<HTMLDivElement>(null)
  const { answer: answerAdhan } = adhan
  const { pause: pauseGame } = prayerPause
  const pauseFromStrip = useCallback(() => {
    answerAdhan()
    pauseGame()
  }, [answerAdhan, pauseGame])

  if (cancelMessage) {
    return (
      <div className="page-wrap py-10">
        <Panel className="mx-auto max-w-xl">
          <EmptyState
            titleAs="h2"
            title={t("game.gameOver")}
            description={cancelMessage}
            action={<p className="type-meta">{t("game.codenames.redirecting")}</p>}
          />
        </Panel>
      </div>
    )
  }

  if (!gameState) {
    if (isLoading) return <BoardSkeleton label={t("common.loading")} />
    return (
      <div className="page-wrap py-10">
        <Panel className="mx-auto max-w-xl">
          <EmptyState
            titleAs="h2"
            title={t("common.error")}
            description={t("game.codenames.loadFailed")}
            action={<Button onClick={() => navigate({ to: "/" })}>{t("common.goHome")}</Button>}
          />
        </Panel>
      </div>
    )
  }

  const isFinished = gameState.status === "finished"
  const isSpectator = gameState.my_role === "spectator"
  const isMyTurn = !isSpectator && gameState.current_team === gameState.my_team
  const isSpymaster = gameState.my_role === "spymaster"
  const clueGiven = !!gameState.current_turn?.clue_word
  const canGiveClue = isMyTurn && isSpymaster && !clueGiven && !isFinished
  const canGuess = isMyTurn && !isSpymaster && clueGiven && !isFinished

  const cardVotes = gameState.current_turn?.card_votes ?? {}
  const votedCount = Object.keys(cardVotes).length
  const totalOperatives = gameState.players.filter((p) => p.team === gameState.current_team && p.role === "operative").length
  const history = serverState?.clue_history ?? []

  const timerSeconds = serverState?.timer_config ? (clueGiven ? serverState.timer_config.guess_seconds : serverState.timer_config.clue_seconds) : 0
  const showClock = !!serverState?.timer_started_at && gameState.status === "in_progress" && timerSeconds > 0
  const spymaster = spymasterOf(gameState.players, gameState.current_team)

  return (
    <div className="page-wrap relative py-5 sm:py-8" data-game="codenames">
      <ConnectionStatus connected={socketConnected} />
      {/* Read a new clue out once, for every role (spectators too), outside the part of
          the page the prayer pause makes inert. */}
      <ClueAnnouncer
        clueWord={isFinished ? null : gameState.current_turn?.clue_word}
        clueNumber={gameState.current_turn?.clue_number}
        teamName={t(`game.codenames.teams.${gameState.current_team}`)}
      />
      <GameOverTransition show={showGameOverTransition} winner={gameState.winner} />

      <div ref={gameRef} inert={isPaused} tabIndex={-1} className="outline-none">
        {adhan.prayer ? (
          <AdhanSuggestion prayerKey={adhan.prayer.key} onPause={pauseFromStrip} onDismiss={adhan.answer} pausing={prayerPause.isPausing} className="mb-4" />
        ) : null}

        <div className="cn-layout" data-finished={isFinished ? "true" : undefined}>
          <Panel className="cn-area-board max-sm:border-0 max-sm:bg-transparent max-sm:p-0" aria-label={t("game.codenames.board")}>
            <ScorePanel
              redRemaining={gameState.red_remaining}
              blueRemaining={gameState.blue_remaining}
              currentTeam={gameState.current_team}
              currentTurn={gameState.current_turn}
              isMyTurn={isMyTurn}
              isFinished={isFinished}
              isSpymaster={isSpymaster}
              winner={gameState.winner}
              myInfo={<CodenamesMyInfo myTeam={gameState.my_team} myRole={gameState.my_role} />}
              clock={
                showClock ? (
                  <PhaseTimer
                    timerStartedAt={serverState?.timer_started_at ?? null}
                    durationSeconds={timerSeconds}
                    onExpired={handleTimerExpired}
                    paused={isPaused}
                    frozenRemaining={serverState?.paused?.remaining_seconds}
                  />
                ) : null
              }
              pause={
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

            {!isFinished && gameState.current_turn && !canGiveClue ? (
              <ClueBanner
                turn={gameState.current_turn}
                spymasterName={spymaster?.username}
                pointing={clueGiven ? { current: votedCount, total: totalOperatives } : null}
              />
            ) : null}

            <GameBoard
              board={gameState.board}
              isSpymaster={isSpymaster}
              canGuess={canGuess}
              isFinished={isFinished}
              onGuessCard={handleGuessCard}
              cardVotes={cardVotes}
              currentUserId={user?.id}
              onHintViewed={handleHintViewed}
              players={gameState.players}
              playedWords={isFinished ? playedWords(history) : undefined}
            />

            {canGiveClue ? (
              <CluePanel
                clueWord={clueWord}
                clueNumber={clueNumber}
                isSubmitting={isSubmittingClue}
                onClueWordChange={setClueWord}
                onClueNumberChange={setClueNumber}
                onSubmit={handleGiveClue}
              />
            ) : null}

            {canGuess ? (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                <p className="text-[13.5px] leading-snug text-muted-foreground">
                  {totalOperatives > 1 ? t("game.codenames.pointTogether") : t("game.codenames.tapToGuess")}
                </p>
                <Button variant="secondary" size="sm" onClick={handleEndTurn}>
                  {t("game.codenames.endTurn")}
                </Button>
              </div>
            ) : null}

            <BoardLegend />
          </Panel>

          <div className="cn-area-side">
            <CodenamesPlayerList players={gameState.players} currentTeam={gameState.current_team} currentUserId={user?.id} isFinished={isFinished} />
            <ClueHistory history={history} />
          </div>

          {isFinished && gameState.winner && !showGameOverTransition ? (
            <div className="cn-area-colophon">
              <GameOverScreen
                winner={gameState.winner}
                roomId={roomIdRef.current}
                board={gameState.board}
                onBackToRoom={handleBackToRoom}
                onLeaveRoom={handleLeaveRoom}
                history={history}
                players={gameState.players}
                remaining={{ red: gameState.red_remaining, blue: gameState.blue_remaining }}
                achievements={serverState?.newly_unlocked_achievements}
                currentUserId={user?.id}
                isHost={!!serverState?.is_host}
                colophon={colophonOf(serverState)}
              />
            </div>
          ) : null}
        </div>
      </div>

      <PauseLayer
        pause={serverState?.paused ?? null}
        canResume={prayerPause.canResume}
        onResume={prayerPause.resume}
        resuming={prayerPause.isResuming}
        isHost={!!serverState?.is_host}
        isSpectator={isSpectator}
        currentUserId={user?.id}
        clockTotal={showClock ? timerSeconds : 0}
        onRefresh={prayerPause.refresh}
        gameRef={gameRef}
      />
    </div>
  )
}

/** Loading: the board as bare warp, still. */
function BoardSkeleton({ label }: { label: string }) {
  return (
    <div className="page-wrap py-5 sm:py-8" aria-busy="true">
      <p className="sr-only" role="status">
        {label}
      </p>
      <div className="cn-layout">
        <Panel className="cn-area-board max-sm:border-0 max-sm:bg-transparent max-sm:p-0">
          <Skeleton className="mb-4 h-6 w-48" />
          <div className="cn-board-wrap">
            <div className="cn-board">
              {Array.from({ length: 25 }, (_, i) => (
                <Skeleton key={i} className="min-h-[max(64px,calc(var(--cw)/1.5))]" />
              ))}
            </div>
          </div>
        </Panel>
      </div>
    </div>
  )
}
