from fastapi import Request
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


url = get_settings().database_url
engine = (
    create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {},
        pool_pre_ping=True,
    )
    if get_settings().database_provider == "sql"
    else None
)
if engine is not None and url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def sqlite_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request):
    if engine is None:
        raise RuntimeError("SQL sessions are disabled for the selected provider")
    with SessionLocal() as session:
        if url.startswith("sqlite") and request.method not in ("GET", "HEAD", "OPTIONS"):
            # SQLite has no row locks. Serialize local writes before reads to avoid overbooking/lost scores.
            session.execute(text("BEGIN IMMEDIATE"))
        yield session
