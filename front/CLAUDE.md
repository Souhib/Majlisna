# CLAUDE.md - Majlisna Frontend

## Overview

React 19 SPA for the Majlisna platform. Uses TanStack Router for file-based routing, TanStack Query for server state management and real-time polling, Tailwind CSS v4 with shadcn/ui components.

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
bun run format              # oxfmt
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
- **Styling**: Tailwind CSS v4 + shadcn/ui (new-york style)
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
│   ├── ui/                  # shadcn/ui primitives
│   ├── layout/              # MainNav, Footer
│   ├── ErrorBoundary.tsx
│   └── NotFound.tsx
├── hooks/
│   ├── use-socket.ts        # Socket.IO hook (real-time state into TanStack Query cache)
│   └── use-prayer-times.ts  # Prayer times hook
├── i18n/
│   ├── index.ts             # i18next config
│   └── locales/             # en.json, ar.json
├── lib/
│   ├── utils.ts             # cn() utility
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
│   └── auth/
│       ├── login.tsx        # Login form
│       └── register.tsx     # Register form
├── index.css                # Tailwind v4 + theme CSS variables
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

Supports English (LTR) and Arabic (RTL). The root layout auto-detects RTL languages and sets `dir="rtl"`.

```typescript
import { useTranslation } from "react-i18next"

const { t } = useTranslation()
t("games.undercover.name")  // "Undercover" or "المتخفي"
```

Translation files in `src/i18n/locales/`.

## Theme

Single theme with light/dark mode support via CSS variables. Uses emerald green primary with gold accent colors. Theme toggle via `useTheme()` provider.

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
