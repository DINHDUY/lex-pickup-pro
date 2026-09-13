from copy import deepcopy
from uuid import uuid4

import pytest
from azure.core.exceptions import ServiceResponseError
from azure.cosmos import exceptions
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domain.records import ClubNote, Match, Player, User
from app.migrate_storage import export_snapshot, restore, restore_cosmos, set_mode, validate_snapshot, verify
from app.storage.cosmos import CosmosStore
from app.storage.cosmos.manage import initialize
from app.storage.interfaces import StorageLimit, StorageUnavailable
from app.storage.sql import SqlStore

from .fake_cosmos import MemoryContainer


def fresh_cosmos(source):
    return CosmosStore(
        source.settings.model_copy(update={"cosmos_club_id": "restore-" + uuid4().hex}),
        container=source.container,
    )


def test_backup_restore_and_reverse_transfer_preserve_records_receipts_and_stats(store, tmp_path):
    # Includes changes made after a cutover: restore into a fresh SQL target, never overwrite stale SQL.
    store.execute(lambda db: setattr(db.get(Player, 2), "name", "Nguyễn Updated"), command_id="abc123")
    original = export_snapshot(store, freeze=True)
    altered = deepcopy(original)
    altered["club_data"]["tables"]["players"][0]["name"] = "Tampered"
    with pytest.raises(ValueError, match="checksum"):
        validate_snapshot(altered)
    engine = create_engine(f"sqlite:///{tmp_path}/restore.db")
    Base.metadata.create_all(engine)
    target = SqlStore(sessionmaker(engine, expire_on_commit=False))
    assert restore(target, original)["dry_run"]
    assert restore(target, original, apply=True)["verified"]
    with pytest.raises(StorageUnavailable):
        target.health()
    set_mode(target, "ready")
    assert target.read().get(Player, 2).name == "Nguyễn Updated"
    assert (
        target.execute(lambda db: pytest.fail("Committed command was replayed"), command_id="abc123") is None
    )
    with pytest.raises(ValueError, match="empty"):
        restore(target, original, apply=True)
    engine.dispose()


def test_live_preview_cannot_be_used_for_cutover(store):
    preview = export_snapshot(store)
    assert not preview["frozen"]
    with pytest.raises(ValueError, match="freeze"):
        restore(store, preview, apply=True)


def test_resumable_cosmos_restore_is_inactive_and_validated(store):
    if not hasattr(store, "container"):
        pytest.skip("Cosmos chunk recovery")
    for group in range(3):
        store.execute(
            lambda db: db.insert_many(ClubNote(title=f"Note {group}-{n}", body="Record") for n in range(60))
        )
    original = export_snapshot(store, freeze=True)
    target = fresh_cosmos(store)
    initialize(target)
    assert not restore_cosmos(target, original, stop_after=1)["verified"]
    with pytest.raises(StorageUnavailable):
        target.read()
    with pytest.raises(ValueError, match="in-progress"):
        set_mode(target, "ready")
    assert restore(target, original, apply=True)["verified"]
    assert verify(target, original)["verified"]
    set_mode(target, "ready")
    assert len(target.read().records(ClubNote)) == 180
    assert (
        target.read().get(User, 1).password_hash
        == store.read(allow_maintenance=True).get(User, 1).password_hash
    )
    # Cleanup the second integration-test partition without affecting the fixture's original club.
    if not isinstance(target.container, MemoryContainer):
        for item in list(
            target.container.query_items(
                query="SELECT * FROM c WHERE c.club_id = @club",
                parameters=[{"name": "@club", "value": target.club}],
                partition_key=target.club,
            )
        ):
            target.container.delete_item(item["id"], partition_key=target.club)


def double_only(store):
    if not isinstance(getattr(store, "container", None), MemoryContainer):
        pytest.skip("Deterministic fault injection on the container double")
    return store.container


