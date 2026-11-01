"""WP-05: a browser's regional language tag (``ar-SA``, ``fr-FR``) reaches the API as ``?lang=``.

The REST ``lang`` parameter is a plain string, and the frontend used to send the raw
browser tag. The content resolver now reads a regional tag as its language, so the real
stack — route, controller, database — answers the Arabic hint for ``ar-SA`` instead of
the English fallback.
"""

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from freezegun import freeze_time
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.rate_limit import limiter
from majlisna.dependencies import get_session, get_settings
from majlisna.settings import Settings

BASE_URL = "/api/v1/daily-word"
NOW = "2026-11-10T09:00:00Z"  # noon in Makkah: the day does not turn during the test
RUNGS = {str(rung): {"en": f"rung{rung}-en", "fr": f"rung{rung}-fr", "ar": f"درجة{rung}"} for rung in range(1, 7)}


@pytest.fixture(autouse=True)
def _frozen_clock(test_app: FastAPI):  # noqa: ARG001 — build (and import) the app before the clock freezes
    with freeze_time(NOW):
        yield


@pytest_asyncio.fixture(name="client")
async def get_client(
    test_app: FastAPI, session: AsyncSession, test_settings: Settings
) -> AsyncGenerator[httpx.AsyncClient]:
    """An async client on the real app and the test database."""

    async def _test_session() -> AsyncGenerator[AsyncSession]:
        yield session

    test_app.dependency_overrides[get_session] = _test_session
    test_app.dependency_overrides[get_settings] = lambda: test_settings
    limiter.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        yield client
    limiter.reset()
    test_app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("lang", "expected_hint"),
    [("ar-SA", "درجة1"), ("ar-MA", "درجة1"), ("fr-FR", "rung1-fr"), ("en-GB", "rung1-en"), ("de-DE", "rung1-en")],
)
async def test_daily_word_reads_a_regional_lang_as_its_language(
    client: httpx.AsyncClient, create_quiz_word, lang: str, expected_hint: str
) -> None:
    """GET /daily-word?lang=ar-SA answers the Arabic hint (it used to answer the English one)."""
    # Prepare
    await create_quiz_word(word_en="Qalamzar", word_ar="قلمزار", word_fr="Qalamzare", category="Places", hints=RUNGS)

    # Act
    response = await client.get(BASE_URL, params={"lang": lang})

    # Assert
    assert response.status_code == 200
    assert response.json()["hints"] == [expected_hint]
