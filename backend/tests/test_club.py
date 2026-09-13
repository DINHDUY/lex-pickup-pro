import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import jwt
import pytest
from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.models import RSVP, Invitation, Match, Player, Rating, Season
from app.security import COOKIE, _attempts

from .conftest import PASSWORD

API = "/api/v1"


def lineup():
    return {
        "formation": "2-2",
        "players": [
            {"player_id": i + (0 if side == "home" else 6), "side": side, "slot": i - 1}
            for side in ("home", "away")
            for i in range(1, 6)
        ],
    }


def start(admin):
    assert admin.put(f"{API}/matches/1/lineup", json=lineup()).status_code == 200
    assert (
        admin.patch(
            f"{API}/matches/1/result", json={"home_score": 0, "away_score": 0, "status": "live"}
        ).status_code
        == 200
    )


def complete(admin, home=0, away=0):
    return admin.patch(
        f"{API}/matches/1/result", json={"home_score": home, "away_score": away, "status": "completed"}
    )


def test_authentication_cookie_and_logout(client):
    assert client.get(f"{API}/players").status_code == 401
    for email in ("admin@example.com", "unknown@example.com"):
        response = client.post(f"{API}/auth/login", json={"email": email, "password": "wrong"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Email or password is incorrect"
    response = client.post(f"{API}/auth/login", json={"email": "ADMIN@example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert "password" not in response.text and "token" not in response.text
    assert client.get(f"{API}/auth/me").json()["role"] == "admin"
    assert client.post(f"{API}/auth/logout").status_code == 204
    assert client.get(f"{API}/auth/me").status_code == 401


def test_public_config_reports_facebook_auth_toggle(client):
    config = client.get(f"{API}/config").json()
    assert "facebook_auth_enabled" in config
    assert config["facebook_auth_enabled"] is False


def test_facebook_callback_creates_user_for_valid_oauth_flow(client, session_factory, monkeypatch):
    monkeypatch.setattr("app.main.settings.facebook_auth_enabled", True, raising=False)
    monkeypatch.setattr("app.main.settings.facebook_app_id", "app-123", raising=False)
    monkeypatch.setattr("app.main.settings.facebook_app_secret", "secret-123", raising=False)
    monkeypatch.setattr(
        "app.main.settings.facebook_redirect_uri", "https://club.example.com/login", raising=False
    )
    monkeypatch.setattr("app.main.settings.registration_enabled", True, raising=False)

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200

        def json(self):
            return self._payload

    def fake_post(url, data=None, timeout=None):
        assert "oauth/access_token" in str(url)
        return FakeResponse({"access_token": "test-access-token"})

    def fake_get(url, params=None, timeout=None):
        assert "graph.facebook.com" in str(url)
        assert params["fields"] == "id,email,name"
        return FakeResponse({"id": "fb-user-123", "email": "facebook@example.com", "name": "Facebook User"})

    monkeypatch.setattr("app.main.httpx.post", fake_post, raising=False)
    monkeypatch.setattr("app.main.httpx.get", fake_get, raising=False)

    response = client.get(
        f"{API}/auth/facebook/callback?code=test-code&state=test-state",
        follow_redirects=False,
        cookies={"facebook_oauth_state": "test-state"},
    )
    assert response.status_code == 302
    assert response.headers["location"].endswith("/")
    assert client.get(f"{API}/auth/me").json()["email"] == "facebook@example.com"


def test_facebook_callback_requires_registration_gate_when_closed(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.facebook_auth_enabled", True, raising=False)
    monkeypatch.setattr("app.main.settings.facebook_app_id", "app-123", raising=False)
    monkeypatch.setattr("app.main.settings.facebook_app_secret", "secret-123", raising=False)
    monkeypatch.setattr(
        "app.main.settings.facebook_redirect_uri", "https://club.example.com/login", raising=False
    )
    monkeypatch.setattr("app.main.settings.registration_enabled", False, raising=False)

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200

        def json(self):
            return self._payload

    def fake_post(url, data=None, timeout=None):
        return FakeResponse({"access_token": "test-access-token"})

    def fake_get(url, params=None, timeout=None):
        return FakeResponse({"id": "fb-user-456", "email": "restricted@example.com", "name": "Blocked User"})

    monkeypatch.setattr("app.main.httpx.post", fake_post, raising=False)
    monkeypatch.setattr("app.main.httpx.get", fake_get, raising=False)

    response = client.get(
        f"{API}/auth/facebook/callback?code=test-code&state=blocked",
        follow_redirects=False,
        cookies={"facebook_oauth_state": "blocked"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Registration is closed. Contact a captain."


def test_facebook_auth_requires_secure_production_configuration():
    with pytest.raises(ValueError, match="Facebook"):
        Settings(
            app_env="production",
            jwt_secret="this-is-a-valid-prod-secret-1234",
            cookie_secure=True,
            frontend_url="https://club.example.com",
            registration_enabled=False,
            club_invite_code="CLUB-READY",
            facebook_auth_enabled=True,
            facebook_app_id="1234567890",
            facebook_app_secret="super-secret",
            facebook_redirect_uri="http://localhost:5173/api/v1/auth/facebook/callback",
        )


def test_logout_revokes_previously_issued_token(admin):
    token = admin.cookies.get(COOKIE)
    assert admin.post(f"{API}/auth/logout").status_code == 204
    admin.cookies.set(COOKIE, token)
    assert admin.get(f"{API}/auth/me").status_code == 401


def test_reschedule_updates_game_without_creating_duplicates(admin):
    before = len(admin.get(f"{API}/matches").json())
    data = {
        "starts_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
        "title": "Updated kickoff",
        "location": "New pitch",
        "capacity": 10,
    }
    response = admin.put(f"{API}/matches/1", json=data)
    assert response.status_code == 200
    assert len(admin.get(f"{API}/matches").json()) == before
    assert response.json()[0]["location"] == "New pitch"
    assert admin.put(f"{API}/matches/1/lineup", json=lineup()).status_code == 200
    assert admin.put(f"{API}/matches/1", json={**data, "capacity": 14}).status_code == 400


def test_inactive_players_remain_named_in_historical_lineups(admin, session_factory):
    start(admin)
    assert complete(admin, 1, 0).status_code == 200
    with session_factory() as db:
        db.get(Player, 3).active = False
        db.commit()
    response = admin.get(f"{API}/matches/1").json()
    assert any(p["id"] == 3 and p["name"] == "Player 3" for p in response["players"])


def test_expired_jwt_is_rejected(client):
    token = jwt.encode(
        {
            "sub": "1",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iss": "lex-pickup-pro",
            "aud": "lex-club",
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    client.cookies.set(COOKIE, token)
    assert client.get(f"{API}/auth/me").status_code == 401


def test_password_whitespace_is_not_silently_changed(client):
    password = "  This is a passphrase!  "
    data = {
        "email": "spaces@example.com",
        "password": password,
        "name": "New Player",
        "team_id": 1,
        "invite_code": get_settings().club_invite_code,
    }
    assert client.post(f"{API}/auth/register", json=data).status_code == 201
    assert (
        client.post(
            f"{API}/auth/login", json={"email": data["email"], "password": password.strip()}
        ).status_code
        == 401
    )
    assert (
        client.post(f"{API}/auth/login", json={"email": data["email"], "password": password}).status_code
        == 200
    )


def test_roles_and_cross_site_protection(player):
    assert (
        player.post(
            f"{API}/matches", json={"starts_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()}
        ).status_code
        == 403
    )
    assert player.post(f"{API}/notes", json={"title": "Hi club", "body": "Hello squad"}).status_code == 403
    assert player.get(f"{API}/admin/members").status_code == 403
    response = player.put(
        f"{API}/matches/1/rsvp", json={"status": "going"}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert (
        player.put(
            f"{API}/matches/1/rsvp", json={"status": "going"}, headers={"Origin": "http://localhost:5173"}
        ).status_code
        == 200
    )


def test_captain_can_organize_but_not_administer(client):
    client.post(f"{API}/auth/login", json={"email": "captain@example.com", "password": PASSWORD})
    data = {"starts_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()}
    assert client.post(f"{API}/matches", json=data).status_code == 201
    assert client.post(f"{API}/players", json={"name": "New Player", "team_id": 1}).status_code == 403


def test_profile_permissions_and_validators(player):
    assert player.put(f"{API}/players/1", json={"name": "Other name"}).status_code == 403
    assert player.put(f"{API}/players/2", json={"name": "My name", "role": "admin"}).status_code == 422
    assert (
        player.put(
            f"{API}/players/2", json={"name": "My name", "photo_url": "javascript:alert(1)"}
        ).status_code
        == 422
    )
    assert player.put(f"{API}/players/2", json={"name": "My name", "positions": "STRIKER"}).status_code == 422
    assert (
        player.put(
            f"{API}/players/2", json={"name": "My name", "positions": "cm, st", "skill": 8.4}
        ).status_code
        == 200
    )
    assert player.get(f"{API}/players/2").json()["positions"] == "CM,ST"


def test_registration_requires_invite_and_never_assigns_privileges(client):
    data = {
        "email": "new@example.com",
        "password": PASSWORD,
        "name": "New Member",
        "team_id": 2,
        "invite_code": "wrong",
    }
    assert client.post(f"{API}/auth/register", json=data).status_code == 403
    data["invite_code"] = get_settings().club_invite_code
    assert client.post(f"{API}/auth/register", json={**data, "role": "admin"}).status_code == 422
    response = client.post(f"{API}/auth/register", json=data)
    assert response.status_code == 201
    assert response.json()["role"] == "player" and response.json()["player"]["team_id"] == 2
    assert client.post(f"{API}/auth/register", json=data).status_code == 409


def test_invitation_claims_existing_profile_once(admin, session_factory):
    response = admin.post(f"{API}/admin/members/3/invite", json={"email": "invited@example.com"})
    token = parse_qs(urlparse(response.json()["url"]).query)["invite"][0]
    with session_factory() as db:
        assert db.scalar(select(Invitation)).token_hash != token
        before = db.scalar(select(func.count()).select_from(Player))
    data = {
        "email": "wrong@example.com",
        "password": PASSWORD,
        "name": "Ignored",
        "team_id": 2,
        "invite_token": token,
    }
    assert admin.post(f"{API}/auth/register", json=data).status_code == 403
    data["email"] = "invited@example.com"
    response = admin.post(f"{API}/auth/register", json=data)
    assert response.status_code == 201
    assert response.json()["player"]["id"] == 3 and response.json()["player"]["team_id"] == 1
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Player)) == before
    assert admin.post(f"{API}/auth/register", json=data).status_code == 403


def test_old_and_expired_invitations_are_invalidated(admin, session_factory):
    response = admin.post(f"{API}/admin/members/3/invite", json={"email": "invited@example.com"})
    old = parse_qs(urlparse(response.json()["url"]).query)["invite"][0]
    response = admin.post(f"{API}/admin/members/3/invite", json={"email": "invited@example.com"})
    current = parse_qs(urlparse(response.json()["url"]).query)["invite"][0]
    data = {"email": "invited@example.com", "password": PASSWORD, "name": "Ignored", "team_id": 1}
    assert admin.post(f"{API}/auth/register", json={**data, "invite_token": old}).status_code == 403
    with session_factory() as db:
        db.scalar(select(Invitation)).expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    assert admin.post(f"{API}/auth/register", json={**data, "invite_token": current}).status_code == 403


def test_recurring_schedule_respects_eastern_daylight_saving(admin):
    start_date = datetime(datetime.now().year + 1, 10, 25, 10, tzinfo=ZoneInfo("America/New_York"))
    response = admin.post(f"{API}/matches", json={"starts_at": start_date.isoformat(), "repeat_weeks": 4})
    assert response.status_code == 201
    games = response.json()
    assert len(games) == 4
    assert len({g["recurrence_id"] for g in games}) == 1
    times = [datetime.fromisoformat(g["starts_at"]) for g in games]
    assert all(t.astimezone(ZoneInfo("America/New_York")).hour == 10 for t in times)
    assert len({t.hour for t in times}) == 2
    assert admin.post(f"{API}/matches", json={"starts_at": "2025-01-01T10:00:00"}).status_code == 422


def test_rsvp_capacity_and_closed_games(player, session_factory):
    with session_factory() as db:
        db.add_all([RSVP(match_id=1, player_id=i, status="going") for i in range(1, 13) if i not in (2, 12)])
        db.commit()
    assert player.put(f"{API}/matches/1/rsvp", json={"status": "going"}).status_code == 409
    assert player.put(f"{API}/matches/1/rsvp", json={"status": "maybe"}).status_code == 200
    assert player.get(f"{API}/matches/1").json()["my_rsvp"] == "maybe"
    with session_factory() as db:
        db.get(Match, 1).starts_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    assert player.put(f"{API}/matches/1/rsvp", json={"status": "out"}).status_code == 400


def test_lineup_validation(admin, session_factory):
    data = lineup()
    data["players"][1]["player_id"] = 1
    assert admin.put(f"{API}/matches/1/lineup", json=data).status_code == 400
    data = lineup()
    data["players"][1]["slot"] = 0
    assert admin.put(f"{API}/matches/1/lineup", json=data).status_code == 400
    assert admin.put(f"{API}/matches/1/lineup", json={**lineup(), "formation": "4-3-3"}).status_code == 400
    with session_factory() as db:
        db.add(RSVP(match_id=1, player_id=2, status="out"))
        db.commit()
    assert admin.put(f"{API}/matches/1/lineup", json=lineup()).status_code == 400


def test_balancing_creates_mixed_match_and_keeps_primary_teams(admin, session_factory):
    with session_factory() as db:
        before = {p.id: p.team_id for p in db.scalars(select(Player))}
        db.add_all([RSVP(match_id=1, player_id=i, status="going") for i in range(1, 11)])
        db.commit()
    assert admin.post(f"{API}/matches/1/balance").status_code == 200
    response = admin.get(f"{API}/matches/1").json()
    assert response["kind"] == "mixed" and len(response["lineup"]) == 10
    assert len({p["player_id"] for p in response["lineup"]}) == 10
    assert sum(p["side"] == "home" for p in response["lineup"]) == 5
    with session_factory() as db:
        assert {p.id: p.team_id for p in db.scalars(select(Player))} == before


def test_live_goals_assists_own_goals_and_career_statistics(admin):
    start(admin)
    assert (
        admin.post(
            f"{API}/matches/1/events", json={"player_id": 2, "assist_player_id": 3, "minute": 10}
        ).status_code
        == 201
    )
    assert (
        admin.post(
            f"{API}/matches/1/events", json={"player_id": 8, "assist_player_id": 2, "minute": 11}
        ).status_code
        == 400
    )
    assert (
        admin.post(
            f"{API}/matches/1/events", json={"player_id": 8, "kind": "own_goal", "minute": 12}
        ).status_code
        == 201
    )
    match = admin.get(f"{API}/matches/1").json()
    assert match["home_score"] == 2 and match["away_score"] == 0
    assert admin.get(f"{API}/stats").json()["matches_played"] == 0
    assert complete(admin, home=2).status_code == 200
    stats = admin.get(f"{API}/stats").json()
    players = {p["player_id"]: p for p in stats["players"]}
    assert players[2]["goals"] == 1 and players[3]["assists"] == 1 and players[8]["goals"] == 0
    assert players[2]["wins"] == 1 and players[8]["wins"] == 0
    assert players[2]["clean_sheets"] == 1 and players[8]["clean_sheets"] == 0
    assert stats["total_goals"] == 2 and stats["teams"][0]["wins"] == 1


def test_completed_results_require_sides_and_bound_event_goals(admin):
    assert complete(admin).status_code == 400
    start(admin)
    assert complete(admin, 1, 0).status_code == 200
    assert admin.post(f"{API}/matches/1/events", json={"player_id": 2, "minute": 12}).status_code == 201
    assert admin.post(f"{API}/matches/1/events", json={"player_id": 3, "minute": 14}).status_code == 400
    assert complete(admin, 0, 0).status_code == 400
    assert admin.put(f"{API}/matches/1/lineup", json=lineup()).status_code == 400
    assert (
        admin.patch(
            f"{API}/matches/1/result", json={"home_score": 1, "away_score": 0, "status": "live"}
        ).status_code
        == 400
    )


def test_event_deletion_and_rating_upsert(admin, session_factory):
    start(admin)
    event = admin.post(f"{API}/matches/1/events", json={"player_id": 2, "minute": 10}).json()
    assert admin.delete(f"{API}/matches/1/events/{event['id']}").status_code == 204
    assert admin.get(f"{API}/matches/1").json()["home_score"] == 0
    assert complete(admin).status_code == 200
    assert admin.put(f"{API}/matches/1/ratings", json={"player_id": 1, "value": 10}).status_code == 400
    for value in (7, 8.5):
        assert admin.put(f"{API}/matches/1/ratings", json={"player_id": 2, "value": value}).status_code == 200
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Rating)) == 1
    profile = admin.get(f"{API}/players/2").json()
    assert profile["stats"]["rating"] == 8.5


def test_mixed_results_follow_actual_sides_and_exclude_rivalry(admin, session_factory):
    data = lineup()
    data["players"][1]["player_id"], data["players"][6]["player_id"] = 8, 2
    assert admin.put(f"{API}/matches/1/lineup", json=data).status_code == 200
    with session_factory() as db:
        db.get(Match, 1).kind = "mixed"
        db.add(RSVP(match_id=1, player_id=2, status="going"))
        db.commit()
    assert complete(admin, home=3, away=1).status_code == 200
    stats = admin.get(f"{API}/stats").json()
    p = {p["player_id"]: p for p in stats["players"]}
    assert p[2]["wins"] == 0 and p[8]["wins"] == 1
    assert p[2]["reliability"] == 100 and p[2]["attendance"] == 100
    assert stats["teams"][0]["games"] == 0 and stats["matches_played"] == 1


def test_exports_and_calendar_are_safe(admin, session_factory):
    with session_factory() as db:
        db.get(Player, 2).name = '=HYPERLINK("evil")'
        db.get(Match, 1).notes = "Long club note " * 30 + "\nBEGIN:VEVENT\nSUMMARY:Fake event"
        db.commit()
    csv = admin.get(f"{API}/export/players")
    assert csv.status_code == 200 and "attachment" in csv.headers["content-disposition"]
    assert "'=HYPERLINK" in csv.text
    calendar = admin.get(f"{API}/matches/1/calendar")
    assert calendar.status_code == 200
    assert len([line for line in calendar.text.splitlines() if line == "BEGIN:VEVENT"]) == 1
    assert all(len(line.encode()) <= 75 for line in calendar.text.splitlines())
    assert "DTSTART:" in calendar.text and "DTEND:" in calendar.text


def test_admin_cannot_lock_themselves_out(admin):
    assert (
        admin.patch(
            f"{API}/admin/members/1", json={"team_id": 1, "active": False, "role": "admin"}
        ).status_code
        == 400
    )
    assert (
        admin.patch(
            f"{API}/admin/members/1", json={"team_id": 1, "active": True, "role": "player"}
        ).status_code
        == 400
    )


def test_deactivated_account_loses_access(admin):
    assert (
        admin.patch(
            f"{API}/admin/members/2", json={"team_id": 1, "active": False, "role": "player"}
        ).status_code
        == 200
    )
    response = admin.post(f"{API}/auth/login", json={"email": "player@example.com", "password": PASSWORD})
    assert response.status_code == 401


def test_new_season_preserves_old_results(admin, session_factory):
    start(admin)
    assert complete(admin, 2, 1).status_code == 200
    assert admin.post(f"{API}/seasons", json={"name": "Next season"}).status_code == 201
    assert admin.get(f"{API}/stats?active_season=true").json()["matches_played"] == 0
    assert admin.get(f"{API}/stats?season_id=1").json()["matches_played"] == 1
    assert admin.get(f"{API}/stats").json()["matches_played"] == 1
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Season).where(Season.active.is_(True))) == 1


def test_auth_rate_limit(client):
    _attempts.clear()
    for _ in range(20):
        assert (
            client.post(
                f"{API}/auth/login", json={"email": "unknown@example.com", "password": "wrong"}
            ).status_code
            == 401
        )
    response = client.post(f"{API}/auth/login", json={"email": "unknown@example.com", "password": "wrong"})
    assert response.status_code == 429 and response.headers["Retry-After"] == "600"


def test_production_configuration_fails_closed():
    with pytest.raises(ValueError):
        Settings(app_env="production")
    config = Settings(
        app_env="production",
        jwt_secret="x" * 64,
        cookie_secure=True,
        frontend_url="https://club.example",
        cors_origins=["https://club.example"],
        club_invite_code="unique-club-code",
        demo_enabled=False,
    )
    assert config.cookie_secure


def test_reminder_delivery_is_signed_and_deduplicated(session_factory, monkeypatch, capsys):
    from app import reminders

    config = Settings(
        reminder_webhook_url="https://hooks.example/club", reminder_webhook_secret="webhook-secret"
    )
    from app.storage.sql import SqlStore

    monkeypatch.setattr(reminders, "get_store", lambda: SqlStore(session_factory))
    monkeypatch.setattr(reminders, "get_settings", lambda: config)
    with session_factory() as db:
        db.get(Match, 1).starts_at = datetime.now(timezone.utc) + timedelta(hours=4)
        db.commit()
    sent = []

    def fake_post(url, *, content, timeout, headers):
        assert url.startswith("https://")
        assert headers["X-Lex-Signature"] == hmac.new(b"webhook-secret", content, hashlib.sha256).hexdigest()
        sent.append(content)

        class Response:
            def raise_for_status(self):
                pass

        return Response()

    monkeypatch.setattr(reminders.httpx, "post", fake_post)
    reminders.run()
    assert "confirm Going" in capsys.readouterr().out and not sent
    reminders.run(deliver=True)
    reminders.run(deliver=True)
    assert len(sent) == 1
