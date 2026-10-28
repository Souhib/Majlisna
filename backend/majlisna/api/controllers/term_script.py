from collections.abc import Iterable, Sequence

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.term_script import TermScript
from majlisna.api.schemas.term_script import TermScriptEntry, TermScriptForms, TermScriptUpsertResult


class TermScriptController:
    """Arabic forms of the Latin game terms (see ``TermScript``)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_forms(self, terms: Iterable[str | None]) -> dict[str, TermScriptForms]:
        """Look up the Arabic forms of several terms in ONE query.

        Terms without a row are simply absent from the result, so callers answer
        ``None`` for them. No query is issued when there is nothing to look up.
        """
        wanted = sorted({term for term in terms if term})
        if not wanted:
            return {}
        rows = (await self.session.exec(select(TermScript).where(TermScript.term.in_(wanted)))).all()  # ty: ignore[unresolved-attribute]
        return {row.term: TermScriptForms(ar=row.ar, ar_vocalized=row.ar_vocalized) for row in rows}

    async def upsert(self, entries: Sequence[TermScriptEntry]) -> TermScriptUpsertResult:
        """Insert the missing terms and update the changed ones, idempotently.

        Rows for terms not in ``entries`` are left untouched. Commits once.
        """
        by_term = {entry.term: entry for entry in entries}
        if not by_term:
            return TermScriptUpsertResult(inserted=0, updated=0, unchanged=0)

        existing = {
            row.term: row
            for row in (
                await self.session.exec(select(TermScript).where(TermScript.term.in_(list(by_term))))  # ty: ignore[unresolved-attribute]
            ).all()
        }

        inserted = updated = unchanged = 0
        for term, entry in by_term.items():
            row = existing.get(term)
            if row is None:
                self.session.add(TermScript(term=term, ar=entry.ar, ar_vocalized=entry.ar_vocalized))
                inserted += 1
            elif row.ar != entry.ar or row.ar_vocalized != entry.ar_vocalized:
                row.ar = entry.ar
                row.ar_vocalized = entry.ar_vocalized
                self.session.add(row)
                updated += 1
            else:
                unchanged += 1

        await self.session.commit()
        return TermScriptUpsertResult(inserted=inserted, updated=updated, unchanged=unchanged)
