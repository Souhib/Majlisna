# Multi-stage build for Majlisna frontend
#
# Base images are pinned by digest (INFRA-17): the tag says which version it is, the
# digest is what gets pulled, so CI's gate and Dokploy's build run the same bytes.
# Bump both together (Dependabot does).

# The clone's git metadata, read by the last build step below: EMPTY unless the build names
# a context `gitmeta` (docker-compose.dokploy.yml hands it the repository root, reduced by
# its .dockerignore to .git/HEAD, .git/refs and .git/packed-refs). See backend/Dockerfile.
FROM scratch AS gitmeta

# Stage 1: Build
FROM oven/bun:1.4.4-alpine@sha256:4cf82f5686b196504fe119db3fcd9185b191f82ece82c40680e597228ec6070a AS build

WORKDIR /app

# Copy package files
COPY package.json bun.lock ./

# Install dependencies (including devDependencies for building)
RUN bun install --frozen-lockfile

# Copy application code
COPY . .

# Build arguments for environment variables
ARG VITE_API_URL
ARG VITE_SENTRY_DSN
ARG VITE_UMAMI_URL
ARG VITE_UMAMI_WEBSITE_ID
ARG VITE_GOOGLE_MAPS_API_KEY
ARG VITE_GOOGLE_CLIENT_ID

# Set environment variables for build
ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN}
ENV VITE_UMAMI_URL=${VITE_UMAMI_URL}
ENV VITE_UMAMI_WEBSITE_ID=${VITE_UMAMI_WEBSITE_ID}
ENV VITE_GOOGLE_MAPS_API_KEY=${VITE_GOOGLE_MAPS_API_KEY}
ENV VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID}

# Build the application, then prepare what nginx serves:
#
# 1. The CSP hashes of index.html's inline scripts, from the BUILT file: Vite rewrites
#    the Umami bootstrap from the build args, so the source file's hashes would be wrong.
#    The script refuses (and fails the build) on an inline event handler or a
#    javascript: URL, which no hash can allow. See security-headers.conf.
# 2. A gzip -9 twin of every compressible file, served as is by nginx's gzip_static
#    (FP-12). Files under gzip_min_length (256 B) are left alone. No Brotli twins: the
#    official nginx image has no ngx_brotli to serve them.
# 3. World-readable modes. Vite copies public/ with the checkout's file modes, and the
#    CI runner's dedicated account checks out with a private umask: sw.js and the skies
#    then reached nginx as 0600 and answered 403.
ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN set -eu; \
    bun run build; \
    bun scripts/csp-inline-hashes.mjs dist/index.html > /app/csp-inline-script-hashes.txt; \
    find dist -type f \( -name '*.js' -o -name '*.mjs' -o -name '*.css' -o -name '*.html' \
        -o -name '*.svg' -o -name '*.json' -o -name '*.txt' -o -name '*.xml' -o -name '*.ico' \
        -o -name '*.webmanifest' \) -size +255c -exec gzip -9 -k {} +; \
    chmod -R a+rX dist

# Stage 2: Production with Nginx
FROM nginx:1.31.8-alpine@sha256:785835ea65db4bba6f021acc0f3be91b0fef76a53fe41f8588c6698d2aed0606 AS production

# Re-declared: build args do not cross stage boundaries. These are the same values
# the bundle above was built with, which is the point — the CSP allowlist and the
# hosts the bundle actually talks to come from one source.
ARG VITE_API_URL
ARG VITE_UMAMI_URL
ARG VITE_SENTRY_DSN

# Copy custom nginx configuration. security-headers.conf is included from every
# location block in nginx.conf (see the comment there for why it can't live in
# the server block alone).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/security-headers.conf

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/csp-inline-script-hashes.txt /tmp/csp-inline-script-hashes.txt

