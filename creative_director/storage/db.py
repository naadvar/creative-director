from contextlib import contextmanager
from typing import Iterator

from loguru import logger
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from creative_director.config import settings
from creative_director.storage.models import (
    Base,
    ConnectedAccount,
    CreatorIdea,
    Event,
    NoteFeedback,
    Upload,
    User,
)


# The read-only corpus DB (re-fetched from R2 on deploy) and the WRITABLE user
# store (users / feedback / uploads) are SEPARATE files. A corpus redeploy
# overwrites the corpus DB but must never touch real signups + uploads, so those
# models are bound to their own engine and live on the persistent volume.
engine = create_engine(settings.database_url, echo=False, future=True)
userdata_engine = create_engine(settings.userdata_url, echo=False, future=True)

# Models whose rows are user-generated and must survive corpus redeploys.
USER_MODELS = (User, NoteFeedback, ConnectedAccount, Upload, CreatorIdea, Event)


def _wal_pragmas(dbapi_conn) -> None:  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=60000")  # wait up to 60s for a lock
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


if str(settings.database_url).startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _corpus_pragmas(dbapi_conn, _record):  # noqa: ANN001
        _wal_pragmas(dbapi_conn)


if str(settings.userdata_url).startswith("sqlite"):

    @event.listens_for(userdata_engine, "connect")
    def _userdata_pragmas(dbapi_conn, _record):  # noqa: ANN001
        _wal_pragmas(dbapi_conn)


# Per-model binds: a single Session routes the user models to userdata_engine and
# everything else to the corpus engine, so existing session_scope() call sites keep
# working without change. (No queries JOIN across the two DBs.)
SessionLocal = sessionmaker(
    bind=engine,
    binds={m: userdata_engine for m in USER_MODELS},
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def init_db() -> None:
    # Corpus tables on the corpus engine; the writable user tables on their own
    # engine. (create_all also makes harmless idle copies of the user tables in the
    # corpus DB — they're never read, the binds route every user query to userdata.)
    Base.metadata.create_all(engine)
    Base.metadata.create_all(
        userdata_engine, tables=[m.__table__ for m in USER_MODELS]
    )
    _ensure_runtime_columns()
    _migrate_userdata_once()


# Columns added AFTER their table first shipped. create_all() never alters an
# existing table, so these idempotent ADDs keep a long-lived SQLite file in sync
# with the model on every boot (and on fresh deploys, which is a no-op).
_RUNTIME_COLUMNS = (
    ("video_features", "craft_read", "JSON"),
    ("videos", "uploaded_by_user_id", "INTEGER"),
)

# Same, but for tables on the WRITABLE userdata engine (the uploads table).
_USERDATA_RUNTIME_COLUMNS = (
    ("uploads", "prior_video_id", "VARCHAR(64)"),
    ("uploads", "revision_verdict", "JSON"),
    ("uploads", "idea_id", "VARCHAR(64)"),
)


def _ensure_runtime_columns() -> None:
    if str(settings.database_url).startswith("sqlite"):
        with engine.begin() as conn:
            for table, col, decl in _RUNTIME_COLUMNS:
                have = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
                if col not in have:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    if str(settings.userdata_url).startswith("sqlite"):
        with userdata_engine.begin() as conn:
            for table, col, decl in _USERDATA_RUNTIME_COLUMNS:
                have = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
                if col not in have:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def _migrate_userdata_once() -> None:
    """One-time lift of legacy user rows from the corpus DB into userdata.db.

    Before the writable store was split out, users / note_feedback /
    connected_accounts lived in the corpus DB. On the first boot with the split,
    copy any existing rows over (ATTACH + INSERT...SELECT) so no signup is lost,
    then leave the corpus copies idle."""
    if not (str(settings.database_url).startswith("sqlite")
            and str(settings.userdata_url).startswith("sqlite")):
        return
    corpus_path = settings.database_url.split("///", 1)[-1]
    try:
        with userdata_engine.begin() as conn:
            n = conn.exec_driver_sql("SELECT COUNT(*) FROM users").scalar() or 0
            if n > 0:
                return  # userdata already populated — nothing to migrate
            conn.exec_driver_sql(f"ATTACH DATABASE '{corpus_path}' AS corpus")
            copied = {}
            for table in ("users", "note_feedback", "connected_accounts"):
                try:
                    cols = [r[1] for r in conn.exec_driver_sql(
                        f"PRAGMA table_info({table})")]
                    has_src = conn.exec_driver_sql(
                        "SELECT name FROM corpus.sqlite_master "
                        "WHERE type='table' AND name=?", (table,)).fetchone()
                    if not cols or not has_src:
                        continue
                    cl = ",".join(cols)
                    conn.exec_driver_sql(
                        f"INSERT OR IGNORE INTO {table} ({cl}) "
                        f"SELECT {cl} FROM corpus.{table}")
                    copied[table] = conn.exec_driver_sql(
                        f"SELECT COUNT(*) FROM {table}").scalar()
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"userdata migrate {table}: {type(e).__name__}: {e}")
            conn.exec_driver_sql("DETACH DATABASE corpus")
        if copied:
            logger.info(f"userdata.db seeded from corpus: {copied}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"userdata migration skipped: {type(e).__name__}: {e}")


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
