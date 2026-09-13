import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

from app.domain.records import (
    RSVP,
    ClubNote,
    Invitation,
    Lineup,
    Match,
    MatchEvent,
    Player,
    PlayerImport,
    User,
)
from app.import_players import ImportProblem, apply_review, preview
from app.reminders import acknowledge, claim
from app.storage.interfaces import StorageConflict, StorageLimit, StorageUnavailable

PASSWORD = "TestPassword2026!"


def payload(count):
    return json.dumps(
        [
            {"name": f"Nguyễn Player {i}", "profileUrl": "", "photoUrl": "", "role": "member"}
            for i in range(count)
        ]
    ).encode()


def test_api_roster_analytics_and_share_contract(api):
    assert api.get("/api/v1/health").json() == {"status": "ok"}
    teams = api.get("/api/v1/teams").json()
    assert [t["name"] for t in teams] == ["Old Gentlemen", "Young Boys"]
    people = api.get("/api/v1/players").json()
    assert len(people) == 12 and all(isinstance(p["id"], int) for p in people)
    for endpoint in (
        "/players/2",
        "/matches",
        "/matches/1",
        "/stats",
        "/notes",
        "/export/players",
        "/matches/1/calendar",
    ):
        response = api.get("/api/v1" + endpoint)
        assert response.status_code == 200, (endpoint, response.text)
        assert "password_hash" not in response.text and "identity_key" not in response.text
    summary = api.get("/api/v1/matches/1/calendar")
    assert summary.status_code == 200


def test_goal_command_replay_and_conflicting_payload(api, store):
    # Make a valid lineup and a live match using the same domain fixture on all providers.
    def prepare(db):
        match = db.get(Match, 1)
        match.status = "live"
        db.insert(Lineup(match_id=1, player_id=2, side="home", slot=0))

    store.execute(prepare)
    headers = {"Idempotency-Key": "score-operation-0000001"}
    goal = {"player_id": 2, "kind": "goal", "minute": 10}
    first = api.post("/api/v1/matches/1/events", json=goal, headers=headers)
    assert first.status_code == 201, first.text
    replay = api.post("/api/v1/matches/1/events", json=goal, headers=headers)
    assert replay.json() == first.json()
    conflict = api.post("/api/v1/matches/1/events", json={**goal, "minute": 11}, headers=headers)
    assert conflict.status_code == 409
    state = store.read()
    assert len(state.records(MatchEvent)) == 1 and state.get(Match, 1).home_score == 1


def test_invitation_registration_atomic_and_replay_session(api, store):
    invite = api.post("/api/v1/admin/members/3/invite", json={"email": "new@example.com"})
    assert invite.status_code == 200
    token = parse_qs(urlparse(invite.json()["url"]).query)["invite"][0]
    data = {"email": "new@example.com", "name": "Ignored", "password": PASSWORD, "invite_token": token}
    headers = {"Idempotency-Key": "registration-operation-01"}
    response = api.post("/api/v1/auth/register", json=data, headers=headers)
    assert response.status_code == 201, response.text
    api.cookies.clear()
    repeat = api.post("/api/v1/auth/register", json=data, headers=headers)
    assert repeat.status_code == 201 and api.get("/api/v1/auth/me").status_code == 200
    assert repeat.json()["player"]["id"] == 3
    assert len(store.read().records(User)) == 4
    state = store.read()
    assert state.first(Invitation, token_hash=hashlib.sha256(token.encode()).hexdigest()).used
    duplicate = api.post("/api/v1/auth/register", json=data)
    assert duplicate.status_code == 403


def test_revocations_are_visible_to_independent_requests(api, store):
    # A distinct SDK client models a second API worker without the first client's session cache.
    from app.main import app
    from app.storage.cosmos import CosmosStore
    from app.storage.factory import get_store
    from app.storage.sql import SqlStore

    other = (
        CosmosStore(store.settings, container=store.container if store.client is None else None)
        if hasattr(store, "container")
        else SqlStore(store.sessions)
    )
    app.dependency_overrides[get_store] = lambda: other
    login = api.post("/api/v1/auth/login", json={"email": "player@example.com", "password": PASSWORD})
    assert login.status_code == 200

    def revoke(db):
        db.get(User, 2).session_version += 1

    store.execute(revoke)
    assert api.get("/api/v1/auth/me").status_code == 401
    api.post("/api/v1/auth/login", json={"email": "player@example.com", "password": PASSWORD})
    store.execute(lambda db: setattr(db.get(Player, 2), "active", False))
    assert api.get("/api/v1/players").status_code == 401
    other.close()


def test_final_rsvp_place_is_atomic(store):
    store.execute(lambda db: setattr(db.get(Match, 1), "capacity", 2))
    store.execute(lambda db: db.insert(RSVP(match_id=1, player_id=1, status="going")).id)
    start = Barrier(2)

    def attend(player_id):
        start.wait(timeout=5)

        def operation(db):
            if len(db.records(RSVP, match_id=1, status="going")) >= db.get(Match, 1).capacity:
                raise HTTPException(409, "Full")
            return db.insert(RSVP(match_id=1, player_id=player_id, status="going")).id

        try:
            store.execute(operation)
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(attend, (2, 3)))
    assert sorted(statuses) == [200, 409]
    assert len(store.read().records(RSVP, match_id=1, status="going")) == 2


