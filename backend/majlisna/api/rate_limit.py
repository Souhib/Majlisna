import ipaddress
import os

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import Response

from majlisna.api.constants import CF_CONNECTING_IP_HEADER, CLOUDFLARE_IP_RANGES, RATE_LIMIT_USER_KEY_PREFIX
from majlisna.api.schemas.error import RateLimitExceededError, error_response

_CLOUDFLARE_NETWORKS = tuple(ipaddress.ip_network(cidr) for cidr in CLOUDFLARE_IP_RANGES)


def _is_cloudflare_edge(host: str) -> bool:
    """Whether ``host`` is one of Cloudflare's published edge addresses (an IPv4-mapped IPv6 too)."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return any(address in network for network in _CLOUDFLARE_NETWORKS)


def client_ip_key(request: Request) -> str:
    """The visitor's address: ``CF-Connecting-IP`` when Cloudflare relayed the request, else the peer.

    Every request reaches production through a Cloudflare edge, so the peer
    (``request.client.host``, after uvicorn's proxy-header middleware trusts Traefik) is
    an edge address: unrelated visitors behind one edge shared one budget, and an
    attacker spread over edges got one budget per edge (SEC F03, INFRA-07, PD-07 — 37
    edges carried all the traffic). Cloudflare sets ``CF-Connecting-IP`` to the visitor
    and overwrites any copy the client sent.

    The header is read ONLY when the peer is inside ``CLOUDFLARE_IP_RANGES``: anyone
    else can write it, so a direct caller (one that skips Cloudflare) is keyed on its
    own address whatever it claims — which is why this is safe without locking the
    origin to Cloudflare. It relies on uvicorn's ``--forwarded-allow-ips`` trusting only
    the proxy network (backend/Dockerfile), so ``client.host`` is not client-written.
    A missing or malformed header falls back to the peer.
    """
    peer = get_remote_address(request)
    if not _is_cloudflare_edge(peer):
        return peer
    visitor = request.headers.get(CF_CONNECTING_IP_HEADER, "").strip()
    try:
        return str(ipaddress.ip_address(visitor))
    except ValueError:
        return peer


def build_limiter(*, storage_uri: str, enabled: bool) -> Limiter:
    """The app's limiter (and any test's): keyed on ``client_ip_key``.

    ``in_memory_fallback_enabled``: when the storage (Redis in production) cannot be
    reached, the counters fall back to this worker's memory — the limits still hold,
    per worker — and slowapi re-checks the storage with a backoff and returns to it
    once it answers. slowapi's default raises instead: with Redis down every limited
    route answered 500 — sign-in, room joins, and the gameplay routes this release
    limits (timer-expired, Kalimat answers, hint views) — while the docs promised the
    app works without Redis (review INT-02).
    """
    return Limiter(
        key_func=client_ip_key,
        enabled=enabled,
        storage_uri=storage_uri,
        in_memory_fallback_enabled=True,
    )


# Shared rate limiter instance. Registered on the app in app.py (app.state.limiter).
#
# In-memory storage keeps a separate counter per uvicorn worker, so with
# N workers the real limit becomes N× the configured value. Point this at
# Redis in production (RATE_LIMIT_STORAGE_URI=redis://...) so the limit is
# shared across workers. Defaults to in-memory for tests/single-process dev.
limiter = build_limiter(
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
    enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false",
)


def user_or_ip_key(request: Request) -> str:
    """Count a signed-in caller's requests per USER, anyone else's per IP.

    For endpoints behind ``get_current_user``, which records the authenticated id on
    ``request.state.user_id``. slowapi checks the limit inside the endpoint wrapper,
    i.e. after FastAPI has resolved the dependencies, so the id is there by then —
    and a forged token has already been answered 401, so it cannot pick a bucket.

    Per IP was wrong for these: a majlis is several phones on one home connection,
    so the whole table shared a single budget. Anyone else is keyed on
    ``client_ip_key``.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"{RATE_LIMIT_USER_KEY_PREFIX}{user_id}"
    return client_ip_key(request)


def refresh_sub_key(request: Request) -> str:
    """``/auth/refresh`` counts per ACCOUNT the refresh token names, else per client address (FR-3 d).

    Every page load spends a refresh, so ten loads in a minute from one home connection
    (a majlis opening the share link) answered the eleventh a 429 — and a tab whose
    load-time refresh failed was signed out 15 minutes later, mid-game. The account is
    recorded by ``dependencies.get_presented_refresh_token`` (signature-checked, only to
    pick the bucket); a token that does not decode is counted per address.
    """
    subject = getattr(request.state, "refresh_token_sub", None)
    if subject:
        return f"{RATE_LIMIT_USER_KEY_PREFIX}{subject}"
    return client_ip_key(request)


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """429 in the same envelope as every other error (``error_key`` included).

    slowapi's default answered ``{"error": "Rate limit exceeded: 30 per 1 minute"}``,
    which the client cannot translate: an Arabic or French player got raw English.
    The rate-limit headers are injected exactly as the default handler does.
    """
    limit = str(exc.detail) if isinstance(exc, RateLimitExceeded) else str(exc)
    response = error_response(RateLimitExceededError(limit=limit))
    current_limit = getattr(request.state, "view_rate_limit", None)
    if current_limit is None:
        return response
    # slowapi's own header helper — what its default handler calls.
    return request.app.state.limiter._inject_headers(response, current_limit)
