from urllib.parse import urlsplit

import socketio
from loguru import logger

from majlisna.api.constants import SOCKET_ALLOW_ALL_ORIGINS
from majlisna.settings import Settings


def _get_redis_url() -> str:
    """Get Redis URL from settings, falling back to default for test environments."""
    try:
        return Settings().redis_url
    except OSError, ValueError:
        return "redis://localhost:6379/0"


def _as_origin(url: str) -> str:
    """``scheme://host[:port]``, lower-cased: what a browser sends as ``Origin``.

    A configured ``https://majlisna.app/`` (trailing slash, or a path) would otherwise
    match no browser's Origin at all, and refuse every socket.
    """
    text = url.strip()
    parts = urlsplit(text)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme.lower()}://{parts.netloc.lower()}"
    return text.rstrip("/")


def socket_allowed_origins(settings: Settings) -> list[str]:
    """The browser origins whose pages may open a socket (SEC F12).

    ``cors_origins`` plus ``frontend_url``, de-duplicated in order. ``frontend_url`` is
    always there: the page connects to its own origin (``io(window.location.origin)``,
    proxied to the backend by nginx / Traefik), and a deployment whose REST API is
    same-origin too has no reason to list that origin in CORS_ORIGINS — without it,
    every socket would be refused. A ``*`` in ``cors_origins`` (development) keeps
    meaning "any origin", as python-socketio defines it.
    """
    configured = [*settings.cors_origins, settings.frontend_url]
    origins = [_as_origin(url) for url in configured if url.strip()]
    if SOCKET_ALLOW_ALL_ORIGINS in origins:
        return [SOCKET_ALLOW_ALL_ORIGINS]
    return list(dict.fromkeys(origins))


def _configured_allowed_origins() -> list[str]:
    """The list for this process; the default front end when Settings cannot load
    (a test environment without a .env, like ``_get_redis_url``) — never allow-all."""
    try:
        settings = Settings()
    except OSError, ValueError:
        return [_as_origin(Settings.model_fields["frontend_url"].default)]
    return socket_allowed_origins(settings)


SOCKET_ALLOWED_ORIGINS = _configured_allowed_origins()
# Once per process, at startup: a refused socket is otherwise silent on the server
# (python-engineio logs it once, and only with its logger on), and a production
# FRONTEND_URL that is not the page's origin refuses every player.
logger.info("Socket.IO accepts handshakes from the origins {}", SOCKET_ALLOWED_ORIGINS)

sio = socketio.AsyncServer(
    async_mode="asgi",
    # Origin validation of the handshake (HTTP polling and WebSocket alike). In
    # python-engineio an EMPTY list does not mean "same origin only", it switches CORS
    # handling — the origin check included — off entirely: any page on the web could
    # open a socket (SEC F12). None (its default) derives the one allowed origin from the
    # request's own scheme and Host, and behind Cloudflare's Flexible TLS the backend
    # sees http:// while the page is https:// — every production socket would be
    # refused. Hence the explicit list. A request without an Origin header (a native
    # client) is not checked: browsers always send one on a cross-site request.
    #
    # The FastAPI CORSMiddleware wraps this mount too (Starlette middleware wraps every
    # route, mounts included) and adds its own CORS headers to the polling responses,
    # so a CROSS-origin polling client would see Access-Control-Allow-Origin twice.
    # No client polls cross-origin — every page connects to its own origin — so it is
    # harmless today; a cross-origin socket client would need one of the two to stop.
    cors_allowed_origins=SOCKET_ALLOWED_ORIGINS,
    client_manager=socketio.AsyncRedisManager(_get_redis_url()),
    ping_interval=15,
    ping_timeout=10,
    logger=False,
    engineio_logger=False,
)

socketio_app = socketio.ASGIApp(sio, socketio_path="/socket.io")

# Register event handlers (side-effect import, must be after sio is created)
import majlisna.api.ws.handlers  # noqa: E402, F401, PLC0415
