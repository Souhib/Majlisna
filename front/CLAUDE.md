# CLAUDE.md - Majlisna Frontend

## Overview

React 19 SPA for the Majlisna platform. Uses TanStack Router for file-based routing, TanStack Query for server state management and real-time polling, Tailwind CSS v4 with the Samar design system (`components/ui` + `components/brand`, contract in the root `DESIGN.md`).

## Development Commands

```bash
cd front

# Start dev server
bun dev                     # http://localhost:3000

# Generate API client from backend OpenAPI spec
bun run generate            # Requires backend running on :5111

# Code quality
bun run lint                # oxlint
bun run lint:fix            # Auto-fix
bun run format              # oxfmt (pinned, config in .oxfmtrc.json; CI runs format:check)
bun run format:check        # Check only
bun run typecheck           # TypeScript strict

# Testing
bun run test                # Vitest once
bun run test:watch          # Watch mode
bun run test:coverage       # With coverage: what CI runs; floors in vitest.config.ts
bun run test:ui             # Vitest UI
```

**Tests run on two storages: never spy on `localStorage` or `sessionStorage`.** On Node ≥ 25
(a workstation) `src/test/setup.ts` installs an in-memory `Storage`; on CI's Node 22/24 the
storage is happy-dom's, a Proxy on which `vi.spyOn(localStorage, "getItem")` is never
restored, so a "blocked storage" spy leaks into every later test of the file (7 failures in
CI on 2026-11-01, green locally). Replace the global instead, which `vi.unstubAllGlobals()`
undoes: `vi.stubGlobal("localStorage", { getItem: blocked, setItem: blocked, removeItem:
blocked, clear: () => {} })`. To reproduce CI's storage locally:
`npx -y node@22 node_modules/vitest/vitest.mjs run <files>`.

## Tech Stack

- **Runtime**: Bun
- **Framework**: React 19 + TypeScript
- **Routing**: TanStack Router (file-based)
- **State**: TanStack Query (React Query) for server state
- **Styling**: Tailwind CSS v4 + Samar primitives on Radix (`components/ui`), brand pieces (`components/brand`), self-hosted @fontsource fonts (`src/fonts.ts`). Read `DESIGN.md` before any UI work.
- **Forms**: controlled inputs with the shared field validation (`components/auth/validation.ts`, `use-field-errors.ts`) and the Samar `Field`; no form or schema library (`react-hook-form` is still listed in `package.json`, but nothing imports it)
- **API**: Kubb-generated hooks from OpenAPI spec + ky HTTP client
- **Real-time**: Socket.IO (socket.io-client) pushes state into TanStack Query cache via `useSocket` hook
- **i18n**: i18next (English, French, and Arabic with RTL support)
- **Testing**: Vitest + Testing Library + MSW

## Project Structure

```
src/
├── api/
│   ├── client.ts            # ky HTTP client with JWT interceptors
│   └── generated/           # Kubb auto-generated (DO NOT EDIT)
├── components/
│   ├── ui/                  # Samar primitives (Button, Field, Panel, Dialog, Tabs…)
│   ├── brand/               # Wordmark, SaduBand, Halqa, CodeTiles, ThreadClock, Colophon…
│   ├── layout/              # MainNav (+ menu sheet), Footer, LanguageSwitch, ThemeToggle
│   ├── home/                # HomeHero (sky + name + join row), HalqaCard, DailyWordCard, GamesFihrist, SupportSection
│   ├── daily/               # The word of the day (/today): DailyWordPage, DailyReveal, DailyCountdown, use-daily-word, daily.ts (pure)
│   ├── ErrorBoundary.tsx    # Resets on navigation; a failed chunk reloads once (see "Errors reach the tracker")
│   └── NotFound.tsx
├── hooks/
│   ├── use-socket.ts        # Socket.IO hook (real-time state into TanStack Query cache)
│   ├── use-resolved-theme.ts # The light on screen ("dark"|"light"), read from <html data-theme>
│   ├── use-{undercover,codenames,wordquiz,mcqquiz}-game.ts # Each game page's logic (state, moves, timers); the page draws it
│   └── use-prayer-times.ts  # Prayer times hook
├── i18n/
│   ├── index.ts             # i18next config
│   └── locales/             # en.json, fr.json, ar.json
├── lib/
│   ├── utils.ts             # cn() utility
│   ├── motion.ts            # Motion grammar tokens as numbers (ease, dur, stagger), bezier(), inkDuration, REREAD
│   ├── view-transition.ts   # View Transitions for phase changes (feature-detected)
│   ├── sky-light.ts         # Follow the sky: sunrise/Maghrib turns (adhan), the stored record index.html reads
│   ├── sacred-names.ts      # holdsSacredName: what no gesture sweeps across (riddle, clue)
│   ├── report-error.ts      # The one door to the error tracker (Sentry-compatible): reportError, the lazy Sentry SDK and its queue
│   └── auth.ts              # Access-token storage, session marker, notices, token-link scrub
├── providers/
│   ├── AuthProvider.tsx     # JWT auth state + token refresh
│   ├── QueryProvider.tsx    # React Query client
│   ├── ThemeProvider.tsx    # The light: afternoon, night, Follow the sky (lib/sky-light.ts), the device's
│   └── index.ts
├── routes/                  # TanStack Router file-based
│   ├── __root.tsx           # Root layout (providers, nav, footer)
│   ├── index.tsx            # Home page (game selection)
│   ├── leaderboard.tsx      # Global leaderboard
│   ├── _auth.tsx            # Protected route layout
│   ├── _auth/
│   │   ├── rooms/
│   │   │   ├── index.tsx    # Room list + join form
│   │   │   ├── create.tsx   # Create room
│   │   │   └── $roomId.tsx  # Room lobby (Socket.IO real-time)
│   │   ├── game/
│   │   │   ├── undercover.$gameId.tsx  # Undercover game UI (Socket.IO)
│   │   │   ├── codenames.$gameId.tsx   # Codenames game UI (Socket.IO)
│   │   │   ├── wordquiz.$gameId.tsx   # Word Quiz game UI (Socket.IO)
│   │   │   └── mcqquiz.$gameId.tsx   # MCQ Quiz game UI (Socket.IO)
│   │   ├── profile.tsx      # User profile + stats
│   │   └── achievements.tsx # Achievement badges
│   ├── today.tsx            # The word of the day (public; components/daily)
│   ├── credits.tsx          # Image, font and icon attribution (CC BY-SA credits live here)
│   ├── privacy.tsx          # Privacy policy (Read page; text in `privacy.sections`, kept true to the code)
│   ├── terms.tsx            # Terms of use (the same Read page, components/about/LegalPage; `terms.sections`)
│   ├── about.tsx            # About + "How the games play" (components/about/GameRules, ids #undercover #codenames #kalimat #quiz)
│   └── auth/
│       ├── login.tsx        # Login form
│       └── register.tsx     # Register form
├── styles/                  # brand.css (component CSS), shell.css (nav/footer), home.css, sadu.css (generated bands), pages/*.css (codenames, quiz, rooms, undercover)
├── fonts.ts                 # Self-hosted fonts (imported first in main.tsx)
├── index.css                # Tailwind v4 + Samar tokens, type roles, motion utilities
└── main.tsx                 # App entry point
```

## Key Patterns

### API Integration (Kubb)
Auto-generated React Query hooks from backend OpenAPI spec:
```typescript
import { useGetLeaderboardApiV1StatsLeaderboardGet } from "@/api/generated"

function MyComponent() {
  const { data, isLoading, isError, refetch } = useGetLeaderboardApiV1StatsLeaderboardGet()
}
```

**Never edit files in `src/api/generated/`.** Regenerate with `bun run generate`.

**A DELETE may carry a body, and `client()` sends it.** `client()` used to put `data` on
POST, PUT and PATCH only, so `DELETE /users/me/account` left without its `{ password }` (or
`{ google_access_token }`) and every deletion from the profile answered 422; the E2E
account-deletion journey found it (WP-20). Test: `api/__tests__/wp20-delete-body.test.ts`.

### Real-time Updates (Socket.IO Primary, Conditional Polling Fallback)
Socket.IO is the primary real-time transport. The room lobby stores `roomId` in SessionStorage before navigating to game pages (`storeRoomIdForGame`), so Socket.IO connects immediately on mount via a lazy `useState` initializer (`retrieveRoomIdForGame`). Fallback: if no stored roomId (e.g., page refresh), the first REST poll provides it.

`useSocket` returns `{ connected }`. All pages (game pages and room lobby) use `refetchInterval: socketConnected ? false : 2_000` — **zero polling when Socket.IO is connected**, fast 2s polling as fallback when disconnected. `useSocket` also accepts an `onKicked` callback for handling `you_were_kicked` events from the server. After `you_were_kicked` (and after a leave), the server **cuts the room socket** (a server-initiated disconnect, which socket.io-client does not retry; a worker that did not serve the kick cuts it within 5 s, backend WP-04): never rely on that socket staying up to learn anything else. A player coming back (reconnect, or a heartbeat after the sweep marked them away) is pushed to the whole room as a `room_state`, so another seat's "away" clears without polling. Only a **re**connect invalidates (`hasConnectedRef`; a failed first attempt counts as having been down): the room state, the room's chat history (`queryKeys.room.messages`, the query `ChatPanel` reads and merges by id) and the game. The first connect re-reads the chat history only: the server pushes `room_state` on connect and answers `join_game` with `game_state` (refetching those too read the same state three times per load), but a chat line sent between the page's history read and the socket joining the room was pushed to nobody and stayed unseen until a reconnect (CI, 2026-11-01). All UI state is derived from the server response via `useMemo`, not accumulated from events.

Phase transitions detected by comparing refs to previous state (`previousPhaseRef`, `previousRoundRef`).

### Room Lobby (REST Polling + Socket.IO)
- The page's client logic is `useRoomLobby(roomId)` (`hooks/use-room-lobby.ts`, tested with fake
  timers in `use-room-lobby.test.ts`); `routes/_auth/rooms/$roomId.tsx` only draws it
- Poll room state every 2s while the socket is down (never a refusal with nothing on screen)
- Socket.IO pushes real-time updates for room state
- Auto-navigate when `active_game_id` appears (stores `roomId` in SessionStorage for game page)
- Leave room via REST `PATCH /api/v1/rooms/leave`
- The host's two removals (owner decision, 2 November 2026; `useRoomLobby.kickPlayer` /
  `banPlayer`). A kick (`PATCH /rooms/{id}/kick`) re-reads the room state and the host's removed
  players (`queryKeys.room.removals`, `GET /rooms/{id}/removals`: the host may still ban them,
  owner request of 3 November 2026); it changes neither the PIN nor the bans. A ban
  (`POST /rooms/{id}/bans`) re-reads the room state, both of the host's lists
  (`queryKeys.room.bans`, `.removals`) and the share link (`queryKeys.room.shareLink`); a new PIN
  in `room_state` re-reads the last three as well (a ban from the host's other device). The
  room's `member_removed_by_host` re-reads the removed players (and the bans, for a ban), and so
  does a newcomer in `room_state` (a removed player who sat down again leaves that list; the
  first state and a departure re-read nothing). An invalidated list no one watches (a guest's
  screen) is not fetched. `removingId`
  is the seat being removed (either kind); `removals` names the seats the host took
  ("removed" / "banned"): from this screen, noted before the request (the route pushes the room
  state before it answers) and dropped when it fails; from the room, `member_removed_by_host`
  `{room_id, user_id, banned}` (`useSocket`'s `onMemberRemoved`, sent before the room state that
  drops the seat), so every member's screen and the host's other devices know too. Dropped once
  the player is back. The activity line says "{{name}} was removed / banned" instead of "left".

### File-Based Routing
- `__root.tsx` - Root layout (double underscore)
- `_auth.tsx` - Protected layout (single underscore, redirects to login)
- `$param.tsx` - Dynamic parameters
- `index.tsx` - Index route for directory

### Authentication
- The **access token** is in localStorage (`majlisna-token`, `majlisna-token-expiry`, the user in
  `majlisna-user-data`, the non-secret marker `majlisna-session`). The **refresh token is never
  stored by the client**: it lives in the httpOnly cookie the server sets (SEC F13). A legacy
  `majlisna-refresh-token` is sent once in the body of a refresh, then deleted (`lib/auth.ts`).
- Auto-refresh 1 minute before expiry (`REFRESH_BUFFER_MS`), through `refreshSession()` in
  `api/client.ts`: cookie only, no body token, `credentials: "include"` (every `/api/v1/auth/*`
  call is sent with credentials).
- A 401 on an ordinary request triggers ONE shared refresh and replays the request once. The
  session ends (tokens cleared, `sendToLogin()`) only when the refresh itself is refused, the
  replay is refused too, or the 401 says `errors.api.sessionRevoked` (no refresh then). A 401
  `errors.api.invalidCredentials` (a re-checked current password) never touches the session,
  nor does any 401 from `/api/v1/auth/*` (`redirectsToLoginOn401`): AuthProvider owns those.

### Styling
```typescript
import { cn } from "@/lib/utils"

<div className={cn("base-class", isActive && "active-class")} />
```

### Error Handling
API errors have `error_key` for i18n and `frontend_message` as fallback:
```typescript
import { getApiErrorMessage } from "@/api/client"

try {
  await apiClient({ ... })
} catch (err) {
  const message = getApiErrorMessage(err, t("some.fallback"))
}
```

Only the server's JSON envelope is read. With no envelope (offline, a timeout, the proxy's
HTML 502 during a deploy) it returns the caller's fallback, or `t("errors.network")` without
one: never ky's or the browser's `error.message` ("Failed to fetch", "Request failed with status
code 502: POST http://…", English, with an internal URL; FR-8). An envelope with nothing
readable gives the fallback, or `t("common.error")`. `gotNoApiAnswer(err)` tells the two apart.
A test that fakes a server refusal must fake the envelope (`{ response: { data: { message } } }`),
not `new Error(message)`. **No English literal fallbacks in pages or hooks**: every fallback is
a `t(...)` key (`game.errors.*`, `common.loadFailed`, …), so a refusal without an envelope
still reads in the player's language. Tests: `api/client.test.ts` (`getApiErrorMessage`),
the WP-13 game-page tests (`routes/_auth/game/-tests/wp13-*.test.tsx`, which fail on an English
fallback), `hooks/use-codenames-game.test.ts`.

## i18n

Supports English and French (LTR) and Arabic (RTL). The root layout sets `<html dir lang>` through
`syncDocumentLanguage(i18n.language)` (`components/layout/language-switch.tsx`).

- **`i18n.language` is always exactly `en`, `fr` or `ar`.** Phones send regional tags (ar-SA,
  fr-FR): the raw tag used to become the language, so `=== "ar"` laid Arabic out left to
  right, `?lang=ar-SA` brought English content back, and the tag was cached in localStorage for
  good. `i18n/index.ts` sets `supportedLngs` and the detector's `convertDetectedLanguage` (the
  language part, lower-cased), so the cached value is the bare code too and a stored "fr-FR"
  is rewritten at boot. Do NOT add `load: "languageOnly"` or `nonExplicitSupportedLngs: true`:
  with either, i18next counts "fr-FR" itself as supported and keeps it. Still compare through
  `currentLanguage()`, and derive `dir` / `lang` with `syncDocumentLanguage`,
  `currentLanguage()` or `i18n.dir()`, never with `=== "ar"` on the raw tag. The backend's
  `normalize_lang` maps regional tags as well (defence in depth: `resolve_multilingual` and the
  socket handshake use it; a few controllers still compare `lang` raw, see backend/CLAUDE.md).
  Tests: `i18n/__tests__/detection.test.tsx` (an `ar-SA` first visit ends `dir="rtl"`, stored
  `ar`), `components/layout/__tests__/language-switch.test.tsx`,
  `e2e/tests/i18n/regional-locale.spec.ts`.
