from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={
        "check_same_thread": False,  # SQLite only
        "timeout": 30,               # wait up to 30s for a write lock before raising
    },
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):
    """
    Set per-connection SQLite pragmas.

    WAL mode: readers don't block writers and writers don't block readers.
    Critical for Railway zero-downtime deploys where the old instance may
    be serving requests (holding read locks) while the new one starts up.

    busy_timeout: if a write lock can't be acquired immediately, SQLite
    retries for up to N milliseconds before raising OperationalError.
    This prevents startup crashes when the old instance briefly holds a
    write lock during an Archer sync.
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=20000")   # 20 seconds in milliseconds
    cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
