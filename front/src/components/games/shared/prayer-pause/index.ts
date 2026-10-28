/**
 * The prayer pause (وقفة الصلاة) of the four games: the host's header control, the veil
 * every seat sees while the game is paused, the adhan suggestion, and the helpers the
 * game pages use to freeze their clocks and to read the server's answers.
 */
export { AdhanSuggestion } from "./AdhanSuggestion"
export { elapsedAtPause, formatWallClock, isGamePausedError, isTimerStopAction, msUntilAnyoneCanResume, type PauseFields, type PauseGame } from "./pause-utils"
export { PauseControl } from "./PauseControl"
export { PauseLayer, type PauseLayerProps, PauseVeil } from "./PauseVeil"
export { ADHAN_CHECK_MS, ADHAN_SUGGESTION_WINDOW_MS, adhanSuggestionKey, useAdhanSuggestion } from "./use-adhan-suggestion"
export { usePrayerPause } from "./use-prayer-pause"
