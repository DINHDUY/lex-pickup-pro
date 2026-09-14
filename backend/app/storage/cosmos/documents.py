"""Versioned Cosmos documents; internal identities never become API fields."""

import hashlib
import json

from ...domain import records as R
from ...domain.club import ClubData
from ..interfaces import StorageLimit, StorageUnavailable

SCHEMA_VERSION = 1
CHILDREN = {R.RSVP: "rsvps", R.Lineup: "lineup", R.MatchEvent: "events", R.Rating: "ratings"}
KINDS = {
    model.__name__.lower(): model for model in R.RECORDS if model not in CHILDREN and model != R.PlayerImport
}
MAX_ITEM_BYTES = 1_800_000
MAX_BATCH_BYTES = 1_900_000


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def document(club, kind, item_id, data, identity=None):
    return {
        "id": item_id,
        "club_id": club,
        "kind": kind,
        "schema_version": SCHEMA_VERSION,
        "identity_key": identity or item_id,
        "data": data,
    }


def encode(data, club):
    docs = {}
    for kind, model in KINDS.items():
        for record in data.records(model):
            record_id = record.dispatch_id if model == R.ReminderDispatch else record.id
            item_id = f"{kind}_{record_id}"
            if model == R.Invitation:
                item_id = f"invitation_{record.token_hash}"
            doc = document(club, kind, item_id, record.model_dump(mode="json"))
            if model == R.ExternalIdentity:
                identity = encoded([record.provider, record.app_id, record.subject])
                doc["identity_key"] = "external_" + hashlib.sha256(identity).hexdigest()
            if model == R.FacebookOnboarding:
                doc["identity_key"] = "onboarding_" + record.token_hash
            if model == R.Player:
                imported = data.first(R.PlayerImport, player_id=record.id)
                if imported:
                    doc["import"] = imported.model_dump(mode="json")
                    doc["identity_key"] = f"import_{imported.import_id}"
            if model == R.User:
                doc["identity_key"] = f"account_player_{record.player_id}"
                email_id = "email_" + hashlib.sha256(record.email.lower().encode()).hexdigest()
                docs[email_id] = document(club, "email", email_id, {"user_id": record.id})
            if model == R.Invitation:
                pointer_id = f"invitation_player_{record.player_id}"
                previous = docs.get(pointer_id)
                if previous is None or previous["data"]["invitation_id"] < record.id:
                    docs[pointer_id] = document(
                        club,
                        "invitation_pointer",
                        pointer_id,
                        {"invitation_id": record.id, "token_hash": record.token_hash},
                    )
            if model == R.Match:
                for child, field in CHILDREN.items():
                    doc[field] = [
                        r.model_dump(mode="json")
                        for r in sorted(data.records(child, match_id=record.id), key=lambda row: row.id)
                    ]
            docs[item_id] = doc
    return docs


def decode(docs, counters):
    docs = list(docs)
    state = ClubData(counters=dict(counters))
    for doc in docs:
        if doc.get("schema_version") != SCHEMA_VERSION:
            raise StorageUnavailable("Unknown document version; run the storage upgrade check")
        kind = doc.get("kind")
        if kind in ("email", "invitation_pointer"):
            continue
        if kind not in KINDS:
            raise StorageUnavailable("Unknown club document kind")
        state.insert(KINDS[kind].model_validate(doc["data"]))
        if kind == "player" and doc.get("import"):
            state.insert(R.PlayerImport.model_validate(doc["import"]))
        if kind == "match":
            for child, field in CHILDREN.items():
                for row in doc[field]:
                    state.insert(child.model_validate(row))
    state.validate()
    if docs:
        club = docs[0]["club_id"]
        actual = {d["id"]: {k: v for k, v in d.items() if not k.startswith("_")} for d in docs}
        if actual != encode(state, club):
            raise StorageUnavailable("Document identity, provenance or account reservations are inconsistent")
    return state


def preflight(operations):
    if len(operations) > 100:
        raise StorageLimit("Cosmos atomic command exceeds 100 operations; no changes were written")
    for operation in operations:
        if operation[0] in ("create", "replace"):
            if len(encoded(operation[1][-1])) > MAX_ITEM_BYTES:
                raise StorageLimit("Club record exceeds the safe Cosmos item size; no changes were written")
    # Conservative allowance for SDK batch envelopes and headers.
    if len(encoded(operations)) + len(operations) * 1024 > MAX_BATCH_BYTES:
        raise StorageLimit("Cosmos atomic command exceeds its safe request size; no changes were written")
