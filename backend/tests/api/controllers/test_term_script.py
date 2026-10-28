"""Tests for the TermScriptController (Arabic forms of game terms)."""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.term_script import TermScriptController
from majlisna.api.models.term_script import TermScript
from majlisna.api.schemas.term_script import TermScriptEntry


async def test_get_forms_returns_known_terms_in_one_query(session: AsyncSession, create_term_scripts, count_statements):
    """Several terms are resolved by a single SELECT; unknown terms are simply absent."""
    # Prepare
    await create_term_scripts({"Sabr": ("صبر", "صَبْر"), "Hajj": ("حج", "حَجّ"), "Yasin": ("يس", None)})
    controller = TermScriptController(session)
    counter = count_statements("term_script")

    # Act
    forms = await controller.get_forms(["Sabr", "Yasin", "Unknown", "Sabr"])

    # Assert
    assert counter.count == 1
    assert set(forms) == {"Sabr", "Yasin"}
    assert forms["Sabr"].ar == "صبر"
    assert forms["Sabr"].ar_vocalized == "صَبْر"
    assert forms["Yasin"].ar_vocalized is None


async def test_get_forms_with_nothing_to_look_up_issues_no_query(session: AsyncSession, count_statements):
    """No terms (or only blanks) means no round-trip at all — e.g. a spectator mid-game."""
    # Prepare
    controller = TermScriptController(session)
    counter = count_statements("term_script")

    # Act
    forms = await controller.get_forms([None, "", None])

    # Assert
    assert forms == {}
    assert counter.count == 0


async def test_upsert_inserts_updates_and_leaves_the_rest(session: AsyncSession, create_term_scripts):
    """Missing terms are inserted, changed ones updated, identical and unlisted ones untouched."""
    # Prepare
    await create_term_scripts({"Sabr": ("صبر", None), "Hajj": ("حج", "حَجّ"), "Kept": ("باقي", None)})
    controller = TermScriptController(session)

    # Act
    result = await controller.upsert(
        [
            TermScriptEntry(term="Sabr", ar="صبر", ar_vocalized="صَبْر"),
            TermScriptEntry(term="Hajj", ar="حج", ar_vocalized="حَجّ"),
            TermScriptEntry(term="Shukr", ar="شكر", ar_vocalized="شُكْر"),
        ]
    )

    # Assert
    assert (result.inserted, result.updated, result.unchanged) == (1, 1, 1)
    rows = {row.term: row for row in (await session.exec(select(TermScript))).all()}
    assert set(rows) == {"Sabr", "Hajj", "Shukr", "Kept"}
    assert rows["Sabr"].ar_vocalized == "صَبْر"
    assert rows["Shukr"].ar == "شكر"
    assert rows["Kept"].ar == "باقي"


async def test_upsert_twice_is_a_no_op(session: AsyncSession):
    """Running the same upsert again changes nothing."""
    # Prepare
    controller = TermScriptController(session)
    entries = [TermScriptEntry(term="Sabr", ar="صبر", ar_vocalized="صَبْر")]
    await controller.upsert(entries)

    # Act
    result = await controller.upsert(entries)

    # Assert
    assert (result.inserted, result.updated, result.unchanged) == (0, 0, 1)
    rows = (await session.exec(select(TermScript))).all()
    assert len(rows) == 1
