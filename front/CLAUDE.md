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
bun run test:coverage       # With coverage
bun run test:ui             # Vitest UI
```

## Tech Stack

- **Runtime**: Bun
- **Framework**: React 19 + TypeScript
- **Routing**: TanStack Router (file-based)
- **State**: TanStack Query (React Query) for server state
- **Styling**: Tailwind CSS v4 + Samar primitives on Radix (`components/ui`), brand pieces (`components/brand`), self-hosted @fontsource fonts (`src/fonts.ts`). Read `DESIGN.md` before any UI work.
- **Forms**: React Hook Form + Zod validation
- **API**: Kubb-generated hooks from OpenAPI spec + ky HTTP client
- **Real-time**: Socket.IO (socket.io-client) pushes state into TanStack Query cache via `useSocket` hook
- **i18n**: i18next (English + Arabic with RTL support)
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
│   ├── home/                # HomeHero (sky + name + join row), HalqaCard, GamesFihrist, SupportSection
│   ├── ErrorBoundary.tsx
│   └── NotFound.tsx
├── hooks/
│   ├── use-socket.ts        # Socket.IO hook (real-time state into TanStack Query cache)
│   ├── use-resolved-theme.ts # The light on screen ("dark"|"light"), read from <html data-theme>
│   └── use-prayer-times.ts  # Prayer times hook
├── i18n/
│   ├── index.ts             # i18next config
│   └── locales/             # en.json, ar.json
├── lib/
│   ├── utils.ts             # cn() utility
│   ├── motion.ts            # Motion grammar presets (durations, easings, variants)
│   ├── view-transition.ts   # View Transitions for phase changes (feature-detected)
│   └── auth.ts              # Token storage helpers
├── providers/
│   ├── AuthProvider.tsx     # JWT auth state + token refresh
│   ├── QueryProvider.tsx    # React Query client
│   ├── ThemeProvider.tsx    # Light/dark mode
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
│   ├── credits.tsx          # Image, font and icon attribution (CC BY-SA credits live here)
│   ├── about.tsx            # About + "How the games play" (components/about/GameRules, ids #undercover #codenames #kalimat #quiz)
│   └── auth/
│       ├── login.tsx        # Login form
│       └── register.tsx     # Register form
├── styles/                  # brand.css (component CSS), shell.css (nav/footer), home.css, sadu.css (generated bands), pages/*.css (codenames, quiz, rooms, undercover)
├── fonts.ts                 # Self-hosted fonts (imported right after zod-jitless)
├── index.css                # Tailwind v4 + Samar tokens, type roles, motion utilities
└── main.tsx                 # App entry point
```

## Key Patterns

### API Integration (Kubb)
Auto-generated React Query hooks from backend OpenAPI spec:
```typescript
import { useGetUsersApiV1UsersGet } from "@/api/generated/hooks"

function MyComponent() {
  const { data, isLoading } = useGetUsersApiV1UsersGet()
}
```

**Never edit files in `src/api/generated/`.** Regenerate with `bun run generate`.

### Real-time Updates (Socket.IO Primary, Conditional Polling Fallback)
Socket.IO is the primary real-time transport. The room lobby stores `roomId` in SessionStorage before navigating to game pages (`storeRoomIdForGame`), so Socket.IO connects immediately on mount via a lazy `useState` initializer (`retrieveRoomIdForGame`). Fallback: if no stored roomId (e.g., page refresh), the first REST poll provides it.

`useSocket` returns `{ connected }`. All pages (game pages and room lobby) use `refetchInterval: socketConnected ? false : 2_000` — **zero polling when Socket.IO is connected**, fast 2s polling as fallback when disconnected. `useSocket` also accepts an `onKicked` callback for handling `you_were_kicked` events from the server. All UI state is derived from the server response via `useMemo`, not accumulated from events.

Phase transitions detected by comparing refs to previous state (`previousPhaseRef`, `previousRoundRef`).

### Room Lobby (REST Polling + Socket.IO)
- Poll room state every 2s (`useQuery` with `refetchInterval: 2000`)
- Socket.IO pushes real-time updates for room state
- Auto-navigate when `active_game_id` appears (stores `roomId` in SessionStorage for game page)
- Leave room via REST `PATCH /api/v1/rooms/leave`

### File-Based Routing
- `__root.tsx` - Root layout (double underscore)
- `_auth.tsx` - Protected layout (single underscore, redirects to login)
- `$param.tsx` - Dynamic parameters
- `index.tsx` - Index route for directory