# Fill the CSP's placeholders, then prove the result is a policy worth shipping.
#
# - The inline-script hashes computed in the build stage go after script-src 'self'.
# - The API origin, and the WebSocket origin derived from it (wss:// for https, ws://
#   for http, host and port kept), go into connect-src. There is no blanket ws:/wss:.
# - The telemetry origins: only the ORIGIN is taken from each value. The Sentry DSN
#   carries a key before the host (https://<key>@host/<project>) and that key must
#   not end up in a response header. An unset arg substitutes to nothing, which is a
#   valid policy — that is the local-dev and E2E case.
#
# The checks are not decoration: a leftover placeholder, an 'unsafe-inline' that would
# make the hashes moot, or a malformed directive would otherwise only surface as a
# container that refuses to start, or worse, as a policy the browser silently ignores.
# `nginx -t` runs on the real configuration: the backend is named through a variable
# (see nginx.conf), so nothing has to resolve at build time.
RUN set -eu; \
    headers=/etc/nginx/security-headers.conf; \
    script_hashes="$(cat /tmp/csp-inline-script-hashes.txt)"; \
    api_origin="$(printf '%s' "${VITE_API_URL:-}" | sed -nE 's#^(https?://[^/]+).*#\1#p')"; \
    case "$api_origin" in \
        https://*) ws_origin="wss://${api_origin#https://}" ;; \
        http://*) ws_origin="ws://${api_origin#http://}" ;; \
        *) ws_origin="" ;; \
    esac; \
    umami_origin="$(printf '%s' "${VITE_UMAMI_URL:-}" | sed -nE 's#^(https?://[^/]+).*#\1#p')"; \
    sentry_origin="$(printf '%s' "${VITE_SENTRY_DSN:-}" | sed -nE 's#^(https?://)([^@/]*@)?([^/]+).*#\1\3#p')"; \
    sed -i \
        -e "s#__INLINE_SCRIPT_HASHES__#${script_hashes}#" \
        -e "s#__API_CONNECT_SRC__#${api_origin} ${ws_origin}#" \
        -e "s#__TELEMETRY_SCRIPT_SRC__#${umami_origin}#" \
        -e "s#__TELEMETRY_CONNECT_SRC__#${umami_origin} ${sentry_origin}#" \
        "$headers"; \
    policy="$(grep -v '^[[:space:]]*#' "$headers")"; \
    if printf '%s' "$policy" | grep -qE '__[A-Z_]+__'; then \
        echo "CSP placeholder left unsubstituted — refusing to ship a policy with a literal token"; \
        exit 1; \
    fi; \
    if printf '%s' "$policy" | grep -oE "script-src [^;]*" | grep -q "'unsafe-inline'"; then \
        echo "script-src allows 'unsafe-inline': the inline-script hashes would be ignored"; \
        exit 1; \
    fi; \
    if printf '%s' "$policy" | grep -oE "connect-src [^;]*" | grep -qE "(^| )wss?:( |$)"; then \
        echo "connect-src allows any WebSocket host"; \
        exit 1; \
    fi; \
    nginx -t; \
    rm /tmp/csp-inline-script-hashes.txt

# The commit this image was built from, stamped into index.html's `majlisna-release` meta;
# the error tracker's SDK sends it as the release (src/lib/report-error.ts, readRelease).
# Last, so a new commit reruns this one step and no cached layer before it: a VITE_
# variable would rebuild the whole bundle on every commit, backend-only ones included.
# The backend's sources, in the same order (scripts/build-commit.sh): the GIT_SHA build
# arg, else the clone's git metadata from `gitmeta` (Dokploy), else "unknown". The gzip
# twin is written again (gzip_static would serve the old one), and a missing meta fails the
# build rather than shipping an image that stamps nothing.
ARG GIT_SHA=unknown
RUN --mount=type=bind,from=gitmeta,target=/run/gitmeta \
    --mount=type=bind,from=build,source=/app/scripts/build-commit.sh,target=/run/build-commit.sh \
    set -eu; \
    release="$(sh /run/build-commit.sh /run/gitmeta/.git "$GIT_SHA")"; \
    index=/usr/share/nginx/html/index.html; \
    sed -i "s#\(<meta name=\"majlisna-release\" content=\"\)[^\"]*\"#\1${release}\"#" "$index"; \
    if ! grep -qF "<meta name=\"majlisna-release\" content=\"${release}\"" "$index"; then \
        echo "index.html has no majlisna-release meta to stamp"; \
        exit 1; \
    fi; \
    gzip -9 -c "$index" > "$index.gz"

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
