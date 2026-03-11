# Multi-stage build for IPG frontend
# Build stage uses x86 (Tailwind CSS v4 Oxide engine needs x86 native binaries)
# Production stage uses target platform (ARM64 on VPS)

# Stage 1: Build (force x86 — Tailwind CSS v4 Oxide has no ARM64 support)
FROM --platform=linux/amd64 oven/bun:1-alpine AS build

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

# Set environment variables for build
ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN}
ENV VITE_UMAMI_URL=${VITE_UMAMI_URL}
ENV VITE_UMAMI_WEBSITE_ID=${VITE_UMAMI_WEBSITE_ID}
ENV VITE_GOOGLE_MAPS_API_KEY=${VITE_GOOGLE_MAPS_API_KEY}

# Build the application
ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN DEBUG=vite:* bun run build 2>&1 || { echo "=== BUILD FAILED, retrying with verbose ===" && npx vite build --debug 2>&1; exit 1; }

# Stage 2: Production with Nginx
FROM nginx:alpine AS production

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
