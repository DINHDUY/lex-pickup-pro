"""Offline, checksummed transfer between SQL and Cosmos. Never changes provider configuration."""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from azure.core import MatchConditions
from azure.core.exceptions import AzureError

from .domain.club import ClubData
from .storage.cosmos.documents import SCHEMA_VERSION, document, encode, encoded, preflight
from .storage.factory import get_store
from .storage.interfaces import StorageError

FORMAT_VERSION = 1


def is_cosmos(store):
    return hasattr(store, "container")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def set_mode(store, mode):
    if mode not in ("ready", "maintenance"):
        raise ValueError("Unknown storage mode")
    if is_cosmos(store):
        control = store._control(allow_maintenance=True)
        if control.get("migration") and not control["migration"].get("verified"):
            raise ValueError("Finish and verify the in-progress restore before changing mode")
        replacement = {k: v for k, v in control.items() if not k.startswith("_")}
        replacement.update(mode=mode, revision=control["revision"] + 1)
        store.container.replace_item(
            "club_state", replacement, etag=control["_etag"], match_condition=MatchConditions.IfNotModified
        )
    else:
        from sqlalchemy import text

        from .models import StorageState

        with store.sessions() as db:
            db.execute(
                text(
                    "BEGIN IMMEDIATE"
                    if db.bind.dialect.name == "sqlite"
                    else "SELECT pg_advisory_xact_lock(725491306)"
                )
            )
            state = db.get(StorageState, 1)
            if state is None:
                db.add(StorageState(id=1, counters={}, mode=mode))
            else:
                state.mode = mode
            db.commit()


def frozen(store):
    if is_cosmos(store):
        return store._control(allow_maintenance=True)["mode"] == "maintenance"
    from .models import StorageState

    with store.sessions() as db:
        control = db.get(StorageState, 1)
        return bool(control and control.mode == "maintenance")


def receipts(store):
    if is_cosmos(store):
        docs = store.container.query_items(
            query="SELECT * FROM c WHERE c.club_id = @club AND c.kind = 'receipt'",
            parameters=[{"name": "@club", "value": store.club}],
            partition_key=store.club,
            max_item_count=100,
        )
        result = [{"command_id": d["id"].removeprefix("receipt_"), **d["data"]} for d in docs]
    else:
        from sqlalchemy import select

        from .models import CommandReceipt

        with store.sessions() as db:
            result = [
                {"command_id": r.command_id, "fingerprint": r.fingerprint, "result": r.result}
                for r in db.scalars(select(CommandReceipt))
            ]
    return sorted(result, key=lambda r: r["command_id"])


def export_snapshot(store, *, freeze=False):
    if freeze:
        set_mode(store, "maintenance")
    snapshot = {
        "format_version": FORMAT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_provider": "cosmos" if is_cosmos(store) else "sql",
        "frozen": frozen(store),
        "club_data": store.read(allow_maintenance=True).dump(),
        "receipts": receipts(store),
    }
    # A live export is only a planning preview: state and receipts need not share a cutover point.
    snapshot["checksum"] = digest(snapshot)
    return snapshot


def validate_snapshot(snapshot):
    if snapshot.get("format_version") != FORMAT_VERSION or snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported snapshot version")
    if digest({k: v for k, v in snapshot.items() if k != "checksum"}) != snapshot.get("checksum"):
        raise ValueError("Snapshot checksum mismatch")
    data = ClubData.load(snapshot["club_data"])
    ids = set()
    for receipt in snapshot["receipts"]:
        command_id = receipt["command_id"]
        if (
            not isinstance(command_id, str)
            or not 1 <= len(command_id) <= 64
            or not command_id.isalnum()
            or command_id in ids
        ):
            raise ValueError("Invalid or duplicate command receipt")
        ids.add(command_id)
    return data


def target_documents(store, snapshot):
    data = validate_snapshot(snapshot)
    docs = encode(data, store.club)
    for receipt in snapshot["receipts"]:
        item_id = "receipt_" + receipt["command_id"]
        docs[item_id] = document(
            store.club, "receipt", item_id, {k: v for k, v in receipt.items() if k != "command_id"}
        )
    records = [doc for doc in docs.values() if doc["kind"] != "receipt"]
    if (
        len(records) > store.settings.cosmos_max_documents
        or sum(len(encoded(d)) for d in records) > store.settings.cosmos_max_snapshot_bytes
    ):
        raise ValueError(
            "Snapshot exceeds the target's supported club size; adjust capacity before restoring"
        )
    return docs


def cosmos_documents(store):
    return {
        d["id"]: {k: v for k, v in d.items() if not k.startswith("_")}
        for d in store.container.query_items(
            query="SELECT * FROM c WHERE c.club_id = @club AND c.kind != 'control'",
            parameters=[{"name": "@club", "value": store.club}],
            partition_key=store.club,
            max_item_count=100,
        )
    }


def verify(store, snapshot):
    expected = validate_snapshot(snapshot)
    actual = store.read(allow_maintenance=True)
    if digest(actual.dump()) != digest(expected.dump()):
        raise ValueError("Target record/counter checksum mismatch")
    if receipts(store) != snapshot["receipts"]:
        raise ValueError("Target receipt checksum mismatch")
    if is_cosmos(store) and cosmos_documents(store) != target_documents(store, snapshot):
        raise ValueError("Target document identities/reservations mismatch")
    from .services import statistics

    if statistics(actual) != statistics(expected):
        raise ValueError("Target analytics mismatch")
    return {
        "verified": True,
        "checksum": snapshot["checksum"],
        "counts": {name: len(rows) for name, rows in actual.tables.items()},
    }