- **Each language falls back only to itself** (`fallbackLng: { fr: [], ar: [], default: ["en"] }`),
  so a French or Arabic page never downloads the English chunk. A key missing in fr or ar shows
  as its raw key, which is why the whole-tree parity test (`components/stats/__tests__/locales.test.ts`)
  must stay.
- **The first-visit dialog downloads no other locale**: its three "Choose your language" lines
  are `CHOOSE_LANGUAGE_PROMPTS` in `LanguageWelcomeModal.tsx`, each in its own language (the
  `ui.chooseLanguage` of each locale; `i18n/__tests__/detection.test.tsx` keeps them in step).
- **A locale chunk gone after a deploy reloads the page once** (`loadLocale`: a sessionStorage
  guard, re-armed by any successful load), instead of the switch storing the new language and
  showing nothing.
- `i18n` is its own instance (`i18next.createInstance()`); `detection.test.tsx` boots the real
  module per test (`vi.resetModules`) with a stubbed `navigator.languages`.

```typescript
import { useTranslation } from "react-i18next"

const { t } = useTranslation()
t("games.undercover.name")  // "Undercover" or "أندركفر"
```

Translation files in `src/i18n/locales/` (`en.json`, `fr.json`, `ar.json`, always the same keys).

- **Arabic role names are phonetic** (DESIGN.md §10): سيفيليان, أندركفر, مستر وايت (a no-break
  space inside), سبايماستر, أوبريتيف; the plural is the collective with the article ("فاز
  الأندركفر"). `components/stats/__tests__/locales.test.ts` fails if المتخفي, المدني, السيد وايت,
  رئيس الجواسيس, العميل (or their plurals) come back anywhere in `ar.json`.
- **French keeps the roles' English names**: Civilian, Undercover, Mr. White, Spymaster,
  Operative (« les Civilians », « en tant qu’Undercover »). The same test fails if Infiltré,
  Maître-espion or Civil come back anywhere in `fr.json`.
- **Codenames teams have one name everywhere**: `game.codenames.teams.red|blue` (Red / Blue,
  Rouge / Bleue, الأحمر / الأزرق: the plain colour, like the original game; the roles stay the
  game's English names, phonetic in Arabic), always with the team's glyph. Sentences carry the
  word "team" themselves ("the {{team}} team", « l’équipe {{team}} », «الفريق {{team}}»). The stats pages use it too;
  there is no "Red Team" key any more.
- **No game-event toasts, so no `toast.*` keys for them.** The `toast` namespace holds only the
  results of the player's own actions (`youLeftRoom`, `roomCreated`). Starting a game has no
  toast (the game page is the answer; it sat over the game's header), so `gameStarting` is gone.
- **Before pruning a key**, remember the dynamic ones: `t(\`${base}.sample\`)` (home fihrist),
  `errors.api.*` (the backend's `error_key`), `achievements.items.*` / `challenges.items.*` (codes
  from the API). The audit of 2026-10-28 removed 122 dead keys (legacy room, toast, quiz,
  codenames and stats strings); a scan of `t("…")`/`i18nKey`/`*Key:` literals found no reference to a missing key.

## Theme

Samar: one world under two lights. Dark = the night (Maghrib), light = the afternoon (ʿAṣr).
Tokens are OKLCH custom properties in `index.css`, mapped onto the Tailwind names the pages
already use (`bg-background`, `text-muted-foreground`, `bg-primary`…) plus Samar names
(`bg-surface-2`, `border-line-brass`, `text-brass`, `bg-wool-madder`…). `ThemeProvider` sets both
`class="dark|light"` (Tailwind `dark:` variant) and `data-theme` (the tokens) on `<html>`;
`index.html` applies the stored choice before first paint. Full contract: root `DESIGN.md`.

### Follow the sky (the third choice)

`useTheme().theme` is `"light" | "dark" | "system" | "sky"`; read the light on screen with
`useResolvedTheme()`, never from `theme`. "sky" is the afternoon from sunrise to Maghrib and the
night from Maghrib to sunrise, from the stored prayer-times city (`lib/sky-light.ts`, adhan,
Muslim World League). What to keep:

- **It never asks for a place.** No city stored: the device's light, and the theme control
  says so (`nav.skyNote.noCity`). It reads `majlisna-city` / `majlisna-coordinates` again every
  30 s, on a `storage` event and when the tab is shown (the prayer chip stores a city without
  an event in this tab).
- **The pre-paint script cannot run adhan.** ThemeProvider stores the light and a week of turns
  (`majlisna-sky-light`, `{light, turns: [[ms, light], …]}`, written only when it changes) and
  `index.html` walks them; past the last turn it falls back to the device's light. Change the
  record's shape on both sides: `lib/sky-light.test.ts` runs the inline script against
  `lightAt`.
- **The turn is the app's one ceremony** (`withViewTransition` + `:root[data-sky-turn]`, a
  1100 ms root crossfade), only when the sky turned while the page was open: a load, a choice,
  a new city or the device's light change it at once. Never with a game on the table (a
  `/game/` route without `[data-colophon-title]`): it waits for the colophon or the lobby, then
  1100 ms. **A view transition takes every press** (Chrome hit-tests them to `<html>`;
  `pointer-events: none` on `::view-transition` does not help, measured): the turn waits for a
  still page (`SKY_QUIET_MS`, no press, key, wheel or touch for 2 s), and a press ends it at once
  (that press is spent: the player presses again; review RM-4, the ceremony's form is the
  owner's call). Under reduced motion, in a hidden tab or without view transitions: at once.
  Every change of light finishes the colour transitions it starts (`finishLightTransitions`).
- `useResolvedTheme` re-renders its readers in the same task as the change
  (`announceResolvedTheme`, called by ThemeProvider): inside the transition's `flushSync` the
  title and the sky must already be the new ones when the browser captures them.
- Tests: `providers/ThemeProvider.test.tsx` (fake timers over Makkah's real Maghrib),
  `lib/sky-light.test.ts`, `components/layout/__tests__/theme-toggle.test.tsx`,
  `hooks/use-resolved-theme.test.ts`.

The temporary `styles/compat.css` (re-dyed Tailwind palette, neutralised `.glass`,
`.gradient-text`, `.card-hover`, looping `animate-*`, flat gradients, neutral coloured shadows,
borders for raw inputs) is gone: no file used any of it any more, and every page captured in both
lights before and after its removal was pixel-identical (2026-10-28). Do not bring its habits
back: there is no `text-red-500`, `bg-blue-600`, `glass` or `bg-gradient-to-*` in this app, only
the Samar tokens (`text-ember`, `bg-wool-indigo`, `border-line-brass`…). A raw `<input>` gets no
border for free: use `components/ui/field` (`Input`, `Textarea`) or give it `border-line-field`.

## Environment

```env
VITE_API_URL=http://localhost:5111    # Backend API URL
```

Vite dev server proxies `/api` to the backend.

## Hard-Won Rules

### AuthProvider must schedule a token refresh on the cookie path too

`initAuth` tries cookie auth via `GET /me` first. That branch used to set a
`"cookie-auth"` sentinel and `return` — scheduling **no** refresh at all. So any
reloaded tab ran on whatever access token happened to be in localStorage, and once
that expired (15 min in production) the next request 401'd and `client.ts`'s
`afterResponse` hard-redirected the player to `/auth/login` **mid-game**.

Every signed-in load now ends with a refresh **scheduled** (`keepFresh`), never with
nothing scheduled. What to preserve:

- **A token with time left is not refreshed at load, only scheduled** (FP-11): the page
  used to wait for `/me` AND a refresh before its first data request. `setIsLoading(false)`
  comes right after `/me`. Only a token with no recorded expiry (or none at all, a cookie
  session) is refreshed at once, in the background.
- **A refresh with no verdict is retried, the session kept** (FR-3): 429, 5xx, offline or a
  timeout (`RefreshOutcome.status === "unavailable"`) schedules a retry with backoff (5 s
  doubling to 5 min, plus up to 1 s of jitter), never sooner than the server's `Retry-After`,
  which `refreshSession` also honours for every tab (`majlisna-refresh-blocked-until`). Only a
  refusal (a 4xx but 408/429) ends the session. The old code fell to the `"cookie-auth"`
  sentinel with nothing scheduled after a 429, and 15 minutes later the next request wiped a
  still-good refresh token and bounced the player out mid-game. The sentinel survives only for a
  session whose access token is in the cookie alone, always with a refresh scheduled.
- **`useSocket` authenticates the Socket.IO handshake with the localStorage
  token** (`getStoredToken()`), and the backend `connect` handler rejects an
  expired one. A stale token there doesn't just break auth — it silently drops
  real-time and leaves every player on the 2s REST polling fallback.
- A legacy body refresh token that is refused (not revoked) is followed by **one cookie-only**
  try: the backend reads the body before the cookie, so a stale copy shadows a good cookie.
- A revoked session (`errors.api.sessionRevoked`) goes to `/auth/login?redirect=…` with the
  notice `auth.sessionRevoked` (`noteSessionRevoked` → sessionStorage → a toast when the next
  page's AuthProvider mounts), and is never refreshed again.

There is also a `visibilitychange` refresh: `setTimeout` is throttled or frozen in
a backgrounded tab, which is where a party game spends most of its time on mobile.
Tabs follow each other through the `storage` event: a token another tab stored is adopted
and rescheduled (`onTokenStored`), a session another tab ended ends here too
(`onSessionEndedElsewhere`).

### The refresh token is in the httpOnly cookie only; the access token stays readable

`storeAuthData(accessToken, expiresIn, user?)` stores no refresh token, and
`login(accessToken, expiresIn, user?)` takes none (SEC F13): since review INT-06 no response
body carries one — login, refresh and Google sign-in set it as the httpOnly cookie only
(`LoginResponse`, `AccessTokenResponse`, `SocialLoginResponse`). A script, an injected one
included, can read the 15-minute access token but never the 7-day refresh token, not even by
calling `/auth/refresh` itself. The access token stays in localStorage
because the sockets authenticate with it (`getStoredToken()`); a short-lived socket ticket
would remove that too, and is not built yet.

The cookies need `credentials: "include"`, which `client()` sets for every `/api/v1/auth/*`
call (login, Google sign-in, refresh, logout, `/me`) and only those: `ky` defaults to
`"same-origin"`, so a cross-origin `VITE_API_URL` (the E2E stack's `:5049` beside `:3049`,
or `api.majlisna.app`) never stored or sent them. A credentialed cross-origin call needs
an explicit `CORS_ORIGINS` (Starlette answers `*` to a request without a cookie, which the
browser refuses), as the E2E and compose stacks have. Production is same-origin
(`majlisna.app/api`); dev goes through Vite's proxy. Do not depend on the refresh cookie's
`Path`: the server may narrow it.

### `PhaseTimer` fires `onExpired` once per timer window, not per render

The effect keys on `timerStartedAt` + `durationSeconds` and refuses to fire twice
for the same pair (with a 15s re-arm as a liveness valve: a failed call would otherwise
stall the round; any player may report, see `useTimerReport` below).

It used to depend on `[remaining, onExpired]`. `onExpired` is a `useCallback` whose
deps include the React Query mutation object — a **fresh object on every render** —
so any parent re-render re-armed the effect. And the handler calls
`invalidateQueries`, which re-renders the parent: a self-sustaining loop firing a
POST and a server broadcast per cycle, for as long as the phase kept the timer
expired. In Undercover that phase is the whole gap between a round resolving and
the host starting the next one, and each call used to eliminate another player.

The server-side guard (`round_already_resolved`) is the real safety net — see
backend/CLAUDE.md, "An Undercover round resolves exactly ONCE". Both halves stay.

### Who reports an expired timer: `useTimerReport`

Every game page's `onExpired` is `useTimerReport` (`hooks/use-timer-report.ts`, BDP-03). Any
player may still report (gating on the host stalled the game whenever the host's phone
locked), but every clock reaches zero at once, and a 12-player table sent 12 POSTs for one
change, each followed by a refetch.

- **The host reports at once; everyone else waits 1–2 s** (`TIMER_REPORT_JITTER_MIN_MS` /
  `MAX_MS`, a uniform draw) and reports only if the page's `phaseKey` (phase + round + the
  clock's server start) has not moved: the host's report lands, its `game_updated` brings the
  next state, and the waiting reports are dropped. If the host is away, the first wait to end
  reports. A state change that does not end the phase (someone's answer) keeps the wait.
- **No refetch after a no-op answer** (`isTimerNoOpAction`: `paused`, `timer_not_expired`,
  `not_playing`, `round_already_resolved`, `none`); a stop answer (`isTimerStopAction`) still
  silences the window until the next one.
- E2E: a guest's report is 1–2 s late. Poll the server state, never sleep a fixed time.

### A stale access token is refreshed BEFORE `/me`

After an hour away the access token has expired (and the access cookie with it: its
`max_age` is the token's life) while the refresh token is still good — the normal state of a
returning visitor. `initAuth` used to ask `/me` first with the stale bearer; the 401 made
`client.ts` clear the session and send the visitor to `/auth/login`, from any page, the public
`/today` and the home card included, and the refresh never ran. Now:

- `initAuth` refreshes first when the stored token is past (or within `REFRESH_BUFFER_MS` of)
  its expiry, or missing (`accessTokenIsStale`), then asks `/me` with the fresh token and
  schedules from it; a refused refresh clears the session and ends signed out, with no
  redirect; an unanswered one keeps the stored session and retries. A `/me` 401 on a token
  that looked fresh earns one refresh and one more `/me`.
- `client.ts` leaves every 401 from `/api/v1/auth/*` alone (`redirectsToLoginOn401`): no
  refresh, no clearing, no redirect. They are the provider's own probes (and `/auth/login`'s
  wrong password). A protected page then redirects through `_auth.tsx`, with the page in
  `redirect`.

Tests: `AuthProvider.test.tsx` ("refreshes an expired access token before asking /me", "ends
signed out … when an expired session cannot be refreshed"), `api/client.test.ts`
(`redirectsToLoginOn401`), and `e2e/tests/auth/token-management.spec.ts` ("an expired access
token with a valid refresh token stays signed in").

### One refresh at a time, per tab and per browser

`refreshSession()` (`api/client.ts`) returns the pending promise to a concurrent caller:
AuthProvider's timer, `visibilitychange`, and the 401 replay all share it. A concurrent caller
used to get `false`, which read as *failure* and logged the player out while the other
refresh was about to succeed. Overlapping callers are the normal case on mobile: the
throttled `setTimeout` fires at the same moment `visibilitychange` does.

Across tabs it takes a Web Lock (`navigator.locks`, `majlisna-auth-refresh`): every refresh
rotates the cookie (SEC F01, single-use refresh tokens), and tabs scheduled from the same
shared expiry fire together. The second tab waits, finds the first tab's token (stored token
differs from its `staleToken` and is fresh) and asks nothing. A frozen tab holding the lock is
waited for 15 s at most. A browser without Web Locks relies on the server's reuse grace
(`REFRESH_REUSE_GRACE_SECONDS`). A late timer also checks `accessTokenIsFresh()` first and only
reschedules. Tests: `api/client.test.ts` ("two tabs", two module copies over a fake
`navigator.locks`) and `AuthProvider.test.tsx` (two providers, one refresh).

### Token links leave the address bar at once

`/auth/reset-password` and `/auth/verify-email` read `?token=` once (a `useState`
initializer), keep it in memory and call `scrubTokenFromUrl()` (`lib/auth.ts`, a
`history.replaceState` that keeps the router's history state) on mount, so the history, an
analytics page view or a screenshot never holds a working token (SEC F06). Links already
sent keep working. TanStack Router hears the replace (it wraps `replaceState`) and re-renders
with `token: ""`: never read the token from `useSearch` after the first render. A reload can no
longer resend the token, so verify-email offers "Retry" when its request got no answer.
Test: `routes/auth/-tests/wp06-token-links.test.tsx`.

### The client's security rules, in one place (2026-10 audit)

Each is detailed in its own section; each names its test.

- **The refresh token lives only in the httpOnly cookie**, never in localStorage or
  `document.cookie` (`lib/auth.test.ts`, `AuthProvider.test.tsx`, `api/client.test.ts`;
  `e2e/tests/auth/login.spec.ts` reads the real cookie jar).
- **Token and PIN links are scrubbed with `history.replaceState` as soon as they are read**:
  reset and verification tokens (`wp06-token-links.test.tsx`), a share link's code and PIN
  (`/rooms/join`, "`/rooms/join` uses `mutateAsync`" below).
- **Umami runs with `data-exclude-search`**, so no page view carries a query string
  (`src/__tests__/index-html.test.ts`).
- **`script-src` has no `'unsafe-inline'`**; inline scripts pass by build-time hashes ("The CSP
  is enforced").
- **A third-party script loads only on the routes that use it**: Google's GSI only on
  `/auth/login` and `/auth/register` (and inside the open deletion dialog of a Google account),
  never from the root layout ("Google sign-in" below; `i18n/__tests__/detection.test.tsx`,
  `components/auth/__tests__/auth.test.tsx`, `e2e/tests/i18n/regional-locale.spec.ts`). **A
  component that calls a provider's hook must still render when the feature is unconfigured
  and its provider absent** (`WithGoogleOAuth` renders nothing without `VITE_GOOGLE_CLIENT_ID`).
- **A revoked session ends here too** (`errors.api.sessionRevoked` → login with a notice, never
  a refresh; "AuthProvider must schedule a token refresh").

### `UserData` carries only what the API returns

`is_active` and `is_admin` were declared `boolean` here and fabricated at every call
site (`is_admin: false` at login, `updated.is_admin` from a PATCH whose response is
a `UserView`). The backend has never exposed either, so both were permanently
`undefined` behind a `boolean` type. Do not re-add a client-side admin flag:
authorization is decided server-side by `get_current_admin_user`.

### The lobby warns about stale state instead of blanking

The full-page error (`LobbyRefusal`) shows when the room state is in error with no room on
screen; once there is a roster, a failing refetch (`isError` with data) gets a banner
(`room.staleState`) instead — a room that stopped refreshing (kicked, room closed, backend
down) used to leave the player on a frozen lobby with no signal. Deliberately a banner and not
a redirect: replacing a live lobby over one bad poll would be worse than showing stale data.

A refusal with nothing on screen is final (FR-5). TanStack v5 puts a query with no data back
to `pending` at every fetch, so a 404 polled every 2 s and retried twice drew the skeleton
between two error pages forever. Now:

- `retry: retryUnlessRefused` (`components/rooms/errors.ts`): never a 4xx, twice otherwise;
- `refetchInterval` returns `false` while the query is in error with no data (the socket's
  state reaches it through `socketConnectedRef`, read after each render; all of it lives in
  `useRoomLobby`, `hooks/use-room-lobby.ts`);
- the refusal is held in a ref while it is asked again (a refocus), so no skeleton in between;
- for `errors.api.userNotInRoom` the page offers "Join this room" (code and PIN, through
  `useJoinRoom`), and keeps its socket closed until then: the server refuses a non-member's
  socket, and socket.io-client never retries a refused one.

Tests: `routes/_auth/rooms/-tests/lobby.test.tsx` (fake timers: 10 s with one request and no
skeleton). Route tests sit in a `-tests` folder: the router plugin ignores names starting with `-`.

### A failed read is not an empty state

Every data page branches on `isError` before its empty state (FR-7): during an incident
`/stats` said "No games played", `/achievements` "No achievements yet", `/leaderboard` "No
players yet", `/friends` "My friends 0", the profile kept its skeleton forever and a player page
answered a 500 with "We could not find this player". Now they show `LoadFailed`
(`components/stats/LoadFailed.tsx`: an error `Alert` with `getApiErrorMessage(err,
t("common.loadFailed"))` and a `common.retry` button calling `refetch()`), as the notebook and
the word of the day do.

- `/stats` fails as a whole when either of its two reads fails (a missing game list would read
  as "no recent games"); `/friends` per list, and a tab's count shows only once it is known.
- The player page says "not found" only for a 404 or a 422 (an id that is not one); anything
  else is `LoadFailed`.
- The leaderboard's E2E hooks: `data-testid="leaderboard"` on the table (loading, empty or
  filled; never on a failure), `leaderboard-row` on each player's row, `leaderboard-error` on the failure.
- When you add a page that reads, give it the same branch. Test: `routes/-tests/error-states.test.tsx`
  (every read answers 500: the alert and Retry, never the empty copy).

### Text on a 10% tint uses the `-on-tint` tokens

`text-primary` on `bg-primary/10` measured **3.56:1** at 12px and
`text-destructive` on `bg-destructive/10` measured **4.09:1** — both under the 4.5:1
AA floor for small text. `--primary-on-tint` / `--destructive-on-tint` exist for that
pairing only, so buttons, icons and headings keep the brand colours. They are
*darker* in light mode and *lighter* in dark mode: the tint composites over opposite
backgrounds.

This is also a lesson about the accessibility suite. The axe scan runs right after
`domcontentloaded`, and axe skips a node that is momentarily `opacity: 0`: when this was
found the cards still faded in on load, so whether the chips got measured at all depended
on machine speed. Three clean local gate runs missed it; CI caught it. (The pages no longer
animate anything at load — the 2026-10 audit counted 0 app animations on 18 routes, the
word of the day's hint ink aside — but a fade added later would bring the trap back.) The
deterministic guard is `e2e/tests/accessibility/contrast.spec.ts`, which waits for any
animation to settle and composites the translucent tint the way a browser does. When adding a
chip-style label, keep it above 4.5:1 or make the text large enough to qualify for
the 3:1 large-text threshold.

### The CSP is enforced

`security-headers.conf` ships `Content-Security-Policy`, not `-Report-Only`. Two things
made that possible:

**The unknown hosts are no longer unknown.** The Umami, Sentry and **API** origins are
substituted into the policy by the frontend Dockerfile's production stage, from the
same build args the bundle is compiled with — so the allowlist cannot drift from what
the bundle talks to. Only the origin is taken from the Sentry DSN; its key never
reaches a response header. An unset arg substitutes to nothing, which is valid.

The API origin is **not** redundant with `'self'`: `'self'` is scheme + host + *port*,
so `api.majlisna.app` (documented as supported) or the E2E stack's `:5049` next to the
frontend's `:3049` is a different origin. Without it an enforced policy blocks every
API call. The E2E suite is what found that. Its WebSocket twin (`wss://` for https,
`ws://` for http, same host and port) is substituted next to it, for the invitation
socket in `_auth.tsx`; there is no blanket `ws: wss:` (SEC F13). The room socket
connects to the page's own origin, which `'self'` covers.

**`script-src` has no `'unsafe-inline'`: the inline scripts are allowed by hash.** The
Dockerfile's build stage runs `scripts/csp-inline-hashes.mjs` on the BUILT
`dist/index.html` (Vite rewrites the Umami bootstrap from the build args, so only the
built bytes hash right) and the production stage substitutes one `'sha256-…'` per inline
`<script>`. So editing or adding an inline script in `index.html` needs no CSP edit, but
an inline event handler (`onload="…"`) or a `javascript:` URL **fails the build**: no
hash can allow them, so attach listeners from a script. `style-src` keeps
`'unsafe-inline'` (React inline styles). The Dockerfile also refuses a policy with a
leftover placeholder, an `'unsafe-inline'` in `script-src`, or a bare `ws:`/`wss:`.

**A new inline script is allowed only by a rebuilt image.** The hashes come from the built
`dist/index.html` at image build, so never hand-edit a hash into the policy; rebuild, and keep
`e2e/tests/smoke/csp.spec.ts` clean. `scripts/csp-inline-hashes.test.mjs` pins the hashing
(and the refusal of inline handlers and `javascript:` URLs).

`e2e/tests/smoke/csp.spec.ts` fails on any enforced violation and reports
`sourceFile`/`line`, so the next one names itself. It collects violations over
`console`, never `page.evaluate` — Playwright evaluates in the main world, which
Chromium subjects to CSP, so reading results that way reports an `eval` violation of
the harness's own making.

### The Word Quiz hint ladder arrives one rung at a time

`state.hints` is a **prefix**, not the whole ladder: the server sends only the
hints it has actually released. It used to send all six at round start "so the
client can control display timing locally", which meant the most specific hint was
in the very first response — and the score for a correct answer is
`max_hints - hint_number + 1` computed from elapsed *server* time. Opening the
network tab paid full marks at t=0.

Three consequences for this page:

- **`maxHints` comes from `state.max_hints`**, never from `state.hints.length`.
  Inferring it off a prefix makes "hint 2/6" read "2/2".
- **The local clock is clamped to what we hold** (`Math.min(localHintsRevealed,
  state.hints.length)`), because it can run a beat ahead of the fetch.
- **Crossing a rung we don't hold triggers an `invalidateQueries`.** There is no
  Socket.IO event for a hint — nothing mutates — and polling is off while the
  socket is connected, so this effect is the only thing that pulls the next one in.
- **The ladder's clock is one timeout set for its next change, never polled** (WP-26,
  `hooks/use-wordquiz-game.ts`): `hintClockAt(elapsedMs, rules)` is the server's rule
  (`_calculate_hints_revealed`; an interval of 0 releases the whole ladder) and
  `msUntilHintClockChanges` says when it next answers something else (the next second of
  "next hint in", else the next rung), in integer milliseconds on `serverNow()`. A 500 ms
  `setInterval` used to re-render the whole page twice a second and land a rung up to
  half a second late; a rung now lands at `round_started_at + N × interval`. The thread
  clock itself is `PhaseTimer` → `ThreadClock` (`startedAt` + `durationMs`, WP-18).
  Tests: `hooks/use-wordquiz-game.test.ts`, `routes/_auth/game/-tests/wp26-wordquiz-page.test.tsx`.
- **The field counts the round's tries** (owner rule (e)): `AnswerInput` takes
  `attemptsLeft` (`my_attempts_left`; null shows nothing) and `maxAttempts`, says
  `game.wordQuiz.triesLeft` under the field (read with it), and closes at 0; the last miss
  then reads `errors.api.answerAttemptsExhausted`, not "try again", and focus moves to the
  count instead of falling to `<body>`. A 409 `answerAttemptsExhausted` comes back from
  `handleSubmitAnswer` as `{ refused: <translated> }`, which the field says in its alert
  (no toast), and the state is re-read. "Worth N points now" is `kalimatWorth(max, rung,
  my_rungs_lost)`, the server's price, shown only while the player can still earn it: not once
  they found the word, nor at 0 tries left (review F5). Tests:
  `components/games/wordquiz/wp26-tries-left.test.tsx`, `routes/_auth/game/-tests/wp26-wordquiz-page.test.tsx`.
- **A password-only form says a wrong password as one** (`components/profile/password-error`):
  the delete-account dialog and the password change map the login's
  `errors.api.invalidCredentials` ("check your email and password") to `profile.wrongPassword`
  (review F6).

### Vote targets are not in the payload while a round is open

`serverState.votes` blanks every target but the caller's own until the round
resolves, and `vote_history` omits the round in progress. `deriveVotedPlayers`
only takes the dict's keys, so the UI is unaffected — but do not start rendering
`votes[playerId]` as a target during the voting phase and assume it is there.

### Fonts are bundled, never fetched from a CDN

Every face comes from `@fontsource` through `src/fonts.ts` (Readex Pro, Reem Kufi, Marcellus,
Amiri, Aref Ruqaa), so the enforced CSP's `style-src`/`font-src` stay `'self'` (+ `data:`) and no
visitor IP goes to Google. The per-script `unicode-range` subsets mean a page only downloads the
scripts it renders. A `Samar Figures` face (Readex digits only) sits first in the display stack
because Marcellus's 1 reads as an I. Do not add `<link>`s to a font host: the policy blocks them.

Three things keep a page to the files it needs (FP-13). `src/fonts.css`, imported by `fonts.ts`
AFTER the @fontsource CSS, declares two small faces over theirs (a later face of the family is
tried first for the characters of its `unicode-range`): Readex's transliteration letters (ā ī ū ḥ
ṣ ḍ ṭ ẓ ʾ ʿ…, 5 kB, instead of the 28 kB latin-ext file one "salām" pulled), and Amiri's space and
no-break space (inlined, instead of the 20 kB Latin file every Arabic phrase with a space pulled).
Latin text IS set in Amiri (MCQ explanations, meanings, Latin answers): never give Amiri's Arabic
face the space, or a Latin paragraph would pull the 100 kB Arabic file. And a Vite plugin
(`preloadUiFont`, `vite.config.ts`) preloads Readex's Latin file, which every page needs, from the
built `index.html`. The subset files are in `src/assets/fonts/` (how they were cut:
`SOURCES.txt`); a subset with no outline at all is rejected by Chrome's sanitizer and fails
silently, which `src/fonts-subsets.test.ts` guards with the copy's letters. The Arabic UI still
fetches Amiri's Latin file for the full stop that ends its titles.

### The display figures are pinned to the weight of the letters around them

`Samar Figures` used to declare Readex's whole 160–700 range, so a Marcellus title (400) drew its
digits at Readex 400 and "Bilalbd1 wins!" had a bold 1 (an Arabic title, 700, even bolder).
`fonts.ts` now registers it with ONE weight, `DISPLAY_FIGURES_WEIGHT` = 280 (Marcellus's stem): a
single-value descriptor clamps the variable `wght` axis to it whatever the title asks for
(`fonts.test.ts`). One weight in every language on purpose: digits in a title sit in a Latin run
(a username, "Players (5)") set in Marcellus, also in Arabic titles; a heavier face for Arabic's
700 was tried and drew "مجلس PolJf746" with a bold 746 beside a light PolJf. And because Chrome
fakes a bold for a 700 request on a face lighter than 600, everything in the display stack sets
`font-synthesis-weight: none` (h1/h2, the `type-*` roles, and `.font-display` in index.css).

### The home sky: the `<picture>` and the preload in `index.html` are one contract

`HomeHero.tsx` draws one sky per light from `public/sky/` (≤ 760 px: 800/1000 w, 761–1100 px:
the 2:1 tab crop at 800/1200/1600 w, above: 1600/2400 w, `sizes="100vw"` except the tablet
range: `TABLET_SKY_SIZES`, because in portrait the cover box is drawn wider than the viewport,
so a 768 × 1024 iPad at DPR 1 takes tab1200, 95 kB, not the 215 kB tab1600 it used to, nor a
stretched tab800). The inline script in `index.html`
preloads the same file for the stored light on `/`, with the same `imagesrcset`, `imagesizes`
and media queries, so the browser downloads exactly one sky. Change one, change the other
(and check the network panel: one `/sky/` request per load);
`components/home/__tests__/home-sky.test.tsx` runs the inline script and compares. The sky files' bottom edge is the
horizon and the CSS ground starts on their last row: never crop or re-export them without the
ground colours in `public/sky/SOURCES.txt`.

For "Follow the sky" the script preloads the light the stored turns give (the device's when
there are none). The other light's sky is fetched by `useSkyWarmUp` (HomeHero) 10 min before a
turn, after `load`, at low priority, through `warmSky`: the picture's own range, candidates and
sizes for this width (`skyRanges`, shared with `HomeSky`), so the turn requests nothing. Never at
load: the load's one `/sky/` request stays the current light's.

### `_auth.tsx` must not re-navigate from the login page

The auth gate navigates to `/auth/login?redirect=<where you were>`. The layout stays mounted
while the router moves, so the effect ran again with `location` = the login URL and navigated
a second time with `redirect=/auth/login?...`, which `safeRedirect` drops: every redirect was
lost (a shared `/rooms/join?code=…&pin=…` link, or the home join row, then landed on `/`). The
effect now skips paths under `/auth/`.

Note: `vite.config.ts` no longer drops every `console.*` (`esbuild.drop` used to, in dev
too, so a debugging `console.log` printed nothing and every `console.warn`/`console.error`
vanished in production). Now `esbuild.pure: ['console.log', 'console.debug']`: the minifier
removes those two from the production bundle, they still print in dev, and `console.warn` /
`console.error` ship (the "No retries" rule's visible warnings need them).

### Errors reach the tracker (`lib/report-error.ts`)

- **One door**: `reportError(error, { source, extra })` says the error in the console and
  sends it through the Sentry SDK to the self-hosted, Sentry-compatible tracker (Bugsink on
  the host, project `majlisna-front`; production builds get its DSN as the `VITE_SENTRY_DSN`
  build arg since 2 November 2026, root CLAUDE.md "Monitoring tools"). Callers: `ErrorBoundary`, and
  `QueryProvider`'s `QueryCache`/`MutationCache` `onError`, which skip a 4xx
  (`isReportableRequestError`: the server's verdict, said on the page). A network failure
  or a 5xx is reported.
- **The SDK is lazy**: `startErrorReporting({ dsn })` (main.tsx) imports `@sentry/react`
  after `load`, when the page is idle (`requestIdleCallback`, a 1.5 s timer without it), and
  only when the build has `VITE_SENTRY_DSN`. Until then reports, `window` errors and
  unhandled rejections wait in a queue (`MAX_QUEUED_REPORTS`); then the SDK's own handlers
  take over. Without a DSN nothing is downloaded. Never import `@sentry/react` statically:
  `check:bundle` fails if the SDK lands in the entry.
- **Every event carries the release, the deployed commit** (3 November 2026):
  `startErrorReporting({ dsn, release: readRelease() })`. `readRelease` reads index.html's
  `<meta name="majlisna-release">` and answers only 40 lowercase hex digits (else undefined,
  and `init` gets no `release`). index.html ships `content="unknown"`; the image's LAST step
  (`front/Dockerfile`) stamps the commit with `scripts/build-commit.sh` (the `GIT_SHA` build
  arg, else Dokploy's clone through the `gitmeta` named context, else `unknown`) and rewrites
  `index.html.gz`. Not a `VITE_*` variable on purpose: that would rebuild the whole bundle on
  every commit, backend-only ones included; the stamp step reruns alone. Tests:
  `lib/report-error.test.ts`, `src/__tests__/index-html.test.ts`, and
  `backend/tests/api/test_build_commit.py` for the script and the Dockerfile step.
- **`ErrorBoundary` resets when the page changes** (FR-10). The exported component reads the
  router's *resolved* location (`useRouterState`), not `useLocation`: the address changes
  before the new page's matches render, so a reset on it drew the crashed page again and
  stayed on the error. A test that mocks `@tanstack/react-router` and renders a page with a
  boundary must give the mock `useRouterState`. A chunk that failed to load
  (`isChunkLoadError`) makes "Try again" reload the tab once per error message
  (sessionStorage `majlisna-chunk-reload`): a rejected lazy import is never retried in place.
  The technical message sits under a "Technical details" toggle (`ui.errorDetails`).
  Tests: `components/__tests__/ErrorBoundary.test.tsx` (a real memory router),
  `providers/QueryProvider.test.tsx`, `lib/report-error.test.ts`.

### The bundle diet (`bun run check:bundle`)

After `bun run build`, `scripts/check-bundle.mjs` fails when the entry chunk holds zod (or
`jitless`) or the Sentry SDK, or weighs 60 kB gzip or more (22 kB when it was set, from
77.7 kB). The frontend CI job runs it after the build (`pipeline.yml`, wired by WP-15).

- **No Kubb zod schemas** (FP-02): the barrel re-exported ~250 of them into the entry of every
  page and nothing used them. `kubb.config.ts` has no `pluginZod`.
- **`manualChunks`** (`vite.config.ts`): `react-vendor` is exactly react, react-dom and
  scheduler (a bare `'/react-dom/'` also caught `@floating-ui/react-dom`); there is **no
  Radix rule** (it preloaded Select, Tabs, Progress and Switch on every page; each now goes
  with its route); whatever else the shell imports statically from the entry (the nav's
  Radix pieces, sonner, ky, tailwind-merge…) goes to `vendor`, which stays cached across a
  deploy that only changes app code. Stylesheets are never chunked by hand.
- **No chart library**: `/stats`'s `WinLossChart` is plain elements on the Samar tokens
  (a few kB; chart.js was 52 kB gzip). Bars carry `data-day`, segments `data-part`.
- Radix is deduplicated (one release line, no nested copies in `bun.lock`).

### `PhaseTimer` renders the thread clock, never red

`PhaseTimer` keeps its props and its once-per-window `onExpired` logic; it renders
`components/brand/ThreadClock` (a woven thread drawn back through the loom, five brass lozenges for
the last five seconds, a knot at zero). Urgency is a change of rhythm, not colour: no red, no pulse. Its
`aria-label` names the clock and gives its text ("Time left: 0:20", `ui.clock.label`); a polite
live region speaks only at 30, 10 and 5 s.

**The thread never animates `width`** (WP-18). It used to: a 500 ms width transition on a
one-second tick, so it moved half of each second and stood still the other half, and laid the
page out every frame it moved (308 layouts in 5 s on a phone, against 5 now). The thread is
full length inside an `overflow: hidden` track; `PhaseTimer` passes `startedAt` +
`durationMs` and `ThreadClock` runs ONE `Element.animate` on `transform: translateX` per timer
window (positive in RTL), from where the thread stands now to five seconds left, linear, on the
compositor. The 500 ms tick changes only the figures. Under reduced motion (or with only
`remaining`/`total`, as in the pause veil) the CSS places the thread from `--left`, once a
second. Tests: `components/brand/__tests__/ThreadClock.test.tsx` (a recording fake of
`Element.animate`: happy-dom has no Web Animations).

### Motion rules (DESIGN.md §7)

- **A continuous animation moves `transform` and `opacity` only**, never `width`, `height`,
  `left` or a `clip-path` in a loop (the `ink` mask on text is the one authored exception). The
  thread clock is ONE Web Animation on `transform` per timer window. Tests:
  `ThreadClock.test.tsx`, `e2e/tests/perf/thread-clock.spec.ts` (one `thread-clock` animation,
  no width animation, under 20 layouts in a 5 s trace).
- **A word written on the compositor is a pen and its ink, translated against each other**
  (the Codenames clue, `ClueBanner`, DESIGN.md §7): the `ink` utility animates a registered
  custom property inside a mask, which Chrome reports as non-composited and repaints every
  frame. The pen (`.cn-clue-pen`) carries a static soft-edged mask and the room for swashes and
  harakat as negative margins its ink pads back, so the word lays out exactly as without them;
  the two `Element.animate` calls share duration and easing. Any box the script moves keeps an
  identity `transform` at rest (gaining or losing one re-lays its line out), and the banner
  clips its inline axis so a travelling pen never makes the page scroll. Write only on a NEW
  value, judged by a ref of the last one shown, never on mount. Tests:
  `codenames/ClueBanner.motion.test.tsx` (a recording fake of `Element.animate`),
  `codenames/__tests__/codenames-motion.test.ts`.
- **A gesture triggered by a server change plays only when the change happens on screen.**
  Compare with the state the component last drew (a `useState` of the previous phase, as
  `ChoiceButtons` does for its reveal, or a ref of the last totals, as `PlayerScoreboard`
  does): a page load, a reload, a refetch or a socket push of the same state replays nothing.
  A WAAPI animation that waits (a stagger, a delay) takes `fill: "backwards"`, never
  `forwards`: the CSS holds the end, and nothing lingers in `getAnimations()`. Do not animate
  a thread with nothing to show (a share of 0): Chrome refuses to composite an animation with
  no visible change.
- **A gesture on a component that cannot see the previous phase asks who was on screen.** The
  Undercover verdict turns its tablet over only when the vote resolved in front of the player:
  `RoundOverPanel` reads `tableIsOnScreen()` (`games/undercover/table-witness.ts`) in a lazy
  state initializer, i.e. whether a `DescriptionList` is still mounted while the verdict first
  renders. The page swaps phases in one commit, so that list unmounts in the very commit the
  verdict arrives; a page loaded on the verdict, a refetch and Mr. White's guess have none. The
  rule is `verdictTurnNow()` (same file), read the same way by `MrWhiteGuessPanel`, whose
  compact verdict turns when the vote finds Mr. White on screen.
  The turn is CSS on `.uc-verdict[data-turn]` (pseudo-element layers: a warp cover clipped by
  the role chip and the face, the role band's pattern clipped by the band), `data-word` when
  the face shows a word (the cover then only fades: a word may be a sacred name). Tests:
  `undercover/__tests__/verdict-turn.test.tsx`.
- **ERASE is opacity, ending on the CSS's receded state** (`hooks/use-seat-erase.ts`): a list
  renders an emptied seat receded itself (`data-out` / `data-away`: name at `--erase-ink` .72,
  the muted token's contrast, lozenge at `--erase-mark` .45), and `useSeatErase(rootRef,
  seats, quiet)` animates only a seat that changed since the last render (`[data-seat]`,
  parts `[data-erase="ink|mark|note"]`), never on the first. An opacity cannot end on another
  colour, so a receded name stays `--text` under the opacity; a muted colour inside it would
  fall below 4.5:1. `quiet` records without playing (the vote's list once the vote is
  complete: under the view transition the page draws it one more frame with the resolved
  state, and the verdict tells that seat). Tests: `undercover/__tests__/erase.test.tsx`,
  `rooms/__tests__/PlayerRoster.erase.test.tsx`.
- **After every phase swap and every game over, focus moves to the new phase's heading when
  focus was free** (on `<body>`, or on a control of the game region that is not a field being
  typed in): `usePhaseFocus` ("Game pages" below). Tests: `hooks/use-phase-focus.test.ts`,
  `e2e/tests/accessibility/phase-focus.spec.ts`.
- **Under reduced motion a phase change keeps a 120 ms crossfade, never a cut** (index.css:
  `::view-transition-old/new(root)` at 120 ms, groups at 0 s); the other gestures become short
  fades in the CSS twins, the clock steps once a second. Reduced motion is the CSS's job:
  nothing animates through motion/react (the `motion` package is still in `package.json`, but
  nothing imports it), and there is no `MotionConfig`. Tests: `lib/view-transition.test.ts`,
  `components/brand/__tests__/Seal.test.tsx`, `lib/motion.test.ts`.
- **The home's kashida is woven once per session** (`Wordmark weave`, HomeHero only): one Web
  Animation on the `.k-band`'s `transform`, held at its first frame (the band out of its clip)
  from the first commit and played once the wordmark's face is loaded (3 s at most). The
  session flag (`majlisna-kashida-woven`) is taken at the first commit and kept in a ref across
  StrictMode's effect re-run; a storage that cannot be read weaves nothing. Under reduced
  motion nothing moves. Test: `components/brand/__tests__/Wordmark.test.tsx` (a recording fake
  of `Element.animate` and of `document.fonts`).
- **Nothing sweeps, strikes or wipes across a sacred name: it fades.** One list,
  `holdsSacredName` (`lib/sacred-names.ts`): the samar riddle's line and the Codenames clue (free
  text from the spymaster) fade instead of being written when they hold a name of Allah, the
  Prophet ﷺ, a prophet, Jibril, the Qur'an or the Kaaba. A new gesture that passes over a text
  asks it too. Tests: `lib/sacred-names.test.ts`, `codenames/ClueBanner.motion.test.tsx`.
- **A CSS gesture's direction is a custom property, never a second `animation-name`.**
  `[dir="rtl"]` sets the value (`--tally-from`, `--uc-to-reading-end`), one `@keyframes` reads
  it: a swapped name is a new animation, so a language switch replayed the gesture (review RM-9).
- **A moved box rests on an identity transform**, an animated opacity on a box of its own:
  gaining or losing a transform (or an inline gaining a layer) lays the line out again at the
  animation's end (the clue's pen, the scoreboard's rows and its gain, `inline-block`).
- **A change of light finishes the transitions it starts** (`ThemeProvider`
  `finishLightTransitions`, twice: in the task, then a microtask after React's re-render of the
  light's readers): every `transition-colors` on the page would otherwise fade from the old
  light, off the compositor. Test: `providers/ThemeProvider.test.tsx`.
- **A long view transition must not take a press.** Chrome sends every pointer event to
  `<html>` while one runs. The phase crossfades stay at 180 ms; the sky's 1100 ms ceremony
  waits for a still page and ends on a press (ThemeProvider, "Follow the sky" above).

### Nothing clips the page sideways

`body` used to carry `overflow-x: clip`. It propagates to the viewport, so anything wider than
the screen was simply cut off and unreachable: at 390 px the lobby's fourth game button ("The
Quiz", "مسائل" in Arabic) was off-screen and a host on a phone could not pick it. It is gone. Make
content fit instead (the picker is 2 × 2 on phones), let the home hero clip its own sky
(`.home-hero`), and never start an entrance off to the side: in RTL a block waiting at `x: -20`
lies past the start edge, and negative overflow is scrollable there, so the whole page slides.
Check with `scrollWidth - clientWidth` at 390 px in EN and AR (a clip hides the overflow from
`getBoundingClientRect` sweeps, never from `scrollWidth`).

### The menu sheet opens from a Radix trigger

`MainNav`'s "Menu" button is a `SheetTrigger asChild`, not a Button with its own `onClick`:
without the trigger Radix has nothing to hand focus back to, and Escape or Close left keyboard
focus on `<body>`. On open, focus goes to the first page link (Radix's own auto-focus skips links
and landed on the prayer chip).

### `/rooms/join` uses `mutateAsync`

Per-call `mutate(vars, { onSuccess })` callbacks belong to the mutation observer, which
StrictMode's mount/unmount/mount replaces in development: the join succeeded on the server and
the page sat on "Joining room…". The promise from `mutateAsync` always settles.

- **The code and PIN leave the address bar at once.** The page reads them once (a `useState`
  initializer), then `history.replaceState` drops them, keeping the router's history state,
  before the join is sent: the PIN used to stay in the browser history and in every analytics
  page view (SEC F06).
- **The code arrives as the link wrote it.** A share link is written by hand, so nothing quotes
  its values, and the router's default parser (JSON) read a code like 3E182 as the number
  3e+182 (about one room in 2,000: digits, E, digits): the link opened no room. The router's
  `parseSearch` (`lib/search-params.ts`, set in `main.tsx`) keeps any number that would not
  come back as written as its text; what the router writes itself reads back as before.
- **One room at a time.** A player seated in another room gets a 409
  (`errors.api.userAlreadyInRoom`): the page says `room.joinPage.alreadyInRoom` and offers
  "Leave {{room}} and join" (`components/rooms/use-join-room.ts`, shared with the lobby's
  "Join this room"). The button reads `/rooms/active` again when pressed, leaves that room
  through the normal leave, then joins.
- **A ban is said, and that is all.** A 403 `errors.api.roomBanned` shows its translated
  message: no retry, no leave offer (leaving another room does not lift it), no repair line
  and no "Type the code yourself" — only "Back to the majlis"; the /rooms form drops its
  "Check the code and PIN with your host" for a ban and a seat elsewhere (review F2). One
  rule picks the repair: `components/rooms/errors.joinRepairFor(errorKey)` (`useJoinRoom`
  exposes `errorKey`).
- **A refused PIN may be an old one.** Every ban rotates the PIN (a kick does not), and a share link keeps the
  PIN it was made with: `errors.api.wrongRoomPassword` is followed by
  `room.joinPage.pinChangedRepair` ("ask the host for a new link or invite", review F1). A
  friend's invite no longer goes through this page: it is stored on the server and accepted
  by id, without the PIN ("Friend invites" below).
- **Friend invites** (`components/rooms/RoomInviteStrip.tsx`, `use-room-invites.ts`,
  `useAcceptInvite` in `use-join-room.ts`). The strip accepts the invite itself (`POST
  /rooms/invites/{id}/accept`, no code, no PIN in any URL), then the shell opens the lobby. A
  refusal that holds is said on the strip in the server's words (403 `roomBanned`, 410
  `roomInviteExpired`, 404 `roomInviteNotFound` — spent, or deleted by a ban of its sender or of the caller — 404
  `roomNotFound`, `data-testid="room-invite-error"`) and then only Close is offered: that list
  is `errors.isFinalInviteRefusal`, an allow-list, because every error answer carries an
  `error_key`, a 429 or a 500 too, and Close hides the invite for good (review F3); 409
  `userAlreadyInRoom` offers "Leave {{room}} and join" (the same `useSeatRequest` as the join
  page); any other failure (429, 5xx, no answer) is said and keeps Join. The shell shows the
  latest pushed invite (`room_invite` = `RoomInviteView`), else the newest of `GET
  /rooms/invites` (keyed by viewer; re-read after the personal socket reconnects). An
  answered invite (Not now, Close, seated) is remembered by id with its `expires_at`: a
  re-invite keeps the id and moves the expiry, so it shows again. The strip is keyed by
  `id@expires_at`, so a new invite starts with a fresh Join.
- **`useJoinRoom` tracks its own in-flight join** (`busy`), never `joinMutation.isPending`:
  StrictMode's mount, unmount, mount detaches the mutation observer of the join sent at
  mount, and the "Leave {{room}} and join" offer stayed busy for ever under `bun dev`
  (review F8; `join.test.tsx` renders it in `<StrictMode>`).

### Credits

`routes/credits.tsx` carries the attribution the CC BY-SA images need (the home skies and
`og-image.jpg`, CC BY-SA 4.0; the Jabreen arch, CC BY-SA 2.0). It is linked from the footer on
every page. A new third-party image ships only with its entry there.

### Privacy

`routes/privacy.tsx` is a Read page on the About rails (`components/about/rails.ts`): section
titles at the start, the text at a reading measure. Its text is `privacy.sections` (`{ title,
body[] }`, the same number of sections and paragraphs in the three locales: the parity test walks
arrays): one paragraph reads as a paragraph, several as a list behind brass lozenges. Strings may
carry `<b>` (an item's lead term) and `<profile>` (link to /profile). Test:
`components/about/__tests__/privacy-page.test.tsx` (every section of each locale is rendered).
The page is `components/about/LegalPage` (`ns="privacy"`), shared with the terms of use; under
its contact line, `privacy.seeTerms` links /terms.

The policy describes the code as it is (checked 2026-10-28), so **a change to any flow it names
changes its text**, in the three languages, with a new "updated" date:

- prayer times: computed on the device (adhan); the nav calls `https://ipapi.co/json/`
  automatically while no city is stored, at every width (one request per load, shared with a
  mounted chip; a failure is remembered for 24 h in `majlisna-geo-failed-at`); city search →
  Open-Meteo geocoding (with the interface language); a chosen city → Open-Meteo for its time
  zone; "Use my location" (on request) → Nominatim (Accept-Language: the interface language) +
  Open-Meteo; the city
  lives in localStorage only (`majlisna-city`, `majlisna-coordinates`);
- browser storage: the access token (never the refresh token, which stays in its cookie) and
  `majlisna-user-data` in localStorage beside the httpOnly cookies, theme, language, the
  welcome flag, per-tab sessionStorage during a game; for "Follow the sky", the week of turns
  computed on the device (`majlisna-sky-light`); per tab, whether the home's name has been
  woven (`majlisna-kashida-woven`) and the samar riddle on screen in a room, in its lobby as in
  a game (`majlisna-riddle:<room>:<scope>`, `privacy.sections[3].body[2]`);
- Google: sign-in only; Google's script loads on the sign-in and sign-up pages (the
  provider is mounted by `GoogleLoginButton`, see "Google sign-in" below) and in the open
  deletion dialog and password form of a Google account, where it confirms the deletion or the
  new password, and profile pictures come from Google's servers (`privacy.sections[6].body[0]`);
  a Google-created account has no password until it sets one, confirmed with Google, then signs
  in either way (`privacy.sections[0].body[1]`); deletion is confirmed with the password or with
  Google (`privacy.sections[8].body[0]`), so Google accounts no longer write in to delete;
- Umami events carry no identifier, and page views no query string (`data-exclude-search` in
  index.html's bootstrap: the URLs carry reset and verification tokens and a room's code and
  PIN, SEC F06); error reports go only to the self-hosted error tracker,
  once one is configured (`VITE_SENTRY_DSN`, for the Bugsink on the host; there is no
  GlitchTip, corrected 2026-10-30);
  Resend, Cloudflare, Oracle Cloud;
- what other players see (public stats, achievements and leaderboard; the public profile, i.e.
  the username, the bio and the games played, for anyone, signed in or not: `GET
  /profiles/users/{id}` takes no token and `routes/players/$userId.tsx` is outside `_auth`; the
  country and the picture for signed-in players only, `GET /users/{id}`;
  `privacy.sections[4].body[0]`, corrected 2026-11-07: it said signed-in players only), the
  notebook, the word of the day, chat, and what account deletion removes (and that past games
  keep the name a player played under).

### Terms of use

`routes/terms.tsx` (owner request, 3 November 2026) is the same Read page as the privacy policy:
`<LegalPage ns="terms" />`, text in `terms.*` (`title`, `updated`, `intro`, `sections`,
`contact`), marks `<b>`, `<profile>`, `<privacy>`, `<terms>` (`LegalText`, with
`shouldUnescape`: Trans turns a "<" that opens no known mark into "&lt;", and the username rule
lists `@ / \ < >`). Linked from the footer (right after the privacy policy), from the privacy
page, and from the sign-up page: `auth.acceptTerms`, one sentence under the form and the Google
button ("By creating an account, you accept the terms of use and the privacy policy"), no
checkbox. The document title is `terms.title` (`lib/route-title`).

The terms state only what the code and PRODUCT.md hold, so **a change to one of these changes
them**, in the three languages, with a new "updated" date: the password minimum and the
username rules (`components/auth/validation`; the test reads its constants), the host's Remove
and Ban (the only moderation tools), what the `ADMIN_EMAILS` access covers (game content:
words, word packs, challenges; nothing that suspends an account), what account deletion
removes (the same list as `privacy.sections[8]`), who sees the username and the bio (anyone, as
in `privacy.sections[4]`: `terms.sections[5]`), and the religious-content line (not a fatwa,
**not** reviewed by scholars: never claim a review). No governing law, jurisdiction, minimum
age, company, address, liability cap or arbitration until the owner decides them
(`terms-page.test.tsx` fails on those words in English). Tests:
`components/about/__tests__/terms-page.test.tsx`, `routes/auth/-tests/register-terms.test.tsx`,
the footer and privacy-page tests.

### `/auth/me` says `email_address`, `UserData` says `email`

The cookie path of `initAuth` cast `GET /auth/me` (a `UserView`) straight to `UserData`, so after
any reload `user.email` was `undefined` and the profile showed no address. It goes through
`userFromView()` now (`AuthProvider.tsx`, tested). Login and register answer `user.email`; only
`/me` (and the `PATCH /users/me` view) uses `email_address`.

### Game pages: what the reviewers made us write down

- **A game that is gone is detected by its status, never by its message.** `isGameGoneError`
  (`components/games/shared/game-errors.ts`) answers on 404/410 and the server's *untranslated*
  `message`. `getApiErrorMessage` translates through `error_key`, so a "not found" test on the text
  the player sees never matched in Arabic or French and the redirect home never happened. All four
  games use it (Undercover was the last to test the translated text).
- **A kicked or banned player leaves the game page too.** The four game pages pass `onKicked:
  useLeaveAfterKick()` to `useSocket` (`hooks/use-leave-after-kick.ts`, the lobby's behaviour):
  `you_were_kicked` is `{room_id, banned}`, `onKicked(roomId, banned)` notes the `room-notice`
  ("kicked" or "banned", `lib/room-notice.ts`) and goes to /rooms. A removed player is out of the
  room's socket rooms, so no `game_updated` reaches them: without it they sat on a frozen game,
  still seated. The lobby's polling fallback (the seat gone from the state, no event) notes
  "removed" (`room.youWereRemoved`, "the host removed you"): it cannot tell a kick from a ban,
  so it promises nothing ("kicked" says they may join again, false for a ban). A ban then
  shows on the next join as the server's 403. **Only for the page's own room**: the event goes to
  the player's personal channel (`user:{id}`), which every room socket joins too, so `useSocket`
  drops a `you_were_kicked` whose `room_id` is not its room. Without it, a kick from a room the
  player had left away (Remove is for exactly that), or the ban of a removed player, sent them
  out of the room they were in now.
- **A page driven by `useViewTransitionValue` draws the shown phase from `useHeldForPhase`.** The
  transition value lags the server by one render (the browser snapshots the old phase), and in
  that render the page would otherwise draw the OLD phase with the NEW state: "The answer was"
  with no answer. `useHeldForPhase(state, phase)` (`games/shared/quiz-utils.tsx`) keeps the state
  that belongs to the phase on screen, so the frame the crossfade fades out is true.
- **A test's `document.startViewTransition` stub runs the update asynchronously**, as the
  browser does (after the old state is captured): `vi.fn((update) => ({ finished:
  Promise.resolve().then(update) }))`, then `await act(async () => {})`. A stub that called it
  synchronously ran the hook's `flushSync` inside React's own effect ("flushSync was called from
  inside a lifecycle method", on every run) and could not show the old phase being held
  (`src/lib/view-transition.test.ts`).
- **Quiz scores are held back while a question is open, by the server.** The Quiz's state shows
  every total as it stood before the round (`current_round_points` and `my_points` are 0) until
  the reveal, so `PlayerScoreboard` shows the totals as sent. It used to subtract
  `current_round_points` itself (`holdRoundPoints`, removed): with the server doing it, that
  would take the points off twice.
- **The Quiz's reveal is the server's, so it survives a reload.** At the results phase the
  state carries `choice_tallies` (one count per choice), `my_choice_index` and
  `my_answer_time_ms` (all null while the question is open), and each `round_results` row its
  `choice_index`. `choiceNotes` (`games/mcqquiz/reveal.ts`) turns them into the note on each
  choice ("1 player", "you and 2 others", "+2 · you", "0"); the lock-in mark ("locked in at
  0:09") comes from `my_answer_time_ms`. Only while the question is open, when the server says
  nothing yet, does your own tap stand in for "you" and the mark. The page also hands
  `ChoiceButtons` the `tallies` and the `players` count: each choice draws its share as a tally
  thread (`tallyShares`), woven only when the reveal happens on screen (DESIGN.md §7).
- **The scoreboard's threads are measured against the game's maximum** (`PlayerScoreboard`
  `maxScore`: `QUIZ_ROUND_MAX` × rounds for The Quiz, `max_hints` × rounds for Kalimat), never
  against the leader, so a thread only grows. Its FLIP (`useScoreWeave`) plays when the totals
  change, never on the first state or the same totals sent again; it remembers each row's
  INDEX, not its pixels, and reads the slots from the layout of the moment (a language switch
  changes row heights). `current_round_points` shows as the gain ("+3"), so The Quiz shows it
  from the reveal and Kalimat from the moment a player finds the word. The gain's slot is on
  every row, gained or not (a first gain moved every total 44 px). The Quiz passes `weaveAfter`
  (`tallyWeaveMs`, `games/mcqquiz/reveal.ts`) during its results: the scoreboard waits for the
  tally threads, the reveal's one authored moment.
- **Every colophon's meta line is `ColophonMeta`** (`games/shared/ColophonMeta.tsx`): "Undercover
  · Yusuf’s majlis · 3 rounds · 21:40", from the state's `host_username`, `started_at`, `ended_at`
  (`colophonOf(state)`); a part the state lacks is left out, and a game under a second has no
  duration. The duration is a clock for the eye and a sentence for screen readers.
- **Kalimat's "Last round" card comes from the results phase.** The next round's state no longer
  carries the results, so the page keeps what `lastRoundFrom(state)` read there (the first
  finder, what they wrote: `typed_answer`, at which hint, for how much) and stores it in the tab
  (`rememberLastRound`, sessionStorage per game) so a reload still shows it. The header names the
  word's theme from `category` (`game.quiz.kalimat.category.*`); the results list what each
  player wrote, a miss's last try and its number of tries.
- **`useSocket` sends the language with `join_game`.** Undercover and Codenames write the
  `game_state` push straight into the cache: it is asked for in `i18n.language` and written only
  into the query keyed `{ lang }` with that value, so an English push can no longer overwrite the
  Arabic meanings (or land in another language's cached query).
- **Achievements are seals on the colophon, grouped by `useAchievementSeals`**
  (`games/shared/achievement-seals.ts`): one seal per achievement, captioned with everyone at the
  table who earned it ("you and Maryam · Bronze"), yours first. Never a toast mid-game; the old
  `AchievementToast` is deleted.
- **Undercover's role model.** Civilians and Undercovers are NOT told their role: the lawh shows
  each of them a word and nothing else (the canonical rule). Mr. White IS told (his tablet says he
  has no word, because he has to bluff). Roles appear when someone is eliminated and at game over.
- **Codenames reads a clue out once.** The header's live line only says whose turn it is;
  `ClueAnnouncer` (exported from `games/codenames/CluePanel.tsx`) is a polite, always-mounted
  `role="status"` whose text changes only when a new clue lands ("Clue for the Red team: KNOWLEDGE, 2").
  It must be mounted once on the page for every role, not inside the spymaster's composer, and
  BEFORE `ClueBanner` in the page's JSX: its layout effect notes the clue that just landed
  (`clueJustLanded`, cleared on the next microtask), which the spymaster's banner, mounting in
  the same commit as their clue, reads to write it in (`ClueBanner.motion.test.tsx` checks the
  page's order).
- **No hidden E2E hooks in the quiz pages.** The specs read what a player reads: the header's
  "Round 1 of 5" / "Question 1 of 10", and the hint ladder's rung in play
  (`aria-current="step"` in the list named "Hints, from the vaguest…"). The old `sr-only
  aria-hidden` "Round 1/…", "Question n/m" and "#1" spans were removed; do not add test-only
  text to a page.
- **Focus follows the phase** (`hooks/use-phase-focus.ts`, F2). A phase swap unmounted the
  button just pressed, focus fell to `<body>` and the next Tab restarted at the skip link.
  `usePhaseFocus(phaseKey, gameRef, { targets })` focuses the new phase's title after the
  swap (tabindex -1, `preventScroll`), only when focus is free: on `<body>`, or on a control
  inside the game region that is not a field being typed in (`focusIsFree`). Never on the
  first render or the first state (a change from null: a page load). Targets: Undercover,
  each phase's h2; The Quiz, the question (h2), the locked-in note, the reveal's first h3;
  Kalimat, the rung in play, the "You found it" status, "The answer was"; every game's end,
  the colophon title (`data-colophon-title`, which `Colophon` puts on its title). The quiz
  pages wrap their game-over branch in the same `gameRef`.
- **Codenames' end** (F3, `useCodenamesGame`): the veil comes 640 ms after the game ends
  (the decisive card's weave, `--dur-authored`), holds 1280 ms (`--dur-ceremony` + 180), or
  comes at once and holds 600 ms under reduced motion, then lifts through
  `withViewTransition`; `colophonHeld` keeps the colophon back for all of it. A page opened
  on a finished game has no veil and takes no focus. The 640 ms are counted from the
  `requestAnimationFrame` after the end, never from the effect: the effect can run inside
  the task that commits the board, and on a slow phone the rest of that task held the
  paint back (~340 ms on CI's runner), so the veil came while the card had barely shown.
- **The quiz colophon reads owner rule (a) from its leaderboard** (`QuizGameOver`): several
  top scorers above 0 → `game.quiz.sharedWin` naming them all; nobody scored →
  `game.quiz.noWinner`; one player → `game.quiz.soloScore`, never "wins". The server's
  `winner` is null for the first two; the analytics "game-over" event keys on `game_over`.
- **A clue is one word, said before it is sent** (`CluePanel`, `isOneWordClue`, BR-14): any
  whitespace inside the trimmed clue shows `errors.api.clueMustBeOneWord` under the field and
  sends nothing (the server's `ClueMustBeOneWordError` stays the rule).
- **One request per move** (FR-4): a move handler sets a synchronous in-flight ref before
  `mutateAsync` (TanStack's `isPending` reaches the button a tick later): The Quiz's lock-in
  and next round, Kalimat's next round, Codenames' clue, guess and End Turn (busy while
  sent), and every page's Leave. Refusals fall back to `game.errors.*`, never English.
  The Quiz's lock-in also counts from the server's yes (`useMcqQuizGame().hasLockedIn`):
  until the refetch said `my_answered`, the button was live again and a second tap sent a
  second answer, refused with a toast, the pick on screen cleared.
- **The quiz pages draw, their hooks decide** (TQ-12): `useWordQuizGame` and
  `useMcqQuizGame` (`hooks/`) hold the state read, the moves, the timer report, the gone-game
  redirect and Kalimat's ladder clock, like `useUndercoverGame`; the pages keep the phase
  on screen, focus and the pause veil. Tested on fake timers (`hooks/use-*-game.test.ts`).

### The prayer pause (وقفة الصلاة)

`components/games/shared/prayer-pause/` serves all four game pages; the server owns every rule
(backend/CLAUDE.md, "The prayer pause").

- **`usePrayerPause(game, gameId, state)`** reads `paused`, `can_pause`, `can_resume` (per caller)
  and sends the two requests. Success has no toast: the veil appearing or lifting is the answer.
- **`PauseControl`** is the host's control in the game header. **`PauseLayer` / `PauseVeil`** lie
  over the whole game frame while paused: the page makes the game underneath `inert`; the veil
  says who paused and for how long, shows the still thread where the clock stopped, and holds the
  only live Resume. It takes focus only if focus was in the game, and gives it back on resume.
- **Clocks freeze from the server's figure.** `PhaseTimer` takes `paused` and `frozenRemaining`
  (the server's `remaining_seconds`); on resume the server moves `timerStartedAt` forward, so the
  clock just continues. The thread's own animation is paused (`Animation.pause()`), never
  re-created while paused, so it stands still to the pixel; the moved start re-creates it from
  the server's figure on resume. A `timer-expired` answering `paused` or `round_already_resolved`
  (`isTimerStopAction`) stops firing for that window; a move refused with
  `errors.api.gamePaused` (`isGamePausedError`) refetches the state that shows the veil.
- **"Anyone may resume"** is timed on the server's clock (`msUntilAnyoneCanResume`), never the
  device's.
- **The adhan suggestion** (`useAdhanSuggestion`, `AdhanSuggestion`): from the adhan until
  `ADHAN_SUGGESTION_WINDOW_MS` (20 min) after, the host alone is offered the pause, once per prayer
  per game (sessionStorage). Only from a stored city: a game never asks the network where its host is.

### The Kunnash (/notebook)

- **The page** is `routes/_auth/notebook.tsx` with `components/notebook/*`: newest first, grouped
  into runs by game and day (`groupEntries`), keyset pages from `next_cursor`
  (`use-notebook-entries.ts`), an undo window before a removal is sent.
- **The colophons** (Undercover, Codenames, Kalimat) use `useColophonNotebook` + `KeepWordsAction`
  ("Keep the words", the brass action while a word is unkept, then the link "Kept in your
  kunnash") and an `aria-pressed` keep toggle per word row. They read the game id from the URL
  (`route-game.ts`, `useRouteNotebookGameId`); an optional `gameId` (`wordQuizGameId` on the quiz)
  prop overrides it. Nothing for a spectator or an MCQ game, and no request either.
- **A 204 has no body.** FastAPI labels it `application/json`; `api/client.ts` answers 204/205
  with `undefined` data instead of parsing (it used to throw a SyntaxError after the server had
  done the work: every DELETE, friend reject, notebook removal).
- **`KeepAction`** (`KeepWords.tsx`) is the keep pattern on its own (`kept`, `keeping`, `onKeep`,
  `label`, `keptLabel`): the colophons reach it through `KeepWordsAction`, the word of the day's
  reveal directly ("Keep in your kunnash", then "Kept in your kunnash", singular in French).
- **A word of the day is a `daily_word` entry** with no `source_game_id`: `gameName` names it
  (`GAME_NAME_KEY.daily_word` → `daily.name`) and `groupEntries` groups it by type and day.

### The word of the day (/today)

`routes/today.tsx` (public) renders `components/daily/DailyWordPage`; the server owns every rule
(backend/CLAUDE.md, "The word of the day"). Strings: the `daily` namespace.

- **One read for the page and the home card**: `useDailyWordQuery` (`use-daily-word.ts`). It is
  enabled only once `AuthProvider` has settled (`isLoading` false): the endpoint is public but
  answers 401 to a token that IS sent and invalid, and `api/client.ts` answers any 401 with a
  stored token by a refresh and, if that is refused, by sending the visitor to the login page.
  The key is `dailyWordKey(lang, viewer)`,
  the generated key plus `{ viewer }` (the user id, or null): a signed-out and a signed-in read of
  the same URL differ, so a login or a logout never shows the other's cached state.
  `DAILY_WORD_URL_KEY` (`[{ url }]`) matches every variant for an invalidation.
- **Every move sends `day: state.day`** (`useDailyWord`: `revealHint`, `guess`, `giveUp`, `keep`)
  and writes the state it gets back straight into the read's cache. A 409 `dailyWordNotToday`
  (a page left open past midnight in Makkah), `dailyWordAlreadyFinished` (another tab) or
  `dailyWordNoMoreHints` re-reads the day; the first is said as a plain toast, the others as
  errors (a move is the player's own action).
- **Midnight.** `DailyCountdown` counts to the state's `next_day_at` on `serverNow()`, one step a
  second, as a `role="timer"` (never a live region). The query re-reads a beat after
  `next_day_at`; that delay is capped at setTimeout's 2³¹−1 ms, beyond which it fires at once
  (a device clock far behind would otherwise loop reads).
- **The ladder is Kalimat's `HintDisplay`**, with three optional props it gained here: `offer`
  (what the next hidden rung shows instead of its warp: "Another hint: 5 points instead of 6",
  a `daily.ladder.another` plural on the points left; no arrow glyph, which a screen reader
  reads as "right arrow"), `nowTag` ("found" on the rung it was found
  at) and `settled` (a day given up: no rung in play). `focusableNow` + `listRef` let the page
  move focus to the hint it just revealed (`data-rung`), so it is read where it lands; Tab then
  reaches the next offer, then the field. The answer field is Kalimat's `AnswerInput`, with
  three optional props: `hint` ("… A wrong try opens the next hint.", `daily.play.fieldHint`),
  `wrongGuessMessage` and `maxLength` (`DAILY_WORD_ANSWER_MAX_LENGTH`, the server's 100; the
  default `ANSWER_MAX_LENGTH` is Kalimat's same 100), so a longer answer is never a bare 422.
- **A wrong try opens the next rung** (the server's rule, backend/CLAUDE.md): the state it
  answers holds one more hint. Focus stays in the field; its error names the rung
  ("“Badr” is not it. Hint 2 is open now.", `daily.play.wrongTry`, or `wrongTryLast` on the
  last rung, where a try opens nothing).
- **Focus on reveal.** A right guess or a confirmed give-up moves focus to the reveal's title
  (`#daily-reveal-title`, tabindex -1, a scroll margin under the sticky nav); loading a finished
  day takes none. Give up is a Radix `AlertDialog`, never `window.confirm`.
- **The reveal** (`DailyReveal`) is a colophon in the `ArchFrame`: the Arabic (vocalised when
  known, `answerForms`: the Arabic UI reads the Arabic alone), the word, its explanation, "found
  at hint 3 · 4 points" (sealed) or "given up", the streaks, "N players found it today",
  `KeepAction`, "Share" (the day's card through the share sheet, "The colophon card" below;
  where an image cannot be shared it copies `shareLine`: number, hint, `majlisna.app/today`,
  never the answer; a read-only field to copy by hand when the clipboard is refused), the
  countdown, the madd band.
- **Signed out**: the number, the date, the theme and hint 1; "Sign in to play"
  (`/auth/login?redirect=/today`) stands where the field would be.
- **The home card** (`components/home/DailyWordCard.tsx`) sits between the hero and the fihrist:
  the Arabic name, the number and theme, then one rung and the way to /today. Not started (or
  signed out): hint 1 worth 6 and "Find today’s word". Under way: the latest hint the player
  opened, worth what a right answer is worth now (`stakes`), and "Continue today’s word". Over:
  hint 1, "You found it · 4 points" (sealed) or "You gave up today’s word", and "See today’s
  word". A failed read leaves no card.
- **The menu sheet** lists `/today` after Play (`SHEET_LINKS`); the wide nav keeps its five
  links. The footer's pages list it too.
- Tests: `components/daily/__tests__/daily.test.ts` (pure helpers), `daily-page.test.tsx` (the
  page's states on the real generated hooks over the notebook's fake client),
  `components/home/__tests__/daily-card.test.tsx`. E2E: `e2e/tests/daily-word/today.spec.ts`
  (signed out → sign in and back; hint, wrong try, found; give up; keep → /notebook; the home
  card), desktop and phone, with the day's answer read from the database (`e2e/helpers/db.ts`).

### The colophon card (Share)

`components/brand/share-card/` (DESIGN.md §6, `ShareCardAction`): the evening as a 1080 × 1350
PNG, from every game's colophon (`ColophonActions`) and the word of the day's reveal.

- **The drawing model is pure** (`model.ts`: `layoutCard(input, measure)` → draw operations,
  colours as night tokens only, `CARD_COLORS`); `render.ts` only applies it to a canvas.
  happy-dom has no canvas: the model is tested with a fake `measure`, the renderer with a
  recording 2D context (`__tests__/render.test.ts`). What the card says comes from
  `game-card.ts` (the colophon's fields + the notebook's words) and `daily-card.ts`, kept apart
  so a game's colophon never loads the day's code (and a suite that mocks `@/api/generated`
  without `wordQuizCategoryEnum` keeps working).
- **The word of the day's card never carries the word**, its forms, its explanation, a hint or
  a guess: `__tests__/inputs.test.ts` checks the input AND every line drawn from it.
- **`document.fonts.load` fetches every face of the list that covers the text, fallbacks
  included**: the renderer asks only for the families it draws (`drawnStack`: Amiri; Samar
  Figures + Marcellus; Readex) and for letters only (a space is in Amiri's Latin face too), then
  awaits `document.fonts.ready`. The whole display stack used to download Amiri's Latin file
  for "Word of the day".
- **The work leaves the tap's task**: every await resolved at once (faces loaded), so the
  probe, both layouts and the drawing ran inside the click (29 ms at 4x CPU). `renderCardFile`
  yields to the browser first and between its pieces (`scheduler.yield`, else a 0 ms timeout);
  Chrome then encodes the PNG in idle slices. Measured on a production build at 1x and 4x: no
  frame or task over 20 ms (`render.test.ts`: nothing measured or drawn before the browser had
  a turn).
- **The share flow** (`ShareCardAction`): `canShareFiles()` asks `navigator.canShare` about an
  empty PNG synchronously, inside the tap; no → the line is copied at once (today's behaviour,
  no card drawn); yes → draw, then `navigator.share({ files, title, text: line })`. AbortError
  (sheet closed) says nothing; NotAllowedError (the tap's activation ran out) keeps the file and
  says `*.share.ready`, and the next tap shares that file at once; any other failure, or a card
  that cannot be drawn (reported through `reportError`), copies the line.

### The lobby

- **The room state read last wins** (`lib/room-state.ts`, `newerRoomState`). Every
  `RoomState` carries `as_of_ms`, when the server read it (before its first query). Two
  reads can arrive out of order: a socket's connect read the room just before the host
  picked Kalimat and sent it after the pick's own push, so a guest's lobby stayed on the
  old game for good, with no polling while the socket is up (CI, 2026-11-01). The socket's
  `room_state` handler writes through `newerRoomState`, and the lobby's query uses it as its
  `structuralSharing`. Never write a room state into the cache without it.
- **Seats keep their order.** The server lists a room's links by join time (it used to be heap
  order, which a heartbeat moved), and `stableOrder` (`components/rooms/lobby.ts`) keeps first-seen order and
  appends newcomers: the halqa never reshuffles under people's eyes.
- **Arrivals and departures are not toasts.** A status line under the ring
  (`data-testid="lobby-activity"`) says who sat down or left (`room.lobbyPage.activity*`), and on
  every member's screen whom the host removed or banned (`activityRemoved`, `activityBanned`,
  from `useRoomLobby.removals` through `rosterEvents`; the room is told by
  `member_removed_by_host`, a lobby on the polling fallback reads "left"); toasts stay for the player's own actions
  (copied link, start failed). Being removed or banned is an inline notice on /rooms.
- **The roster is in the DOM.** The halqa is a picture; `PlayerRoster` is the real list ("Players
  (N)", one row per seat, the host's Remove and Ban), and the E2E specs read its exact shape.
- **Remove and Ban each ask first** (owner decision, 2 November 2026: two actions, it replaced
  owner rule (c) under which Remove banned). Each row offers the host Remove (`UserMinus`, "Remove
  {{name}} from the room", a kick) then Ban (`Ban`, "Ban {{name}} from the room"), each opening
  its own `AlertDialog`: Remove's says the player may come back with the code and PIN, or an
  invite; Ban's that they cannot, not even through an invite, until the host lifts the ban, and
  that the PIN changes. Nothing is sent before the dialog's "Remove" or "Ban". After either, focus
  goes to the same button of the next row (`data-remove` / `data-ban`). E2E clicks the row's
  button by its name, then the dialog's action. The button and its dialog are one component,
  `RemovalConfirmButton` (`components/rooms/RemovalConfirmButton.tsx`), which RoomBans reuses.
- **The banned players, for the host only** (`components/rooms/RoomBans.tsx`, under the
  roster, "Banned players"; a kick is not listed there): `GET /rooms/{id}/bans`, each row with
  "Let {{name}} come back" (`DELETE`, one request per tap, a 404 read as already lifted). Under
  it, the **"Removed" group** (ban after removal, owner request, 3 November 2026; an `h3` in a
  `section` named by it, "Removed (N)", with a one-line hint): `GET /rooms/{id}/removals`, the
  players the host removed who are neither banned nor seated again, newest first, each with the
  roster's own Ban (`RemovalConfirmButton`, its dialog's text `banRemovedConfirmBody`: they
  already left, so it does not say they leave the room). A ban there moves the row to the banned
  list at once (the answer is the ban), re-reads both lists, the room state and the share link
  (the new PIN); a 404 `userNotInRoom` (back at the table, or banned from another device) is
  `room.lobbyPage.bans.removedGone` in a toast.info, never the server's "You are not in this
  room.". The group shows only while it lists someone or failed to load (its own `LoadFailed`).
  No panel while nobody was banned or removed; once shown it stays,
  so lifting the last ban leaves `room.lobbyPage.bans.empty` with focus on its title. One action
  at a time across the panel; after one, focus goes to the same button of the next row of that
  list, else to the panel's title (where a banned removed player went). A failed read is
  `LoadFailed`, never the empty line. A guest renders nothing and asks nothing. E2E: a Removed
  row has the roster's row shape, so `kick-ban.spec.ts` scopes the roster's rows to its region
  ("Players (N)").
- **The PIN on screen is the room state's.** The code tiles and the Share link read
  `room_state.password`, which a ban rotates: a link copied before a ban no longer works (one
  copied before a kick still does).
- **A banned friend is said on the invite dialog's row.** `InviteFriendModal` reads 403
  `errors.api.inviteeBanned` as "Banned from this room" (`room.invite.banned`, role=status) in
  place of that friend's Invite, not as a toast; members cannot read the bans, so the row learns
  it from the refusal. The app shell drops a room's invites, the pushed one and the stored
  copies (at once, before the re-read lands), on `you_were_kicked` with `banned`
  (`useRoomInvites.forgetRoom`): the server deleted them.
- **An away seat counts down from the server's figure.** `RoomPlayerState.away_seconds_left` is
  the server's own grace rule; `awayCountdown(members, dataUpdatedAt, now)` (`rooms/lobby.ts`)
  counts it down from the moment that state arrived (the query's `dataUpdatedAt`, which a socket
  push resets too), one tick a second only while someone is away. The ring's seat, the roster
  row and, with one player away, the legend say "away · 9:58". Never compute the grace locally.
- **Tabs pass `dir` themselves.** There is no Radix `DirectionProvider`, so Radix stamps
  `dir="ltr"` on a Tabs root unless told otherwise: the game picker passes `dir={i18n.dir()}`, or
  arrow keys run backwards in Arabic. Do the same for any new Radix roving-focus widget.

### The samar riddle (`components/rooms/SamarRiddle.tsx`, `samar-riddle.ts`)

While the table waits, a riddle: rung 1 of a Kalimat word, from `GET /rooms/{id}/riddle?lang=`
(`useGetRoomRiddleApiV1RoomsRoomIdRiddleGet`; members only, never today's word of the day nor an
answer of the room's running quiz, 409 while another game is played: backend/CLAUDE.md).

- **Where.** The lobby, under the activity line, while the table waits for its quorum
  (everyone) or for the host (every guest and spectator): `tableWaits` in the page. Never for
  the host of a ready table (or one too full): the next move is theirs. The Quiz's page, under
  the results (after "Next question"), between two questions; after the last question it only
  answers the riddle before (`ask={false}`). Never during a question, and never in Kalimat:
  Kalimat draws its words round by round, so a riddle could be a later round's word.
- **One riddle per wait, kept in the tab.** sessionStorage `majlisna-riddle:<room>:<scope>`
  (`lobby`, or `game:<gameId>` whose waits are the question numbers) holds the riddle on
  screen, when it was first shown and whether it was revealed: a remount or a reload shows the
  same riddle and asks nothing. Not mounted, nothing is asked.
- **"Revealed when the game starts" is read at the room's next wait.** The lobby follows the
  table into the game at once (`useRoomLobby` calls `answerRoomRiddle` before it navigates)
  and a question's results give way to the next question, so the riddle still unanswered is
  shown at the next wait of that room as "The last riddle, “…”, was Ibrahim."
  (`settleRiddleRecord`). Otherwise the answer is offered on a tap 30 s after the riddle was
  first shown (`RIDDLE_REVEAL_AFTER_MS`); a lobby whose game is Kalimat offers no tap (the word
  could come up in the game). "Another riddle" follows a revealed answer.
- **A refusal shows nothing** (403, 409, 429, offline): it is a pastime, never an error, and
  an "Another riddle" that fails keeps the riddle on screen.
- **Motion** (DESIGN.md §7): the line is written in on the compositor only when it CHANGES,
  never on the riddle a panel opens on; a line naming Allah, the Prophet ﷺ, a prophet, Jibril,
  the Qur'an or the Kaaba fades instead (`holdsSacredName`, `lib/sacred-names.ts`), and so does a
  line that wraps (its line boxes, read once: one window would wipe every line at once);
  reduced motion fades. No heading
  in it (the Quiz focuses the reveal's first `h3`), no live region.
- Tests: `components/rooms/__tests__/SamarRiddle.test.tsx` (the recording fake of
  `Element.animate`), `samar-riddle.test.ts`, `hooks/use-room-lobby.test.ts`,
  `routes/_auth/rooms/-tests/lobby.test.tsx`, `routes/_auth/game/-tests/mcqquiz-riddle.test.tsx`.
  A page test that mocks `@/api/generated` wholesale mocks `@/components/rooms/SamarRiddle` too
  (`wp13-mcqquiz-page.test.tsx`).

### The fixes of the 2026-10-28 review (keep them)

- **One table list per Undercover phase.** While describing and voting the seats are
  `DescriptionList` itself: who spoke and what, the Mayor (ink lozenge, never brass), who
  has voted (never for whom), the emptied seats with their role and "Eliminated · …"
  (`e2e` reads "Eliminated" there). For a player who may vote the other rows ARE the
  candidates (`button.uc-seat`, `aria-pressed`, named "Vote for X", text = the name, so
  `button:has-text(<name>)` still finds them). `UndercoverPlayerList` shows only where
  there is no list (the first reading, Mr. White's guess, the colophon). A seat that empties
  mid-round (a departure) stays in its place in this round's speaking order, receded; only
  the seats emptied in earlier rounds (not in the order) wait at the end. While a voter
  chooses, every row has a candidate's height (`--uc-seat-h`), so a candidate who leaves
  moves nothing under the finger.
- **Between rounds, the ready quorum** (owner rule (d), `RoundOverPanel`): the host keeps
  "Next round" (forces it; the E2E helper clicks exactly that name), every other alive player
  gets "I’m ready", then "You are ready…" (focus moves to that line when it replaces the
  button), and everyone, the eliminated and spectators included, reads the polite
  `role="status"` count "2 of 3 ready" (`readyCount`, from the state's `ready_count` /
  `ready_quorum`; plural keys, passed `count` — "1 sur 2 prêt", "2 من 3 جاهزان", review F4). `useUndercoverGame.handleStartNextRound` sends the one next-round call for
  both, behind a synchronous in-flight ref; `advanced: false` is a ready mark, shown at once
  (`isReady`) until the pushed state says so. Nothing on this screen may say "Waiting for".
- **The first reading and the read count survive a reload** (`lib/undercover-session`,
  sessionStorage per game); a table where someone has described is past it anyway.
- **Every colophon ends with `ColophonActions`** (`games/shared/ColophonActions.tsx`):
  Keep the words → Back to the room → the host's Play again → Share → Leave the room. Guests never
  see Play again (the server answers 403). Keeping the words is said in place, no toast.
  Share is a player's only: the call site passes `share` (`ColophonShare`: the game, host,
  count, start, end) and leaves it out for a spectator, as Keep is off for them.
- **Leaving is "Leave the room" everywhere** (`room.lobbyPage.leave`).
- **The server's clock** (`lib/server-clock`): the ky client notes each response's `Date`
  header; `serverNow()` is never ahead of the server (the largest lower bound of the
  offset). `PhaseTimer` and the Kalimat ladder read it: a phone 3 s ahead crossed a rung
  the server had not released, and the per-rung fetch guard then left it on the old hint.
  A rung still missing after its fetch gets ONE follow-up, still once per rung.
- **Sockets read the token at each (re)connect** (`auth: (cb) => cb({ token: … })`) and,
  refused, connect again when `onTokenStored` fires (AuthProvider's refresh): socket.io-client
  never retries a refused handshake. The app shell's personal socket (`_auth.tsx`) carries
  no `room_id` and receives friends' invites (`RoomInviteStrip`): the stored invite's id,
  code and inviter, never the PIN.
- **No `/auth/me` probe without a stored session** (`hasStoredSession`): a logged-out
  visitor's page load spent a 401 on it.
- **The host's game pick is the room's**: the lobby's tabs call `PATCH /rooms/{id}/settings
  {game_type}` and every member derives `gameType` from the room state.
- **A refused join is said once, on the page** (`data-testid="join-error"`, role=alert), never
  also as a toast; the removed player reads `room.youWereKicked` (they may join again),
  `room.youWereBanned`, or (the lobby's polling fallback, no event to say which)
  `room.youWereRemoved` on /rooms (`room-notice`).
- **Code then PIN, left to right, on every page** (home row, /rooms, the lobby, /rooms/join):
  the pair sits in a `dir="ltr"` container, labels stay translated.
- **The document title names the page** (`lib/document-title`, `lib/route-title`,
  `useDocumentTitle`): the route gives the fallback, a page with a name from its data
  (lobby, player, 404) overrides it; "Title · Majlisna" in the page's language.
- **`<main>` is at least one screen tall** under the nav: the footer starts below the fold
  (it caused CLS up to 0.7 when content arrived).
- **`ConnectionStatus` sits under the nav** (`top: var(--navh)`, z-40), never over its controls.
- **Locale typography is tested** (`components/stats/__tests__/locales.test.ts`): ’ and …,
  no-break spaces before French `: ; ? !`, the same keys in the three files; in Arabic,
  Western digits, the tanwin on the letter before its alif (ـًا, never ـاً) and one kashida
  per game name in the games list, at a join Naskh allows (DESIGN.md §10). The Edit tool
  cannot carry U+00A0: write `\u00a0` in the JSON, or an exact-string replacement. Writing
  `\u00a0` in the Edit's old string also matches an existing no-break space, so French lines
  that hold one can be anchored.

### Google sign-in: the provider lives with the button

`GoogleOAuthProvider` injects Google's script (accounts.google.com/gsi/client, ~100 kB) on
mount, and it used to wrap the whole app in `__root.tsx`: every page and every game screen
downloaded it for a button that exists on two pages. Now `GoogleLoginButton` is an outer
`WithGoogleOAuth` (exported from `components/auth/GoogleLoginButton.tsx`) around an inner
component that calls `useGoogleLogin`, so the script loads on /auth/login and /auth/register
only, and is removed when they unmount.

- **No client id, no Google**: `WithGoogleOAuth` renders nothing when `VITE_GOOGLE_CLIENT_ID`
  is empty (read at render, `googleClientId()`). The hook used to run before that check and
  threw "must be used within GoogleOAuthProvider", which took both pages down in any build
  without the variable (a fresh clone, a preview).
- **Any other Google control** wraps itself in `WithGoogleOAuth` the same way; never put the
  provider back in the root layout. Account deletion does (`components/profile/DeleteAccount.tsx`,
  SEC F14): the dialog reads `/auth/me` once it opens, and for `auth_provider` "google" (with a
  client id in the build) its "Confirm with Google" asks `useGoogleLogin` for a fresh token
  (`hint` = the address, `prompt: "select_account"`) and sends `{ google_access_token }`; the
  provider sits inside the open dialog, so the script loads when it opens and goes when it
  closes. Every other account (and a build without a client id) types its password.
  `errors.api.googleAccountMismatch` is said in the dialog; Google's own refusal (or a script
  that failed to load: `WithGoogleOAuth`'s `onScriptLoadError`) says
  `profile.deleteAccountGoogleFailed`; a closed popup says nothing. `GoogleIcon` is exported for
  such buttons. Test: `components/profile/__tests__/DeleteAccount.test.tsx` (the real
  `@react-oauth/google` over a stand-in `window.google`).
- **"Change password" works for every account** (`components/profile/ChangePassword.tsx`,
  mounted in the profile's Account panel): the form reads `/auth/me` once "Change password"
  is pressed. An account with a password types its current one. A Google-only account
  (`auth_provider` "google") reads `profile.passwordGoogleIntro`, chooses a password, and the
  form's submit is "Confirm with Google" (the password is checked first, then Google is asked),
  sending `{ new_password, google_access_token }`; the provider sits inside the open form only.
  Both forms ask Google through `useGoogleConfirmation` (`components/profile/use-google-confirmation.ts`,
  with `GOOGLE_PROVIDER`). The PATCH answers the account, written into the `/auth/me` query
  (`auth_provider` is "email" from then on: the account signs in with the password AND with
  Google), so this form and the deletion dialog ask for the password afterwards; the toast says
  `profile.passwordSet`. A build without a client id offers the emailed reset link
  (`profile.passwordSetByEmail` → /auth/forgot-password), which sets a usable password too.
  `escapeTo` and `FormActions` live in `components/profile/form-parts.tsx`. Test:
  `components/profile/__tests__/ChangePassword.test.tsx`.
- Tests: `components/auth/__tests__/auth.test.tsx` renders the real pages with and without an
  id (no button mock), and `i18n/__tests__/detection.test.tsx` checks the shell on /, /about
  and a game page loads no Google script.

### The login form: "Forgot password?" comes after the password in the tab order

It sits at the end of the password's label row, but it is rendered AFTER the field and laid over
the label row (one grid cell, aligned on the first baseline), so Tab goes email → password →
"Forgot password?" → Log in. Do not move it back into `Field labelEnd`.
