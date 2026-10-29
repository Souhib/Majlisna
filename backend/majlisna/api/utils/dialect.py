"""The dialect's own INSERT, which is what carries ``on_conflict_do_nothing``.

PostgreSQL in production, SQLite in dev and the default test run — the only two this
project runs on. Chosen from the session's bind, so one code path serves both.
"""

from sqlalchemy.dialects.postgresql import Insert as PostgresqlInsert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import Insert as SqliteInsert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel.ext.asyncio.session import AsyncSession


def dialect_insert(session: AsyncSession, table: type) -> PostgresqlInsert | SqliteInsert:
    """``INSERT INTO table`` in the session's dialect (postgresql, else sqlite)."""
    bind = session.bind
    if bind is not None and bind.dialect.name == "postgresql":
        return postgresql_insert(table)
    return sqlite_insert(table)