def test_timeout_after_commit_reconciles_without_replaying(store):
    container = double_only(store)
    called = []

    def fail_once():
        container.after_batch = None
        raise ServiceResponseError("Response lost after successful commit")

    container.after_batch = fail_once

    def goal(db):
        called.append(True)
        db.get(Match, 1).home_score += 1
        return db.get(Match, 1).home_score

    assert store.execute(goal, command_id="ambiguous1") == 1
    assert len(called) == 1 and store.read().get(Match, 1).home_score == 1


def test_batch_rejection_has_no_partial_writes_and_retry_is_bounded(store, monkeypatch):
    container = double_only(store)
    monkeypatch.setattr("app.storage.cosmos.time.sleep", lambda _: None)
    before = container.batch_count
    container.fail_status = 429
    with pytest.raises(StorageUnavailable):
        store.execute(lambda db: setattr(db.get(Player, 1), "name", "Uncommitted"))
    assert container.batch_count - before == store.settings.storage_retry_attempts
    assert store.read().get(Player, 1).name == "Player 1"


def test_conflict_retry_rechecks_authorization(store):
    container = double_only(store)
    first = True
    version = store.read().get(User, 1).session_version

    def revoke():
        nonlocal first
        if first:
            first = False
            container.before_batch = None
            store.execute(lambda db: setattr(db.get(User, 1), "session_version", 2))

    container.before_batch = revoke

    def authorize(db):
        if db.get(User, 1).session_version != version:
            raise PermissionError("Session revoked")

    with pytest.raises(PermissionError, match="revoked"):
        store.execute(lambda db: setattr(db.get(Match, 1), "home_score", 5), authorize=authorize)
    assert not first
    assert store.read().get(Match, 1).home_score == 0


def test_oversized_item_rejected_before_batch(store):
    if not hasattr(store, "container"):
        pytest.skip("Cosmos encoded item limit")
    with pytest.raises(StorageLimit):
        store.execute(lambda db: db.insert(ClubNote(title="Large", body="x" * 1_800_000)).id)
    assert not store.read().records(ClubNote)


def test_unknown_schema_and_missing_control_fail_closed(store):
    container = double_only(store)
    state = container.items[store.club, "club_state"]
    state["schema_version"] = 999
    with pytest.raises(StorageUnavailable):
        store.read()
    del container.items[store.club, "club_state"]
    with pytest.raises(StorageUnavailable):
        store.health()


def test_unique_key_policy_is_enforced_by_container(store):
    if not hasattr(store, "container"):
        pytest.skip("Cosmos unique keys")
    duplicate = store._read_item("user_1")
    duplicate = {k: v for k, v in duplicate.items() if not k.startswith("_")}
    duplicate["id"] = "user_999"
    with pytest.raises((exceptions.CosmosHttpResponseError, exceptions.CosmosBatchOperationError)):
        store.container.execute_item_batch([("create", (duplicate,))], partition_key=store.club)
    assert store._read_item("user_999") is None


def test_54_player_import_server_failure_rolls_back_the_entire_batch(store, monkeypatch):
    from app.domain.records import PlayerImport
    from app.import_players import apply_review, preview

    from .test_contract import payload

    if not hasattr(store, "container"):
        pytest.skip("Cosmos batch failure")
    source = payload(54)
    report = preview(store.read(), source)
    report.reviewed = True
    execute = store.container.execute_item_batch
    duplicate = {k: v for k, v in store._read_item("team_1").items() if not k.startswith("_")}

    def inject(operations, **kwargs):
        # The final operation fails after all player operations were evaluated by the service.
        return execute([*operations[:-1], ("create", (duplicate,))], **kwargs)

    monkeypatch.setattr(store.container, "execute_item_batch", inject)
    with pytest.raises(StorageUnavailable):
        store.execute(lambda db: apply_review(db, source, report))
    assert len(store.read().records(Player)) == 12
    assert not store.read().records(PlayerImport)
