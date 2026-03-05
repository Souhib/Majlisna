# CLAUDE.md - IPG Frontend

## Overview

React 19 SPA for the IPG (Islamic Party Games) platform. Uses TanStack Router for file-based routing, TanStack Query for server state management and real-time polling, Tailwind CSS v4 with shadcn/ui components.

## Development Commands

```bash
cd front

# Start dev server
bun dev                     # http://localhost:3000

# Generate API client from backend OpenAPI spec
bun run generate            # Requires backend running on :5000

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
- **State**: TanStack Query (React Query) for server state + polling
- **Styling**: Tailwind CSS v4 + shadcn/ui (new-york style)
- **Forms**: React Hook Form + Zod validation
- **API**: Kubb-generated hooks from OpenAPI spec + ky HTTP client
- **Real-time**: TanStack Query polling (2s `refetchInterval`)
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
│   │   │   └── $roomId.tsx  # Room lobby (REST polling)
│   │   ├── game/
│   │   │   ├── undercover.$gameId.tsx  # Undercover game UI (polling)
│   │   │   └── codenames.$gameId.tsx   # Codenames game UI (polling)
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

### Real-time Polling (Game & Room Pages)
Game state is fetched via `useQuery` with 2s polling. All UI state is derived from the server response via `useMemo`, not accumulated from events.

```typescript
const { data: gameState } = useQuery({
  queryKey: ["undercover", gameId],
  queryFn: () => apiClient({ method: "GET", url: `/api/v1/undercover/games/${gameId}/state` })
    .then(r => r.data),
  refetchInterval: 2000,
  refetchOnWindowFocus: true,
})

const voteMutation = useMutation({
  mutationFn: (votedFor: string) =>
    apiClient({ method: "POST", url: `/api/v1/undercover/games/${gameId}/vote`,
      data: { voted_for: votedFor } }),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["undercover", gameId] }),
})
```

Phase transitions detected by comparing refs to previous state (`previousPhaseRef`, `previousRoundRef`).

### Room Lobby (REST Polling)
- Join room via REST `PATCH /api/v1/rooms/join` on mount
- Poll room state every 2s (`useQuery` with `refetchInterval: 2000`)
- Auto-navigate when `active_game_id` appears in polled data
- Leave room via REST `PATCH /api/v1/rooms/leave`

### File-Based Routing
- `__root.tsx` - Root layout (double underscore)
- `_auth.tsx` - Protected layout (single underscore, redirects to login)
- `$param.tsx` - Dynamic parameters
- `index.tsx` - Index route for directory

### Authentication
- JWT stored in localStorage (`ipg-token`, `ipg-refresh-token`, `ipg-token-expiry`)
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
VITE_API_URL=http://localhost:5000    # Backend API URL
```

Vite dev server proxies `/api` to the backend.