def test_concurrent_account_claim_creates_one_user(store):
    start = Barrier(2)

    def claim_profile(index):
        start.wait(timeout=5)

        def operation(db):
            if db.first(User, player_id=3) or db.first(User, email="race@example.com"):
                raise StorageConflict("Already claimed")
            return db.insert(User(player_id=3, email="race@example.com", password_hash="hash")).id

        try:
            store.execute(operation)
            return True
        except StorageConflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(claim_profile, (1, 2))) == 1
    assert len(store.read().records(User, player_id=3)) == 1


def test_54_player_import_is_atomic_idempotent_and_preserves_profile_edits(store):
    source = payload(54)
    report = preview(store.read(), source)
    report.reviewed = True
    assert store.execute(lambda db: apply_review(db, source, report))["created"] == 54
    imported = store.read().records(PlayerImport)
    target = imported[0].player_id

    def edit(db):
        db.get(Player, target).name = "Edited Name"
        db.get(Player, target).team_id = 2

    store.execute(edit)
    assert store.execute(lambda db: apply_review(db, source, report))["unchanged"] == 54
    state = store.read()
    assert len(state.records(Player)) == 66 and len(state.records(PlayerImport)) == 54
    assert state.get(Player, target).name == "Edited Name"
    assert state.get(Player, imported[1].player_id).skill is None
    assert len(state.records(User)) == 3


def test_import_validation_failure_never_persists_partial_roster(store):
    source = payload(54)
    report = preview(store.read(), source)
    report.reviewed = True
    report.rows[-1].action = "match"
    report.rows[-1].existing_player_id = 99999
    with pytest.raises(ImportProblem):
        store.execute(lambda db: apply_review(db, source, report))
    assert len(store.read().records(Player)) == 12 and not store.read().records(PlayerImport)


def test_large_atomic_import_has_provider_specific_limit(store):
    source = payload(101)
    report = preview(store.read(), source)
    report.reviewed = True
    if hasattr(store, "container"):
        with pytest.raises(StorageLimit, match="100 operations"):
            store.execute(lambda db: apply_review(db, source, report))
        assert len(store.read().records(Player)) == 12
    else:
        assert store.execute(lambda db: apply_review(db, source, report))["created"] == 101


def test_pagination_reads_all_history(store):
    for batch in range(3):

        def insert(db):
            for i in range(60):
                db.insert(ClubNote(title=f"Note {batch}-{i}", body="Club record", category="general"))

        store.execute(insert)
    assert len(store.read().records(ClubNote)) == 180


def test_dispatch_lease_reclaims_failed_delivery_and_acknowledges(store):
    now = datetime.now(timezone.utc)
    store.execute(lambda db: setattr(db.get(Match, 1), "starts_at", now + timedelta(hours=12)))
    first = store.execute(lambda db: claim(db, 1, "worker-a", now))
    assert first
    assert store.execute(lambda db: claim(db, 1, "worker-b", now)) is None
    second = store.execute(lambda db: claim(db, 1, "worker-b", now + timedelta(minutes=6)))
    assert first["key"] == second["key"]
    store.execute(lambda db: acknowledge(db, first["dispatch_id"], "worker-a", now))
    assert store.read().get(Match, 1).reminder_sent_at is None
    store.execute(lambda db: acknowledge(db, second["dispatch_id"], "worker-b", now))
    assert store.read().get(Match, 1).reminder_sent_at == now


def test_maintenance_blocks_reads_and_mutations(store):
    from app.migrate_storage import set_mode

    set_mode(store, "maintenance")
    with pytest.raises(StorageUnavailable):
        store.read()
    with pytest.raises(StorageUnavailable):
        store.execute(lambda db: setattr(db.get(Player, 1), "name", "Changed"))
    set_mode(store, "ready")
    assert store.read().get(Player, 1).name == "Player 1"


def test_registration_receipt_cannot_bypass_password_reset(api, store):
    from app.security import password_hasher

    invite = api.post("/api/v1/admin/members/3/invite", json={"email": "reset@example.com"})
    token = parse_qs(urlparse(invite.json()["url"]).query)["invite"][0]
    data = {"email": "reset@example.com", "name": "Ignored", "password": PASSWORD, "invite_token": token}
    headers = {"Idempotency-Key": "register-password-reset-1"}
    assert api.post("/api/v1/auth/register", json=data, headers=headers).status_code == 201
    new_hash = password_hasher.hash("DifferentPassword2026!")

    def reset(db):
        user = db.first(User, email="reset@example.com")
        user.password_hash = new_hash
        user.session_version += 1

    store.execute(reset)
    api.cookies.clear()
    assert api.post("/api/v1/auth/register", json=data, headers=headers).status_code == 401
    assert api.get("/api/v1/auth/me").status_code == 401


def test_invitation_link_is_encrypted_in_command_receipts(api, store):
    from app.migrate_storage import receipts

    response = api.post("/api/v1/admin/members/3/invite", json={"email": "private@example.com"})
    token = parse_qs(urlparse(response.json()["url"]).query)["invite"][0]
    assert token not in json.dumps(receipts(store))
