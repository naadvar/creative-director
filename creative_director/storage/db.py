from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from creative_director.config import settings
from creative_director.storage.models import Base


engine = create_engine(settings.database_url, echo=False, future=True)


# WAL + a long busy-timeout so multiple parallel extraction workers can write
# features to the same SQLite file without "database is locked" failures
# (writes are tiny and infrequent, so they just queue). No-op for non-sqlite.
if str(settings.database_url).startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=60000")  # wait up to 60s for a lock
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def init_db() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
