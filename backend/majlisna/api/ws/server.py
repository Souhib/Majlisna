import socketio

from majlisna.settings import Settings


def _get_redis_url() -> str:
    """Get Redis URL from settings, falling back to default for test environments."""
    try:
        return Settings().redis_url  # type: ignore
    except Exception:
        return "redis://localhost:6379/0"


sio = socketio.AsyncServer(
    async_mode="asgi",
    # The Socket.IO app is mounted separately (app.mount("/socket.io", ...)),
    # so it does NOT pass through FastAPI's CORSMiddleware. An empty list means
    # only same-origin handshakes are accepted, which is what we rely on: the
    # browser hits <origin>/socket.io directly in prod, and the Vite dev proxy
    # makes it same-origin in development. Add explicit origins here if the
    # frontend ever needs to connect cross-origin.
    cors_allowed_origins=[],
    client_manager=socketio.AsyncRedisManager(_get_redis_url()),
    ping_interval=15,
    ping_timeout=10,
    logger=False,
    engineio_logger=False,
)

socketio_app = socketio.ASGIApp(sio, socketio_path="/socket.io")

# Register event handlers (side-effect import, must be after sio is created)
import majlisna.api.ws.handlers  # noqa: E402, F401, PLC0415
