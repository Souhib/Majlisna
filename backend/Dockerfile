# Multi-stage build for the Majlisna backend

# Base images are pinned by digest, not by a floating tag: CI's E2E gate and Dokploy
# build their own images about 30 min apart, and `python:3.12-slim` / `uv:latest`
# could resolve to different bytes in between, so the image the gate tested was not
# the one that shipped (INFRA-17). Dependabot (.github/dependabot.yml, "docker") bumps
# the tag and the digest together.

# Stage 1: Base with Python (what every stage, the shipped one included, starts from)
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies (curl: the HEALTHCHECK below)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Install dependencies
FROM base AS dependencies

# uv lives in this stage only. Nothing in the running container calls it (the seed and
# purge scripts run with the venv's python), and it was 35 MB of the shipped image.
COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /usr/local/bin/uv

# The venv must point at THIS image's interpreter, which the production stage shares,
# never at a Python uv would download into the builder.
#
# UV_COMPILE_BYTECODE: the venv ships its .pyc files. PYTHONDONTWRITEBYTECODE (base stage)
# stops the running container from caching them, so without this every boot, and every
# worker, compiled fastapi, pydantic, sqlalchemy, logfire... from source again:
# `import main` took 1.5 to 2.5 times as long (measured 2026-10-31: 5.8 s against 3.5 s in
# this image, 3.8 s against 1.5 s on a laptop), paid by each of the 4 workers on 2 CPUs
# inside the ~10 s before they answer, i.e. inside each deploy's outage (PD-09). It costs
# about 45 MB of image.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1

# A compiler, for a dependency that would ever ship no wheel. Not Debian's python3-dev:
# that is Debian's own Python (3.13 on trixie) and its headers, never used to build for
# this image's /usr/local Python 3.12, which carries its own headers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Install exactly what uv.lock pins. `uv pip install .` used to re-resolve
# pyproject's floors on every build, so an unrelated rebuild silently picked up
# sqlmodel 0.0.48 — which rejects the deliberately naive RoomUserLink timestamps
# and turned every room creation into a 500. `--frozen` fails the build instead
# of drifting. The app runs from /app, so the project itself is not installed.
# INSTALL_DEV=true installs dev extras (faker, etc.) needed for E2E data seeding
COPY pyproject.toml uv.lock ./
ARG INSTALL_DEV=false
RUN if [ "$INSTALL_DEV" = "true" ]; then uv sync --frozen --no-install-project --no-cache --extra dev; else uv sync --frozen --no-install-project --no-cache --no-dev; fi

# Stage 3: Production
FROM base AS production

# The user exists BEFORE the copies, so they land owned by it (COPY --chown). A
# `chown -R` after them rewrote every file into a second 148 MB layer — about a
# quarter of the image, re-shipped on every code change. Only /app itself (created
# by WORKDIR as root, empty here) needs its owner changed.
RUN useradd -m -u 1000 appuser && chown appuser:appuser /app

# Copy installed venv from dependencies stage
COPY --from=dependencies --chown=appuser:appuser /app/.venv /app/.venv

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# The app's own bytecode too (a few MB, rebuilt with the code layer), for the same reason
# as UV_COMPILE_BYTECODE above.
RUN /app/.venv/bin/python -m compileall -q main.py majlisna

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Runtime knobs, each overridable from the compose environment:
#
# UVICORN_WORKERS — uvicorn worker processes.
#
# FORWARDED_ALLOW_IPS — the peers whose X-Forwarded-For / X-Forwarded-Proto uvicorn
#   believes (IPs or CIDRs, comma-separated). The default is loopback plus the private
#   ranges Docker networks are carved from: Traefik on dokploy-network and the frontend
#   nginx on the stack's network. It used to be '*', and with '*' uvicorn takes the
#   LEFT-MOST X-Forwarded-For entry, which the client writes (Cloudflare and Traefik
#   append to it): every per-IP rate limit was keyed on a value of the caller's choosing
#   (SEC F03, INFRA-07, PD-07). With this list the client is the first untrusted hop
#   from the right: the Cloudflare edge for proxied traffic, the real peer for a direct
#   hit, never the client-written entry. The limiter then reads CF-Connecting-IP only
#   when that peer is a Cloudflare address (rate_limit.client_ip_key). Never add a
#   Cloudflare range or '*' here. A list that misses the proxy's network puts every
#   visitor in the proxy's one rate-limit bucket: after a change, check one request's
#   client_ip in the logs. tests/api/test_trusted_proxies.py reads this line.
ENV UVICORN_WORKERS=4 \
    FORWARDED_ALLOW_IPS="127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

# The commit this image was built from, answered by /health as `version` (CI's promote
# job waits for it after a deploy). Declared last so a new commit invalidates no layer.
ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}

# `exec` replaces the shell with uvicorn, which becomes PID 1 and receives docker
# stop's SIGTERM. Without it two shells sat in front (the shell-form CMD wrapped this
# `sh -c` in another /bin/sh, and neither exec'd): SIGTERM never reached uvicorn,
# every stop and deploy waited out Docker's 10 s and ended in SIGKILL (exit 137), and
# the lifespan teardown never ran (INFRA-10, BDP-14). --timeout-graceful-shutdown
# bounds the drain of open requests and sockets; keep it under compose's
# stop_grace_period. `sh -c` stays for the ${...} expansion. The trust list falls back
# to the ENV default above when the variable reaches the container EMPTY (or unset):
# an empty `--forwarded-allow-ips ""` trusts no proxy, and every anonymous per-IP limit
# then shares Traefik's one bucket (review INT-01). Keep the two lists identical
# (tests/api/test_trusted_proxies.py::test_an_empty_value_falls_back_to_the_default_list).
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port 5000 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}\" --loop uvloop --http httptools --workers ${UVICORN_WORKERS} --timeout-graceful-shutdown 15"]