### Authentication
- JWT stored in localStorage (`majlisna-token`, `majlisna-refresh-token`, `majlisna-token-expiry`)
- Auto-refresh 1 minute before expiry
- 401 responses clear auth state and redirect to login

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
  const message = getApiErrorMessage(err, "Fallback message")
}
```

## i18n

Supports English and French (LTR) and Arabic (RTL). The root layout auto-detects RTL languages and sets `dir="rtl"`.

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
  results of the player's own actions (`gameStarting`, `youLeftRoom`, `roomCreated`).
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

The cookie branch now calls `refreshAccessToken()` immediately and schedules from
the returned `expires_in`. Two consequences to preserve:

- **`useSocket` authenticates the Socket.IO handshake with the localStorage
  token** (`getStoredToken()`), and the backend `connect` handler rejects an
  expired one. A stale token there doesn't just break auth — it silently drops
  real-time and leaves every player on the 2s REST polling fallback.
- `refreshAccessToken` retries **cookie-only** when the body token is rejected.
  The backend prefers `refresh_token` from the JSON body over the httpOnly cookie,
  so a stale localStorage value otherwise shadows a perfectly good refresh cookie.

There is also a `visibilitychange` refresh: `setTimeout` is throttled or frozen in
a backgrounded tab, which is where a party game spends most of its time on mobile.

### localStorage and httpOnly cookies are both live — on purpose, for now

Tokens are written to localStorage *and* set as httpOnly cookies. The cookies are
the real mechanism in production (same-origin via `majlisna.app/api`); localStorage
exists because `ky` defaults to `credentials: "same-origin"`, so a cross-origin
`VITE_API_URL` (local dev on `:5111`, or `api.majlisna.app`) never sends cookies —
and because `useSocket` needs a readable token. Dropping localStorage means setting
`credentials: "include"` on the ky instance and passing the token to Socket.IO some
other way. Until then, do not "clean up" one half of this.

### `PhaseTimer` fires `onExpired` once per timer window, not per render

The effect keys on `timerStartedAt` + `durationSeconds` and refuses to fire twice
for the same pair (with a 15s re-arm as a liveness valve, since only the host
triggers expiry and a failed call would otherwise stall the round).

It used to depend on `[remaining, onExpired]`. `onExpired` is a `useCallback` whose
deps include the React Query mutation object — a **fresh object on every render** —
so any parent re-render re-armed the effect. And the handler calls
`invalidateQueries`, which re-renders the parent: a self-sustaining loop firing a
POST and a server broadcast per cycle, for as long as the phase kept the timer
expired. In Undercover that phase is the whole gap between a round resolving and
the host starting the next one, and each call used to eliminate another player.

The server-side guard (`round_already_resolved`) is the real safety net — see
backend/CLAUDE.md, "An Undercover round resolves exactly ONCE". Both halves stay.

### AuthProvider shares the in-flight refresh promise

`refreshAccessToken` returns the pending promise to a concurrent caller. It used to
return `false`, which `scheduleTokenRefresh` reads as *failure* and answers by
clearing auth and logging the player out — while the other refresh was about to
succeed. Overlapping callers are the normal case on mobile: the throttled
`setTimeout` fires at the same moment `visibilitychange` does.

### `UserData` carries only what the API returns

`is_active` and `is_admin` were declared `boolean` here and fabricated at every call
site (`is_admin: false` at login, `updated.is_admin` from a PATCH whose response is
a `UserView`). The backend has never exposed either, so both were permanently
`undefined` behind a `boolean` type. Do not re-add a client-side admin flag:
authorization is decided server-side by `get_current_admin_user`.

### The lobby warns about stale state instead of blanking

`queryError && !roomData && failureCount > 2` still gates the full-page error, but
`!roomData` is never true again after the first successful load — so a room that
stopped refreshing (kicked, room closed, backend down) left the player on a frozen
lobby with no signal. A banner (`room.staleState`) now says so when there is already a
roster on screen. Deliberately a banner and not a redirect: replacing a live lobby
over one bad poll would be worse than showing stale data.

### Text on a 10% tint uses the `-on-tint` tokens

`text-primary` on `bg-primary/10` measured **3.56:1** at 12px and
`text-destructive` on `bg-destructive/10` measured **4.09:1** — both under the 4.5:1
AA floor for small text. `--primary-on-tint` / `--destructive-on-tint` exist for that
pairing only, so buttons, icons and headings keep the brand colours. They are
*darker* in light mode and *lighter* in dark mode: the tint composites over opposite
backgrounds.

This is also a lesson about the accessibility suite. The axe scan runs right after
`domcontentloaded`, while the cards are still animating in, and axe skips a node that
is momentarily `opacity: 0` — so whether the chips got measured at all depended on
machine speed. Three clean local gate runs missed it; CI caught it. The deterministic
guard is `e2e/tests/accessibility/contrast.spec.ts`, which waits for the animation to
settle and composites the translucent tint the way a browser does. When adding a
chip-style label, keep it above 4.5:1 or make the text large enough to qualify for
the 3:1 large-text threshold.

### The CSP is enforced, and `Zod` must stay jitless for it to be

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
API call. The E2E suite is what found that.

**`src/lib/zod-jitless.ts` must stay imported first in `main.tsx`.** Zod 4 decides
whether to JIT-compile validators by *probing* `new Function("")` in a try/catch. Under
the policy that probe is blocked; Zod catches it and uses the interpreted path, so
nothing breaks — but every page load records a `script-src`/`eval` violation. Setting
`jitless` short-circuits the probe (`fastEnabled = jit && allowsEval.value`), giving the
same code path with no violation. It took a while to find because minification aliases
`Function` to a local, so it does not appear in the bundle as `new Function`.

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
the 2:1 tab crop, above: 1600/2400 w, `sizes="100vw"`). The inline script in `index.html`
preloads the same file for the stored light on `/`, with the same `imagesrcset`, `imagesizes`
and media queries, so the browser downloads exactly one sky. Change one, change the other
(and check the network panel: one `/sky/` request per load). The sky files' bottom edge is the
horizon and the CSS ground starts on their last row: never crop or re-export them without the
ground colours in `public/sky/SOURCES.txt`.

### `_auth.tsx` must not re-navigate from the login page

The auth gate navigates to `/auth/login?redirect=<where you were>`. The layout stays mounted
while the router moves, so the effect ran again with `location` = the login URL and navigated
a second time with `redirect=/auth/login?...`, which `safeRedirect` drops: every redirect was
lost (a shared `/rooms/join?code=…&pin=…` link, or the home join row, then landed on `/`). The
effect now skips paths under `/auth/`.

Note: `vite.config.ts` drops `console.*` in dev too (`esbuild.drop`), so a `console.log`
added while debugging prints nothing; expose a value on `window` instead.

### `PhaseTimer` renders the thread clock, never red

`PhaseTimer` keeps its props and its once-per-window `onExpired` logic; it renders
`components/brand/ThreadClock` (a contracting woven thread, five brass lozenges for the last five
seconds, a knot at zero). Urgency is a change of rhythm, not colour: no red, no pulse. Its
`aria-label` names the clock and gives its text ("Time left: 0:20", `ui.clock.label`); a polite
live region speaks only at 30, 10 and 5 s.

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

### Credits

`routes/credits.tsx` carries the attribution the CC BY-SA images need (the home skies and
`og-image.png`, CC BY-SA 4.0; the Jabreen arch, CC BY-SA 2.0). It is linked from the footer on
every page. A new third-party image ships only with its entry there.

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
- **A kicked player leaves the game page too.** The four game pages pass `onKicked:
  useLeaveAfterKick()` to `useSocket` (`hooks/use-leave-after-kick.ts`, the lobby's behaviour):
  note the `room-notice` and go to /rooms. A kicked player is out of the room's socket rooms, so
  no `game_updated` reaches them: without it they sat on a frozen game, still seated.
- **A page driven by `useViewTransitionValue` draws the shown phase from `useHeldForPhase`.** The
  transition value lags the server by one render (the browser snapshots the old phase), and in
  that render the page would otherwise draw the OLD phase with the NEW state: "The answer was"
  with no answer. `useHeldForPhase(state, phase)` (`games/shared/quiz-utils.tsx`) keeps the state
  that belongs to the phase on screen, so the frame the crossfade fades out is true.
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
  nothing yet, does your own tap stand in for "you" and the mark.
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
  It must be mounted once on the page for every role, not inside the spymaster's composer.
- **No hidden E2E hooks in the quiz pages.** The specs read what a player reads: the header's
  "Round 1 of 5" / "Question 1 of 10", and the hint ladder's rung in play
  (`aria-current="step"` in the list named "Hints, from the vaguest…"). The old `sr-only
  aria-hidden` "Round 1/…", "Question n/m" and "#1" spans were removed; do not add test-only
  text to a page.

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
  clock just continues. A `timer-expired` answering `paused` or `round_already_resolved`
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

### The lobby

- **Seats keep their order.** The server lists a room's links by join time (it used to be heap
  order, which a heartbeat moved), and `stableOrder` (`components/rooms/lobby.ts`) keeps first-seen order and
  appends newcomers: the halqa never reshuffles under people's eyes.
- **Arrivals and departures are not toasts.** A status line under the ring says who sat down or
  left (`room.lobbyPage.activity*`); toasts stay for the player's own actions (copied link, start
  failed). Being removed is an inline notice on /rooms.
- **The roster is in the DOM.** The halqa is a picture; `PlayerRoster` is the real list ("Players
  (N)", one row per seat, the host's Remove), and the E2E specs read its exact shape.
- **An away seat counts down from the server's figure.** `RoomPlayerState.away_seconds_left` is
  the server's own grace rule; `awayCountdown(members, dataUpdatedAt, now)` (`rooms/lobby.ts`)
  counts it down from the moment that state arrived (the query's `dataUpdatedAt`, which a socket
  push resets too), one tick a second only while someone is away. The ring's seat, the roster
  row and, with one player away, the legend say "away · 9:58". Never compute the grace locally.
- **Tabs pass `dir` themselves.** There is no Radix `DirectionProvider`, so Radix stamps
  `dir="ltr"` on a Tabs root unless told otherwise: the game picker passes `dir={i18n.dir()}`, or
  arrow keys run backwards in Arabic. Do the same for any new Radix roving-focus widget.

### The fixes of the 2026-10-28 review (keep them)

- **One table list per Undercover phase.** While describing and voting the seats are
  `DescriptionList` itself: who spoke and what, the Mayor (ink lozenge, never brass), who
  has voted (never for whom), the emptied seats with their role and "Eliminated · …"
  (`e2e` reads "Eliminated" there). For a player who may vote the other rows ARE the
  candidates (`button.uc-seat`, `aria-pressed`, named "Vote for X", text = the name, so
  `button:has-text(<name>)` still finds them). `UndercoverPlayerList` shows only where
  there is no list (the first reading, Mr. White's guess, the colophon).
- **The first reading and the read count survive a reload** (`lib/undercover-session`,
  sessionStorage per game); a table where someone has described is past it anyway.
- **Every colophon ends with `ColophonActions`** (`games/shared/ColophonActions.tsx`):
  Keep the words → Back to the room → the host's Play again → Leave the room. Guests never
  see Play again (the server answers 403). Keeping the words is said in place, no toast.
- **Leaving is "Leave the room" everywhere** (`room.lobbyPage.leave`).
- **The server's clock** (`lib/server-clock`): the ky client notes each response's `Date`
  header; `serverNow()` is never ahead of the server (the largest lower bound of the
  offset). `PhaseTimer` and the Kalimat ladder read it: a phone 3 s ahead crossed a rung
  the server had not released, and the per-rung fetch guard then left it on the old hint.
  A rung still missing after its fetch gets ONE follow-up, still once per rung.
- **Sockets read the token at each (re)connect** (`auth: (cb) => cb({ token: … })`) and,
  refused, connect again when `onTokenStored` fires (AuthProvider's refresh): socket.io-client
  never retries a refused handshake. The app shell's personal socket (`_auth.tsx`) carries
  no `room_id` and receives friends' invites (`RoomInviteStrip`).
- **No `/auth/me` probe without a stored session** (`hasStoredSession`): a logged-out
  visitor's page load spent a 401 on it.
- **The host's game pick is the room's**: the lobby's tabs call `PATCH /rooms/{id}/settings
  {game_type}` and every member derives `gameType` from the room state.
- **A refused join is said once, on the page** (`data-testid="join-error"`, role=alert), never
  also as a toast; the removed player reads `room.youWereKicked` on /rooms (`room-notice`).
- **Code then PIN, left to right, on every page** (home row, /rooms, the lobby, /rooms/join):
  the pair sits in a `dir="ltr"` container, labels stay translated.
- **The document title names the page** (`lib/document-title`, `lib/route-title`,
  `useDocumentTitle`): the route gives the fallback, a page with a name from its data
  (lobby, player, 404) overrides it; "Title · Majlisna" in the page's language.
- **`<main>` is at least one screen tall** under the nav: the footer starts below the fold
  (it caused CLS up to 0.7 when content arrived).
- **`ConnectionStatus` sits under the nav** (`top: var(--navh)`, z-40), never over its controls.
- **Locale typography is tested** (`components/stats/__tests__/locales.test.ts`): ’ and …,
  no-break spaces before French `: ; ? !`, the same keys in the three files. The Edit tool
  cannot carry U+00A0: write `\u00a0` in the JSON, or an exact-string replacement.

### The login form: "Forgot password?" comes after the password in the tab order

It sits at the end of the password's label row, but it is rendered AFTER the field and laid over
the label row (one grid cell, aligned on the first baseline), so Tab goes email → password →
"Forgot password?" → Log in. Do not move it back into `Field labelEnd`.
