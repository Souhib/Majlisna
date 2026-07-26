# Multi-stage build for Majlisna frontend

# Stage 1: Build
FROM oven/bun:1-alpine AS build

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

# Build the application
ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN bun run build

# Stage 2: Production with Nginx
FROM nginx:alpine AS production

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

# Fill the CSP's telemetry allowlist, then prove the result still parses.
#
# Only the ORIGIN is taken from each value: the Sentry DSN carries a key before the
# host (https://<key>@host/<project>) and that key must not end up in a response
# header. An unset arg substitutes to nothing, which is a valid policy — that is the
# local-dev and E2E case.
#
# The two checks are not decoration: a leftover placeholder or a malformed generated
# directive would otherwise only surface as a container that refuses to start, or
# worse, as a policy the browser silently ignores.
#
# The syntax check wraps the generated file in a throwaway server block rather than
# running `nginx -t` on the real config: default.conf proxies to the `backend`
# upstream, which does not resolve until the compose network exists at runtime.
RUN set -eu; \
    api_origin="$(printf '%s' "${VITE_API_URL:-}" | sed -nE 's#^(https?://[^/]+).*#\1#p')"; \
    umami_origin="$(printf '%s' "${VITE_UMAMI_URL:-}" | sed -nE 's#^(https?://[^/]+).*#\1#p')"; \
    sentry_origin="$(printf '%s' "${VITE_SENTRY_DSN:-}" | sed -nE 's#^(https?://)([^@/]*@)?([^/]+).*#\1\3#p')"; \
    sed -i \
        -e "s#__API_CONNECT_SRC__#${api_origin}#" \
        -e "s#__TELEMETRY_SCRIPT_SRC__#${umami_origin}#" \
        -e "s#__TELEMETRY_CONNECT_SRC__#${umami_origin} ${sentry_origin}#" \
        /etc/nginx/security-headers.conf; \
    if grep -qE '__(API_CONNECT|TELEMETRY_(SCRIPT|CONNECT))_SRC__' /etc/nginx/security-headers.conf; then \
        echo "CSP placeholder left unsubstituted — refusing to ship a policy with a literal token"; \
        exit 1; \
    fi; \
    printf 'events {}\nhttp { server { listen 8081; location / { include /etc/nginx/security-headers.conf; return 204; } } }\n' \
        > /tmp/headers-syntax-check.conf; \
    nginx -t -c /tmp/headers-syntax-check.conf; \
    rm /tmp/headers-syntax-check.conf

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
