import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from majlisna.app import create_app
from majlisna.database import create_app_engine, create_db_and_tables, dispose_engine
from majlisna.logger_config import configure_logger
from majlisna.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    settings = Settings()  # type: ignore
    configure_logger(
        log_level=settings.log_level,
        serialize=settings.environment == "production",
    )
    engine = await create_app_engine(settings)
    await create_db_and_tables(engine)

    # Start background disconnect checker loop
    from majlisna.api.controllers.disconnect import disconnect_checker_loop
    from majlisna.api.ws.notify import fire_notify_game_changed, fire_notify_room_changed

    checker_task = asyncio.create_task(
        disconnect_checker_loop(
            engine,
            on_room_changed=fire_notify_room_changed,
            on_game_changed=lambda gid: fire_notify_game_changed(gid),
        )
    )

    yield

    checker_task.cancel()
    try:
        await checker_task
    except asyncio.CancelledError:
        pass
    await dispose_engine()


app = create_app(lifespan=lifespan)


if __name__ == "__main__":
    settings = Settings()  # type: ignore
    uvicorn.run(app, port=settings.port)
