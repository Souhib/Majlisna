import os

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import Response

from majlisna.api.constants import RATE_LIMIT_USER_KEY_PREFIX
from majlisna.api.schemas.error import RateLimitExceededError, error_response

# Shared rate limiter instance. Registered on the app in app.py (app.state.limiter).
#
# In-memory storage keeps a separate counter per uvicorn worker, so with
# N workers the real limit becomes N× the configured value. Point this at
# Redis in production (RATE_LIMIT_STORAGE_URI=redis://...) so the limit is
# shared across workers. Defaults to in-memory for tests/single-process dev.
limiter = Limiter(
    key_func=get_remote_address,
    enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false",
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
)


def user_or_ip_key(request: Request) -> str:
    """Count a signed-in caller's requests per USER, anyone else's per IP.

    For endpoints behind ``get_current_user``, which records the authenticated id on
    ``request.state.user_id``. slowapi checks the limit inside the endpoint wrapper,
    i.e. after FastAPI has resolved the dependencies, so the id is there by then —
    and a forged token has already been answered 401, so it cannot pick a bucket.

    Per IP was wrong for these: a majlis is several phones on one home connection,
    so the whole table shared a single budget.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"{RATE_LIMIT_USER_KEY_PREFIX}{user_id}"
    return get_remote_address(request)


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
