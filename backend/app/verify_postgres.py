"""Integration smoke check for a disposable, seeded PostgreSQL database (CI only)."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from .config import get_settings
from .main import app

if __name__ == "__main__":
    if not get_settings().database_url.startswith("postgresql") or get_settings().app_env == "production":
        raise SystemExit("Run only against a disposable PostgreSQL database")
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": "admin@lexpickup.club", "password": "PickupPro2026!"}
            ).status_code
            == 200
        )
        created = client.post(
            "/api/v1/players", json={"name": "Postgres sequence verification", "team_id": 1}
        )
        assert created.status_code == 201, created.text
        assert created.json()["id"] > 24
        response = client.post(
            "/api/v1/matches",
            json={
                "title": "PostgreSQL verification",
                "starts_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            },
        )
        assert response.status_code == 201, response.text
        mid = response.json()[0]["id"]
        assert client.put(f"/api/v1/matches/{mid}/rsvp", json={"status": "going"}).status_code == 200
        assert client.get("/api/v1/stats").json()["matches_played"] == 18
        assert client.get("/api/v1/export/players").status_code == 200
        print("PostgreSQL migration, seed, sequence, match, RSVP, statistics, and export checks passed.")
