import os
from datetime import datetime, timedelta, timezone

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DEMO_ENABLED"] = "false"
os.environ["CORS_ORIGINS"] = '["http://localhost:5173"]'
os.environ["REGISTRATION_ENABLED"] = "true"
os.environ["COOKIE_SECURE"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Match, Player, Season, Team, User  # noqa: E402
from app.security import _attempts, password_hasher  # noqa: E402
from app.storage.factory import get_store  # noqa: E402
from app.storage.sql import SqlStore  # noqa: E402

PASSWORD = "TestPassword2026!"
HASH = password_hasher.hash(PASSWORD)


@pytest.fixture
def session_factory():
    integration_url = os.environ.get("LEX_TEST_DATABASE_URL")
    if integration_url:
        if not (make_url(integration_url).database or "").startswith("lex_test_"):
            raise RuntimeError("Integration tests require a disposable database named lex_test_*")
        engine = create_engine(integration_url)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(engine, "connect")
        def fk(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    with factory() as db:
        db.add_all(
            [
                Team(id=1, name="Old Gentlemen", short_name="OG", color="#245b46", motto="Experience"),
                Team(id=2, name="Young Boys", short_name="YB", color="#dbab53", motto="Energy"),
                Season(id=1, name="Test season", active=True),
            ]
        )
        db.flush()
        db.add_all(
            [
                Player(
                    id=i,
                    name=f"Player {i}",
                    team_id=1 if i <= 6 else 2,
                    positions="GK" if i in (1, 7) else "CM,ST",
                    skill=5 + i / 3,
                )
                for i in range(1, 13)
            ]
        )
        db.flush()
        db.add_all(
            [
                User(id=1, email="admin@example.com", password_hash=HASH, role="admin", player_id=1),
                User(id=2, email="player@example.com", password_hash=HASH, role="player", player_id=2),
                User(id=3, email="captain@example.com", password_hash=HASH, role="captain", player_id=7),
            ]
        )
        db.flush()
        db.add(
            Match(
                id=1,
                season_id=1,
                starts_at=datetime.now(timezone.utc) + timedelta(days=3),
                capacity=10,
                formation="2-2",
                created_by=1,
            )
        )
        db.flush()
        if integration_url:
            # These fixtures deliberately use fixed IDs; PostgreSQL sequences need to follow them.
            for table in ("teams", "seasons", "players", "users", "matches"):
                db.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}))"
                    )
                )
        db.commit()
    yield factory
    if integration_url:
        Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(session_factory):
    app.dependency_overrides[get_store] = lambda: SqlStore(session_factory)
    _attempts.clear()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def admin(client):
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    return client


@pytest.fixture
def player(client):
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "player@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    return client
