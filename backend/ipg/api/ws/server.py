import socketio

from ipg.settings import Settings

_settings = Settings()  # type: ignore

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=[],  # CORS handled by FastAPI
    client_manager=socketio.AsyncRedisManager(_settings.redis_url),
    ping_interval=25,
    ping_timeout=10,
    logger=False,
    engineio_logger=False,
)

socketio_app = socketio.ASGIApp(sio, socketio_path="/socket.io")

# Register event handlers (side-effect import, must be after sio is created)
import ipg.api.ws.handlers  # noqa: E402, F401, PLC0415
