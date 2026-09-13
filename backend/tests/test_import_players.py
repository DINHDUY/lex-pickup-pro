import json
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func, select

from app.import_players import ImportProblem, apply_review, preview, read_source
from app.models import RSVP, Lineup, Player, PlayerImport, User
from app.storage.sql import SqlStore, load_data

from .conftest import PASSWORD


def source(*names):
    return json.dumps(
        [
            {"name": name, "profileUrl": "", "photoUrl": "", "role": "admin" if "Admin" in name else "member"}
            for name in names
        ],
        ensure_ascii=False,
    ).encode()


def reviewed(factory, payload, previous=None):
    with factory() as db:
        report = preview(load_data(db), payload, previous)
    report.reviewed = True
    return report


def apply(factory, payload, report):
    return SqlStore(factory).execute(lambda db: apply_review(db, payload, report))


def total(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_clean_preview_and_unknown_profiles(session_factory):
    payload = source("Admin ·", "Sample Captain Admin ·", "  Nguyễn   Văn Mẫu  ", "Admin Smith")
    with session_factory() as db:
        report = preview(load_data(db), payload)
        assert total(db, Player) == 12 and total(db, PlayerImport) == 0
    assert not report.reviewed
    assert [r.name for r in report.rows] == ["", "Sample Captain", "Nguyễn Văn Mẫu", "Admin Smith"]
    assert report.rows[0].action == "exclude"
    assert report.rows[1].raw_name == "Sample Captain Admin ·"
    with pytest.raises(ImportProblem, match="reviewed"):
        apply(session_factory, payload, report)
    report.reviewed = True
    assert apply(session_factory, payload, report)["created"] == 3
    with session_factory() as db:
        people = list(db.scalars(select(Player).where(Player.id > 12)))
        for person in people:
            assert all(
                getattr(person, field) is None
                for field in [
                    "team_id",
                    "positions",
                    "skill",
                    "jersey",
                    "age_group",
                    "dominant_foot",
                    "preferred_times",
                    "availability",
                ]
            )
            assert not person.is_captain and person.contact_preference == "Messenger"
        assert total(db, User) == 3


@pytest.mark.parametrize(
    "payload",
    [
        b"{}",
        b"[]",
        b"null",
        b"[null]",
        b"not json",
        b'[ {"name": "A", "name": "B"} ]',
        b'[ {"name": 42, "profileUrl": "", "photoUrl": "", "role": "member"} ]',
        b'[ {"name": "Person", "profileUrl": "javascript:bad", "photoUrl": "", "role": "member"} ]',
        source("\u200bHidden Name"),
        source("A"),
        source("a" * 81),
    ],
)
def test_malformed_source_rejected(payload):
    with pytest.raises(ImportProblem):
        read_source(payload)


def test_repeat_and_regenerated_review_preserve_profile_edits(session_factory):
    payload = source("Sample Player")
    report = reviewed(session_factory, payload)
    assert apply(session_factory, payload, report)["created"] == 1
    with session_factory() as db:
        person = db.scalar(select(Player).where(Player.name == "Sample Player"))
        person.name, person.team_id, person.skill, person.jersey = "Edited Display Name", 2, 8, 0
        db.commit()
    assert apply(session_factory, payload, report)["unchanged"] == 1
    regenerated = reviewed(session_factory, payload)
    assert regenerated.rows[0].import_id == report.rows[0].import_id
    assert regenerated.rows[0].action == "unchanged"
    assert apply(session_factory, payload, regenerated)["unchanged"] == 1
    with session_factory() as db:
        person = db.scalar(select(Player).where(Player.name == "Edited Display Name"))
        assert (person.team_id, person.skill, person.jersey) == (2, 8, 0)
        assert total(db, Player) == 13 and total(db, PlayerImport) == 1


def test_changed_source_rename_and_explicit_matching(session_factory):
    payload = source("Sample Person")
    report = reviewed(session_factory, payload)
    apply(session_factory, payload, report)
    changed = source("Sample Renamed")
    with pytest.raises(ImportProblem, match="Source changed"):
        apply(session_factory, changed, report)
    new = reviewed(session_factory, changed, report)
    assert new.rows[0].action == "unresolved"
    with pytest.raises(ImportProblem, match="unresolved"):
        apply(session_factory, changed, new)
    with session_factory() as db:
        mapping = db.scalar(select(PlayerImport))
        new.rows[0].import_id = mapping.import_id
        new.rows[0].existing_player_id = mapping.player_id
    new.rows[0].action = "match"
    assert apply(session_factory, changed, new)["unchanged"] == 1
    assert reviewed(session_factory, changed).rows[0].action == "unchanged"
    with session_factory() as db:
        assert total(db, Player) == 13
        assert db.get(Player, mapping.player_id).name == "Sample Person"


def test_name_collision_never_automatically_merges_accounts(session_factory):
    payload = source("Player 1")
    report = reviewed(session_factory, payload)
    assert report.rows[0].action == "unresolved"
    assert report.rows[0].candidate_player_ids == [1]
    report.rows[0].action = "create"
    with pytest.raises(ImportProblem, match="collision"):
        apply(session_factory, payload, report)
    report.rows[0].action = "match"
    report.rows[0].existing_player_id = 1
    assert apply(session_factory, payload, report)["matched"] == 1
    with session_factory() as db:
        assert total(db, Player) == 12 and total(db, User) == 3
        assert db.get(User, 1).role == "admin"


def test_duplicate_names_require_distinct_identity_decisions(session_factory):
    payload = source("Same Name", " Same  Name ")
    report = reviewed(session_factory, payload)
    assert all(r.action == "unresolved" for r in report.rows)
    for row in report.rows:
        row.action = "create"
    with pytest.raises(ImportProblem, match="collision"):
        apply(session_factory, payload, report)
    for row in report.rows:
        row.allow_name_collision = True
    assert apply(session_factory, payload, report)["created"] == 2
    assert apply(session_factory, payload, report)["unchanged"] == 2


def test_failed_batch_rolls_back_earlier_creates(session_factory):
    payload = source("First Accepted", "Missing Match")
    report = reviewed(session_factory, payload)
    report.rows[1].action, report.rows[1].existing_player_id = "match", 999999
    with pytest.raises(ImportProblem, match="existing player ID"):
        apply(session_factory, payload, report)
    with session_factory() as db:
        assert total(db, Player) == 12 and total(db, PlayerImport) == 0


def test_source_rows_cannot_be_silently_omitted_or_reassigned(session_factory):
    payload = source("Sample One", "Sample Two")
    report = reviewed(session_factory, payload)
    missing = report.model_copy(deep=True)
    missing.rows.pop()
    with pytest.raises(ImportProblem, match="every source row"):
        apply(session_factory, payload, missing)
    apply(session_factory, payload, report)
    report.rows[0].existing_player_id = 2
    with pytest.raises(ImportProblem, match="cannot be reassigned"):
        apply(session_factory, payload, report)


def test_demo_database_refuses_real_import(session_factory):
    payload = source("Sample Real Person")
    report = reviewed(session_factory, payload)
    with session_factory() as db:
        db.get(User, 1).email = "admin@lexpickup.club"
        db.commit()
    with pytest.raises(ImportProblem, match="demo accounts"):
        apply(session_factory, payload, report)


def test_bootstrap_admin_uses_explicit_imported_profile(session_factory, monkeypatch):
    from app import seed

    payload = source("Sample Organizer")
    apply(session_factory, payload, reviewed(session_factory, payload))
    with session_factory() as db:
        person = db.scalar(select(Player).where(Player.name == "Sample Organizer"))
    monkeypatch.setattr(seed, "get_store", lambda: SqlStore(session_factory))
    monkeypatch.setattr(seed.getpass, "getpass", lambda _: PASSWORD)
    seed.seed(admin_email="organizer@example.com", admin_player_id=person.id)
    with session_factory() as db:
        account = db.scalar(select(User).where(User.email == "organizer@example.com"))
        assert account.role == "admin" and account.player_id == person.id
        assert total(db, Player) == 13
        assert db.get(Player, person.id).team_id is None


def test_imported_profile_claim_balance_export_and_team_permissions(admin, session_factory):
    payload = source("Nguyễn Văn Mẫu", "Sample Captain Admin ·")
    apply(session_factory, payload, reviewed(session_factory, payload))
    with session_factory() as db:
        people = list(db.scalars(select(Player).where(Player.id > 12).order_by(Player.id)))
        ids = [p.id for p in people]
        db.add_all([RSVP(match_id=1, player_id=pid, status="going") for pid in ids])
        db.commit()
    profile = admin.get(f"/api/v1/players/{ids[0]}").json()
    assert profile["stats"]["games"] == 0 and profile["stats"]["rating"] is None
    csv = admin.get("/api/v1/export/players").text
    assert "Nguyễn Văn Mẫu,,Unassigned,,0" in csv
    balance = admin.post("/api/v1/matches/1/balance").json()
    assert set(balance["estimated_player_ids"]) == set(ids)
    assert balance["team_skill"] == {"home": 5.5, "away": 5.5}
    response = admin.post(f"/api/v1/admin/members/{ids[0]}/invite", json={"email": "claimed@example.com"})
    token = parse_qs(urlparse(response.json()["url"]).query)["invite"][0]
    claimed = admin.post(
        "/api/v1/auth/register",
        json={
            "email": "claimed@example.com",
            "name": "Ignored",
            "password": PASSWORD,
            "invite_token": token,
        },
    )
    assert claimed.status_code == 201
    assert claimed.json()["player"]["id"] == ids[0] and claimed.json()["role"] == "player"
    assert claimed.json()["player"]["team_id"] is None
    assert admin.patch(f"/api/v1/players/{ids[0]}/team", json={"team_id": 1}).status_code == 403
    admin.post("/api/v1/auth/login", json={"email": "captain@example.com", "password": PASSWORD})
    assert admin.patch(f"/api/v1/players/{ids[0]}/team", json={"team_id": 1}).status_code == 200
    assert admin.patch(f"/api/v1/players/{ids[0]}/team", json={"team_id": 3}).status_code == 422
    assert admin.patch(f"/api/v1/players/{ids[0]}/team", json={"team_id": None}).status_code == 200
    assert (
        admin.patch(
            f"/api/v1/admin/members/{ids[0]}",
            json={
                "team_id": 1,
                "role": "admin",
                "active": True,
            },
        ).status_code
        == 403
    )
    with session_factory() as db:
        assert total(db, Player) == 14 and total(db, User) == 4
        assert total(db, Lineup) == 2 and all(db.get(Player, pid).skill is None for pid in ids)
