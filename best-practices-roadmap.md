# Best Practices Roadmap (from LaTabdhir audit)

Features **excluded**: Alembic migrations, admin dashboard, FCM push notifications, AWS deployment, driver.js onboarding, nginx caching.

---

## Tier 1 — Quick wins

### 1. Pre-commit hooks
Copy pattern from LaTabdhir's `.pre-commit-config.yaml`:
- Ruff lint + format
- File quality: trailing whitespace, end-of-file-fixer, check-yaml/toml/json, check-merge-conflict, check-added-large-files (500kb)
- Type checking (optional local hook)

**File to create:** `backend/.pre-commit-config.yaml`

### 2. Rate limiting (`slowapi`)
Add to auth-sensitive endpoints:
- `POST /auth/login` — 5/minute
- `POST /auth/register` — 5/minute
- `POST /auth/refresh` — 30/minute

**Files:** `backend/ipg/api/middleware.py` (add limiter setup), auth route decorators

### 3. Sentry (frontend)
LaTabdhir pattern from `front/src/lib/sentry.ts`:
- `@sentry/react` + `@sentry/vite-plugin`
- Environment-aware sample rates (0.1 prod, 1.0 dev)
- Session replay on errors
- Auth token redaction in breadcrumbs
- Error noise filtering (ResizeObserver, AbortError, etc.)
- User context (`setUser` on login)

**Files:** `front/src/lib/sentry.ts` (new), `front/vite.config.ts` (plugin), `front/src/routes/__root.tsx` (ErrorBoundary)

### 4. i18n — Add French
User wants French / English / Arabic. Currently IPG has English + Arabic.
- Add `front/src/i18n/locales/fr.json`
- Register in i18n config
- Add language switcher to UI (LaTabdhir has one)

### 5. Docker compose health checks
Add to `docker-compose.yml` and `docker-compose.dokploy.yml`:
```yaml
db:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U postgres"]
    interval: 10s
    timeout: 5s
    retries: 5
backend:
  depends_on:
    db:
      condition: service_healthy
```

### 6. Structured JSON logging (backend)
Upgrade `logger_config.py` to match LaTabdhir:
- `serialize=True` in production (JSON output for log aggregation)
- Human-readable format in development
- Suppress noisy third-party loggers (uvicorn, sqlalchemy, fastapi)

---

## Tier 2 — Medium effort

### 7. PWA support
LaTabdhir uses `vite-plugin-pwa`:
- `registerType: 'autoUpdate'`
- Web app manifest (name, icons, theme color, display: standalone)
- Workbox runtime caching (API: NetworkFirst, images: CacheFirst)

IPG as a game benefits greatly from being installable on phones.

### 8. Frontend structured logging (`loglayer`)
LaTabdhir pattern:
- Session ID persistence in sessionStorage
- Module-scoped loggers: `getLogger('api')`, `getLogger('socket')`
- Global context enrichment (route, env, timestamp, userId)
- Future: pipe logs to Sentry transport

### 9. Analytics (Umami)
Self-hosted, privacy-friendly analytics:
- Docker compose service with its own PostgreSQL
- Track game engagement, player retention
- No cookie banner needed

### 10. Charts (`chart.js` + `react-chartjs-2`)
Player stats visualization on profile page:
- Win/loss ratio over time
- Games played per week
- Separate Vite chunk for bundle optimization

### 11. Email service (Resend)
LaTabdhir pattern:
- Resend API integration
- Jinja2 HTML templates with i18n (French/English/Arabic)
- RTL support for Arabic emails
- Use cases for IPG: welcome email, password reset

### 12. Referral system
LaTabdhir pattern:
- 8-char alphanumeric codes, unique per user
- Self-referral prevention
- Reward: promo codes or in-game perks
- Constants: cooldown, max referrals, expiry

### 13. Image upload (MinIO)
LaTabdhir uses boto3 with MinIO (local) / S3 (prod):
- Profile avatars for IPG users
- Docker compose MinIO service
- CDN URL generation

### 14. Background cron jobs
LaTabdhir uses `fastapi-scheduler` locally:
- IPG use cases: cleanup stale/inactive rooms, reset daily stats, check achievements
- Pattern: separate handler functions, can later be extracted to Lambda if needed

---

## Tier 3 — Nice to have

### 15. Command palette (`cmdk`)
Power-user navigation — search rooms, players, games from anywhere.

### 16. Lottie animations
Polish for game events (win/loss/achievement unlock).
