"""SEC F12: the Socket.IO handshake checks the browser's Origin.

``ws/server.py`` passed ``cors_allowed_origins=[]`` under a comment saying it meant
"same-origin only". In python-engineio an empty list means the opposite: CORS
handling, origin validation included, is switched off — a handshake from any page on
the web was accepted (the security verifier's probe: 200 with a sid for a foreign
Origin). Today the socket authenticates with an explicit token, not a cookie, so this
is defence in depth; it is what stands between a future cookie-authenticated socket
and cross-site WebSocket hijacking.

The server now passes ``settings.cors_origins`` plus ``settings.frontend_url`` (always:
the page connects to its own origin, and CORS_ORIGINS need not list it when the REST
API is same-origin too). A ``*`` in CORS_ORIGINS (development) stays allow-all.
"""

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from majlisna.api.ws.server import sio, socket_allowed_origins
from majlisna.settings import Settings

FRONTEND = "https://majlisna.app"


def _settings(*, cors_origins: str, frontend_url: str = FRONTEND) -> Settings:
    """Explicit values: the test environment's own .env files say CORS_ORIGINS=*."""
    return Settings(database_url="sqlite+aiosqlite:///:memory:", cors_origins=cors_origins, frontend_url=frontend_url)


# ─── The list ────────────────────────────────────────────────────────────────


def test_the_front_end_is_accepted_even_when_cors_origins_does_not_list_it() -> None:
    """A same-origin deployment has no reason to put its own origin in CORS_ORIGINS;
    without frontend_url every browser socket would be refused."""
    # Act
    origins = socket_allowed_origins(_settings(cors_origins=""))

    # Assert
    assert origins == [FRONTEND]


def test_the_lists_are_merged_and_written_as_a_browser_writes_an_origin() -> None:
    """De-duplicated, in order, and reduced to scheme://host[:port] — a browser's Origin
    never carries a path or a trailing slash, so ``https://majlisna.app/`` would match nothing."""
    # Act
    origins = socket_allowed_origins(
        _settings(cors_origins="https://majlisna.app,http://localhost:3049/", frontend_url="https://Majlisna.app/")
    )

    # Assert
    assert origins == ["https://majlisna.app", "http://localhost:3049"]


def test_a_wildcard_in_cors_origins_stays_allow_all() -> None:
    """Development's CORS_ORIGINS=* keeps meaning "any origin", as python-socketio defines it."""
    # Act
    origins = socket_allowed_origins(_settings(cors_origins="*"))

    # Assert
    assert origins == ["*"]


def test_the_server_is_built_with_the_configured_list() -> None:
    """Port of tests_static::test_f12_server_passes_empty_origin_list: never ``[]`` again."""
    # Act
    configured = sio.eio.cors_allowed_origins

    # Assert
    assert configured == socket_allowed_origins(Settings())
    assert configured != []


# ─── The handshake (port of tests_http::test_f12_engineio_handshake_accepts_foreign_origin) ──


@pytest.fixture(name="production_origins")
def get_production_origins(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """The real server and app, holding the list a production configuration gives.

    The Redis client manager and the ping monitor are kept from starting (a handshake
    would otherwise launch both), and the Engine.IO sessions the test opens are dropped.
    """
    settings = _settings(cors_origins="https://api.majlisna.app")
    monkeypatch.setattr(sio.eio, "cors_allowed_origins", socket_allowed_origins(settings))
    monkeypatch.setattr(sio, "manager_initialized", True)
    monkeypatch.setattr(sio.eio, "start_service_task", False)
    before = set(sio.eio.sockets)
    yield settings
    for sid in set(sio.eio.sockets) - before:
        sio.eio.sockets.pop(sid, None)
        sio.environ.pop(sid, None)


async def _handshake(app: FastAPI, origin: str | None) -> httpx.Response:
    headers = {"Origin": origin} if origin else {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/socket.io/", params={"EIO": "4", "transport": "polling"}, headers=headers)


async def test_a_handshake_from_a_foreign_page_is_refused(test_app: FastAPI, production_origins: Settings) -> None:  # noqa: ARG001
    """A page on another site opens no Engine.IO session."""
    # Act
    response = await _handshake(test_app, "https://evil.example")

    # Assert
    assert response.status_code == 400
    assert "not an accepted origin" in response.text
    assert '"sid"' not in response.text


async def test_a_handshake_from_the_front_end_is_accepted(test_app: FastAPI, production_origins: Settings) -> None:
    """The app's own pages connect as before."""
    # Act
    response = await _handshake(test_app, production_origins.frontend_url)

    # Assert
    assert response.status_code == 200
    assert response.text.startswith("0")
    assert '"sid"' in response.text


async def test_a_handshake_without_an_origin_is_accepted(test_app: FastAPI, production_origins: Settings) -> None:  # noqa: ARG001
    """A browser always sends Origin on a cross-site request; a client that sends none
    (a native app, a test script) is not a browser page and is not refused."""
    # Act
    response = await _handshake(test_app, None)

    # Assert
    assert response.status_code == 200
    assert '"sid"' in response.text
