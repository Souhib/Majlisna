import asyncio
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import FastAPI

from majlisna.api.controllers.disconnect import disconnect_checker_loop
from majlisna.api.ws.handlers import audit_local_socket_memberships
from majlisna.api.ws.notify import fire_notify_game_changed, fire_notify_room_changed
from majlisna.app import create_app
from majlisna.database import create_app_engine, create_schema, dispose_engine
from majlisna.logger_config import configure_logger
from majlisna.settings import Settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan context manager."""
    settings = Settings()
    configure_logger(
        log_level=settings.log_level,
        serialize=settings.environment == "production",
    )
    engine = await create_app_engine(settings)
    # Every worker runs this; they take turns under an advisory lock (INFRA-13).
    await create_schema(settings, engine)

    # Start background disconnect checker loop
    checker_task = asyncio.create_task(
        disconnect_checker_loop(
            engine,
            on_room_changed=fire_notify_room_changed,
            on_game_changed=fire_notify_game_changed,
            # every worker cuts its own sockets whose seat is gone (a kick on another worker)
            on_worker_tick=audit_local_socket_memberships,
        )
    )

    yield

    checker_task.cancel()
    with suppress(asyncio.CancelledError):
        await checker_task
    await dispose_engine()


app = create_app(lifespan=lifespan)


if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(app, port=settings.port)
