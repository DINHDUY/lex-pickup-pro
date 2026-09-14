from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from fastapi import HTTPException

from app.domain.club import ClubData
from app.domain.records import (
    ExternalIdentity,
    FacebookOnboarding,
    Invitation,
    Player,
    PlayerImport,
    User,
    utcnow,
)
from app.facebook import ONBOARDING_COOKIE, complete, settings, token_hash
from app.security import COOKIE
from app.storage.cosmos.documents import decode, encode
from app.storage.interfaces import StorageConflict

API = "/api/v1"


@pytest.fixture
def facebook(monkeypatch):
    monkeypatch.setattr(settings, "facebook_auth_enabled", True)
    monkeypatch.setattr(settings, "facebook_roster_claiming_enabled", True)
    monkeypatch.setattr(settings, "facebook_app_id", "test-app")
    monkeypatch.setattr(settings, "facebook_app_secret", "test-secret")
    monkeypatch.setattr(settings, "registration_enabled", False)
    profile = {"id": "fb-new", "email": "new@example.com", "name": "Different Facebook Name"}
    monkeypatch.setattr(
        "app.facebook.httpx.post",
        lambda *a, **kw: httpx.Response(
            200, json={"access_token": "provider-access-token"}, request=httpx.Request("POST", a[0])
        ),
    )
    monkeypatch.setattr(
        "app.facebook.httpx.get",
        lambda *a, **kw: httpx.Response(200, json=profile, request=httpx.Request("GET", a[0])),
    )
    return profile


def begin(api, invite=None):
    start = api.get(
        f"{API}/auth/facebook/login", params={"invite": invite} if invite else {}, follow_redirects=False
    )
    assert start.status_code == 302
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return api.get(
        f"{API}/auth/facebook/callback", params={"state": state, "code": "valid-code"}, follow_redirects=False
    )