def restore_cosmos(store, snapshot, *, stop_after=None):
    store.check_configuration()
    expected = target_documents(store, snapshot)
    # Validate every item before reserving the inactive target, including unusually large match aggregates.
    for doc in expected.values():
        preflight([("create", (doc,))])
    control = store._control(allow_maintenance=True)
    migration = control.get("migration")
    if migration:
        if migration["checksum"] != snapshot["checksum"]:
            raise ValueError("Target belongs to a different restore; use a new empty target")
        if migration.get("verified"):
            return verify(store, snapshot)
    else:
        if cosmos_documents(store):
            raise ValueError("Restore requires an empty target partition")
        replacement = {k: v for k, v in control.items() if not k.startswith("_")}
        replacement.update(
            mode="maintenance",
            counters=snapshot["club_data"]["counters"],
            migration={"checksum": snapshot["checksum"], "next": 0, "verified": False},
        )
        store.container.replace_item(
            "club_state", replacement, etag=control["_etag"], match_condition=MatchConditions.IfNotModified
        )
    ordered = sorted(expected.values(), key=lambda doc: doc["id"])
    chunks = 0
    while True:
        control = store._control(allow_maintenance=True)
        index = control["migration"]["next"]
        if index >= len(ordered):
            break
        replacement = {k: v for k, v in control.items() if not k.startswith("_")}
        chunk = []
        for doc in ordered[index : index + 75]:
            proposed = chunk + [("create", (doc,))]
            try:
                preflight(
                    proposed + [("replace", ("club_state", replacement), {"if_match_etag": control["_etag"]})]
                )
            except StorageError:
                if not chunk:
                    raise
                break
            chunk = proposed
        replacement["migration"] = {**control["migration"], "next": index + len(chunk)}
        replacement["revision"] += 1
        # Checkpoint and records commit together. On timeout, rerun this command with the same snapshot.
        chunk.append(("replace", ("club_state", replacement), {"if_match_etag": control["_etag"]}))
        preflight(chunk)
        store.container.execute_item_batch(chunk, partition_key=store.club, retry_write=0)
        chunks += 1
        if stop_after and chunks >= stop_after:
            return {"verified": False, "next": index + len(chunk)}
    result = verify(store, snapshot)
    control = store._control(allow_maintenance=True)
    replacement = {k: v for k, v in control.items() if not k.startswith("_")}
    replacement["migration"] = {**control["migration"], "verified": True}
    store.container.replace_item(
        "club_state", replacement, etag=control["_etag"], match_condition=MatchConditions.IfNotModified
    )
    return result


def restore_sql(store, snapshot):
    from sqlalchemy import select, text

    from .domain.club import ClubData
    from .models import CommandReceipt, StorageState
    from .storage.sql import load_data, persist

    expected = validate_snapshot(snapshot)
    with store.sessions() as db:
        db.execute(
            text(
                "BEGIN IMMEDIATE"
                if db.bind.dialect.name == "sqlite"
                else "SELECT pg_advisory_xact_lock(725491306)"
            )
        )
        before = load_data(db, allow_maintenance=True)
        if any(before.tables.values()) or db.scalar(select(CommandReceipt).limit(1)):
            raise ValueError("SQL restore requires an empty, migrated database")
        persist(db, ClubData(), expected)
        db.flush()
        db.get(StorageState, 1).mode = "maintenance"
        db.add_all(CommandReceipt(**row) for row in snapshot["receipts"])
        db.commit()
    return verify(store, snapshot)


def restore(store, snapshot, *, apply=False, stop_after=None):
    data = validate_snapshot(snapshot)
    if not apply:
        if is_cosmos(store):
            for doc in target_documents(store, snapshot).values():
                preflight([("create", (doc,))])
        return {
            "dry_run": True,
            "frozen": snapshot["frozen"],
            "counts": {k: len(v) for k, v in data.tables.items()},
        }
    if not snapshot["frozen"]:
        raise ValueError("A live preview cannot be restored; freeze the source for a final export")
    return (
        restore_cosmos(store, snapshot, stop_after=stop_after)
        if is_cosmos(store)
        else restore_sql(store, snapshot)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    export = sub.add_parser("export")
    export.add_argument("--output", required=True)
    export.add_argument("--freeze", action="store_true")
    for name in ("import", "verify", "activate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--input", required=True)
        if name == "import":
            cmd.add_argument("--apply", action="store_true")
    sub.add_parser("pause")
    sub.add_parser("resume")
    args = parser.parse_args()
    store = get_store()
    try:
        if args.action == "export":
            # Reserve a private, exclusive file before freezing; never overwrite the backup or source.
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                snapshot = export_snapshot(store, freeze=args.freeze)
                json.dump(snapshot, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            print(json.dumps({"checksum": snapshot["checksum"], "frozen": snapshot["frozen"]}))
        elif args.action in ("pause", "resume"):
            set_mode(store, "maintenance" if args.action == "pause" else "ready")
            print(json.dumps({"mode": "maintenance" if args.action == "pause" else "ready"}))
        else:
            path = Path(args.input)
            if path.stat().st_mode & 0o077:
                raise ValueError("Snapshot contains private account material; chmod 600 before use")
            snapshot = json.loads(path.read_text())
            result = (
                restore(store, snapshot, apply=args.apply)
                if args.action == "import"
                else verify(store, snapshot)
            )
            if args.action == "activate":
                set_mode(store, "ready")
            print(json.dumps(result))
    except (ValueError, OSError, StorageError, AzureError) as exc:
        # SDK error payloads can include documents; never print them or credentials.
        message = str(exc) if isinstance(exc, (ValueError, StorageError)) else type(exc).__name__
        parser.exit(2, f"Storage transfer stopped: {message}. The source configuration was not changed.\n")
    finally:
        store.close()


if __name__ == "__main__":
    main()