def test_immediate_claim_preserves_profile_and_replays_safely(api, store, facebook):
    def prepare(db):
        db.get(Player, 3).is_captain = True
        db.get(Player, 12).active = False
        db.insert(
            PlayerImport(
                import_id="existing-import",
                source="messenger",
                source_key="source",
                player_id=3,
                source_fingerprint="fingerprint",
            )
        )

    store.execute(prepare)
    before = store.read()
    api.cookies.clear()
    response = begin(api)
    assert response.headers["location"].endswith("/onboarding/claim-profile")
    assert api.cookies.get("facebook_oauth_state") is None
    assert api.get(f"{API}/auth/me").status_code == 401
    assert api.get(f"{API}/players").status_code == 401
    assert len(store.read().records(User)) == 3
    assert api.get(f"{API}/auth/onboarding").json()["email"] == "new@example.com"
    candidates = api.get(f"{API}/auth/onboarding/players").json()
    assert candidates["total"] == 8
    assert {p["id"] for p in candidates["players"]}.isdisjoint({1, 2, 7, 12})
    assert set(candidates["players"][0]) == {"id", "name", "nickname", "photo_url", "team_id", "team_name"}
    assert api.get(f"{API}/auth/onboarding/players?search=Player%203&limit=1").json()["players"][0]["id"] == 3
    assert (
        api.post(
            f"{API}/auth/onboarding/claim", json={"player_id": 3, "email": "attacker@example.com"}
        ).status_code
        == 422
    )
    assert (
        api.post(
            f"{API}/auth/onboarding/claim", json={"player_id": 3}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    result = api.post(f"{API}/auth/onboarding/claim", json={"player_id": 3})
    assert result.status_code == 200, result.text
    assert result.json()["role"] == "player"
    assert result.json()["player"]["id"] == 3
    after = store.read()
    assert after.records(Player) == before.records(Player)
    assert after.records(PlayerImport) == before.records(PlayerImport)
    assert len(after.records(User)) == 4
    assert len(after.records(ExternalIdentity)) == 1
    pending = after.records(FacebookOnboarding)[0]
    assert pending.completed_at and pending.token_hash != api.cookies.get(ONBOARDING_COOKIE)
    assert "provider-access-token" not in str(after.dump())
    # Lost response recovery works even when the normal session cookie did not arrive.
    for entry in list(api.cookies.jar):
        if entry.name == COOKIE:
            api.cookies.delete(entry.name, domain=entry.domain, path=entry.path)
    assert api.post(f"{API}/auth/onboarding/claim", json={"player_id": 3}).json() == result.json()
    assert api.post(f"{API}/auth/onboarding/claim", json={"player_id": 4}).status_code == 409
    assert len(store.read().records(User)) == 4
    restricted_token = api.cookies.get(ONBOARDING_COOKIE)
    assert api.post(f"{API}/auth/logout").status_code == 204
    api.cookies.set(ONBOARDING_COOKIE, restricted_token, path="/api")
    assert api.post(f"{API}/auth/onboarding/claim", json={"player_id": 3}).status_code == 401


def test_returning_identity_ignores_changed_or_missing_email(api, store, facebook):
    api.cookies.clear()
    begin(api)
    assert api.post(f"{API}/auth/onboarding/claim", json={"player_id": 3}).status_code == 200
    api.cookies.clear()
    facebook["email"] = "admin@example.com"
    assert begin(api).headers["location"].endswith("/")
    assert api.get(f"{API}/auth/me").json()["player"]["id"] == 3
    facebook.pop("email")
    api.cookies.clear()
    begin(api)
    assert api.get(f"{API}/auth/me").json()["email"] == "new@example.com"
    assert len(store.read().records(User)) == 4


def test_existing_account_requires_password_and_preserves_admin(api, store, facebook):
    facebook["email"] = "admin@example.com"
    api.cookies.clear()
    begin(api)
    assert api.get(f"{API}/auth/onboarding").json()["status"] == "link_required"
    assert api.get(f"{API}/auth/me").status_code == 401
    assert api.post(f"{API}/auth/onboarding/claim", json={"player_id": 3}).status_code == 409
    assert api.post(f"{API}/auth/onboarding/link", json={"password": "wrong"}).status_code == 401
    assert store.read().records(ExternalIdentity) == []
    result = api.post(f"{API}/auth/onboarding/link", json={"password": "TestPassword2026!"})
    assert result.status_code == 200, result.text
    assert result.json()["role"] == "admin" and result.json()["player"]["id"] == 1
    api.cookies.clear()
    facebook["id"] = "another-facebook"
    begin(api)
    assert api.post(f"{API}/auth/onboarding/link", json={"password": "TestPassword2026!"}).status_code == 409
    assert len(store.read().records(ExternalIdentity)) == 1


def test_missing_email_denied_oauth_and_invalid_state_are_recoverable(api, store, facebook):
    api.cookies.clear()
    facebook.pop("email")
    response = begin(api)
    assert "email+address" in response.headers["location"]
    assert api.cookies.get(ONBOARDING_COOKIE) is None
    assert api.cookies.get("facebook_oauth_state") is None
    response = api.get(f"{API}/auth/facebook/callback?state=bad&code=code", follow_redirects=False)
    assert "cancelled+or+expired" in response.headers["location"]
    api.get(f"{API}/auth/facebook/login", follow_redirects=False)
    state = api.cookies.get("facebook_oauth_state")
    response = api.get(
        f"{API}/auth/facebook/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert "cancelled" in response.headers["location"]
    expired = jwt.encode(
        {
            "nonce": "x",
            "iat": utcnow() - timedelta(hours=1),
            "exp": utcnow() - timedelta(minutes=1),
            "aud": "facebook-oauth",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    api.cookies.set("facebook_oauth_state", expired, path="/api")
    response = api.get(
        f"{API}/auth/facebook/callback", params={"state": expired, "code": "code"}, follow_redirects=False
    )
    assert "expired" in response.headers["location"]
    assert len(store.read().records(User)) == 3
    assert store.read().records(FacebookOnboarding) == []


def test_invite_target_is_fixed(api, store, facebook):
    invite = api.post(f"{API}/admin/members/3/invite", json={"email": facebook["email"]}).json()
    token = parse_qs(urlparse(invite["url"]).query)["invite"][0]
    api.cookies.clear()
    begin(api, token)
    assert [p["id"] for p in api.get(f"{API}/auth/onboarding/players").json()["players"]] == [3]
    assert api.post(f"{API}/auth/onboarding/claim", json={"player_id": 4}).status_code == 409
    assert store.read().records(Invitation)[0].used is False
    assert api.post(f"{API}/auth/onboarding/claim", json={"player_id": 3}).status_code == 200
    assert store.read().records(Invitation)[0].used is True


def test_expiry_cancel_and_feature_disable_leave_profile_available(api, store, facebook, monkeypatch):
    api.cookies.clear()
    begin(api)
    monkeypatch.setattr(settings, "facebook_roster_claiming_enabled", False)
    assert api.post(f"{API}/auth/onboarding/claim", json={"player_id": 3}).status_code == 403
    monkeypatch.setattr(settings, "facebook_roster_claiming_enabled", True)
    store.execute(
        lambda db: setattr(db.records(FacebookOnboarding)[0], "expires_at", utcnow() - timedelta(seconds=1))
    )
    assert api.post(f"{API}/auth/onboarding/claim", json={"player_id": 3}).status_code == 401
    assert api.get(f"{API}/auth/onboarding").status_code == 401
    begin(api)
    assert api.post(f"{API}/auth/onboarding/cancel").status_code == 204
    assert api.get(f"{API}/auth/onboarding").status_code == 401
    assert len(store.read().records(User)) == 3
    assert len(store.read().records(Player)) == 12
    assert store.read().records(FacebookOnboarding) == []


@pytest.mark.parametrize("collision", ["player", "email", "identity"])
def test_concurrent_claims_cannot_duplicate_bindings(store, facebook, collision):
    def prepare(db):
        for i in range(2):
            db.insert(
                FacebookOnboarding(
                    token_hash=token_hash(f"token-{i}"),
                    app_id=settings.facebook_app_id,
                    subject="same" if collision == "identity" else f"facebook-{i}",
                    email="same@example.com" if collision == "email" else f"new{i}@example.com",
                    name="New member",
                    expires_at=utcnow() + timedelta(minutes=15),
                )
            )

    store.execute(prepare)
    barrier = Barrier(2)

    def run(i):
        barrier.wait()
        try:
            return store.execute(
                lambda db: complete(
                    db, token_hash(f"token-{i}"), player_id=3 if collision == "player" else 3 + i
                )
            )
        except (HTTPException, StorageConflict):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sum(result is not None for result in results) == 1
    after = store.read()
    assert len(after.records(User)) == 4
    assert len(after.records(ExternalIdentity)) == 1
    assert sum(p.user_id is not None for p in after.records(FacebookOnboarding)) == 1
    assert len(after.records(Player)) == 12


def test_legacy_snapshot_and_cosmos_documents_remain_compatible(store):
    snapshot = store.read()
    legacy = snapshot.dump()
    legacy["tables"].pop("facebook_onboarding")
    legacy["tables"].pop("external_identities")
    restored = ClubData.load(legacy)
    documents = encode(restored, "compatibility")
    assert not any(d["kind"] in ("facebookonboarding", "externalidentity") for d in documents.values())
    assert encode(decode(documents.values(), restored.counters), "compatibility") == documents
    assert restored.records(User) == snapshot.records(User)


def test_reissuing_invitation_invalidates_onboarding(api, store, facebook):
    invite = api.post(f"{API}/admin/members/3/invite", json={"email": facebook["email"]}).json()
    token = parse_qs(urlparse(invite["url"]).query)["invite"][0]
    api.cookies.clear()
    begin(api, token)
    api.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "TestPassword2026!"})
    response = api.post(f"{API}/admin/members/3/invite", json={"email": facebook["email"]})
    assert response.status_code == 200, response.text
    assert api.post(f"{API}/auth/onboarding/claim", json={"player_id": 3}).status_code == 401
    assert store.read().records(FacebookOnboarding) == []
