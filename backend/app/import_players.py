"""Review and transactionally import a local Messenger member export. Dry-run by default."""

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .config import get_settings
from .domain.club import ClubData
from .domain.records import Player, PlayerImport, Team, User
from .storage.factory import get_store
from .storage.interfaces import StorageError, StorageLimit

MAX_BYTES = 5 * 1024 * 1024


class ImportProblem(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceRow(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    profileUrl: str = Field(max_length=2000)
    photoUrl: str = Field(max_length=500)
    role: str = Field(max_length=80)

    @field_validator("profileUrl", "photoUrl")
    @classmethod
    def https_url(cls, value):
        if value and (not re.match("^https://[^/\\s]+(?:/[^\\s]*)?$", value)):
            raise ValueError("Export URLs must be empty or HTTPS")
        return value


class ReviewRow(StrictModel):
    row: int = Field(ge=1)
    import_id: str
    raw_name: str
    name: str = Field(max_length=80)
    action: Literal["create", "match", "unchanged", "exclude", "unresolved"]
    existing_player_id: int | None = Field(default=None, gt=0)
    allow_name_collision: bool = False
    candidate_player_ids: list[int] = Field(default_factory=list)
    note: str = ""

    @field_validator("import_id")
    @classmethod
    def uuid(cls, value):
        if str(UUID(value)) != value:
            raise ValueError("import_id must be a canonical UUID")
        return value


class Review(StrictModel):
    version: Literal[1] = 1
    source: str = Field(default="messenger-members", pattern="^[a-z0-9][a-z0-9_-]{0,79}$")
    source_fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    reviewed: bool = False
    rows: list[ReviewRow] = Field(max_length=5000)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ImportProblem("JSON contains duplicate object keys")
        result[key] = value
    return result


def decode(payload: bytes):
    if len(payload) > MAX_BYTES:
        raise ImportProblem("File exceeds the 5 MB limit")
    try:
        return json.loads(payload.decode("utf-8-sig"), object_pairs_hook=no_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ImportProblem("Expected valid UTF-8 JSON") from exc


def read_source(payload: bytes) -> list[SourceRow]:
    data = decode(payload)
    if not isinstance(data, list) or not 1 <= len(data) <= 5000:
        raise ImportProblem("Source must be an array of 1–5000 member objects")
    rows = []
    for index, item in enumerate(data, 1):
        try:
            row = SourceRow.model_validate(item)
        except ValidationError as exc:
            raise ImportProblem(f"Invalid member fields at row {index}") from exc
        name, _ = clean_name(row.name)
        if name and (not 2 <= len(name) <= 80):
            raise ImportProblem(f"Player name must be 2–80 characters at row {index}")
        rows.append(row)
    return rows


def clean_name(value: str) -> tuple[str, str]:
    value = unicodedata.normalize("NFC", value)
    if any((unicodedata.category(c).startswith("C") and (not c.isspace()) for c in value)):
        raise ImportProblem("Names cannot contain invisible control characters")
    name = " ".join(value.split())
    if name == "Admin ·":
        return ("", "Badge-only row: missing identity; excluded for review")
    if name.endswith(" Admin ·"):
        return (name.removesuffix(" Admin ·"), "Removed trailing Messenger admin badge")
    return (name, "Whitespace/Unicode normalized" if name != value else "")


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def source_key(name: str) -> str:
    return hashlib.sha256(normalized(name).encode()).hexdigest()


def fingerprint(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def preview(db: ClubData, payload: bytes, previous: Review | None = None) -> Review:
    source = previous.source if previous else "messenger-members"
    rows = read_source(payload)
    counts = Counter((normalized(clean_name(row.name)[0]) for row in rows))
    names, mappings, old_rows = (defaultdict(list), defaultdict(list), defaultdict(list))
    for player in db.records(Player):
        names[normalized(player.name)].append(player.id)
    for mapping in [row for row in db.records(PlayerImport) if row.source == source]:
        mappings[mapping.source_key].append(mapping)
    if previous:
        for row in previous.rows:
            old_rows[source_key(clean_name(row.raw_name)[0])].append(row)
    has_imports = bool(mappings)
    result = Review(source=source, source_fingerprint=fingerprint(payload), rows=[])
    for index, row in enumerate(rows, 1):
        name, note = clean_name(row.name)
        key = source_key(name)
        mapped = mappings[key][0] if len(mappings[key]) == 1 else None
        old = old_rows[key][0] if len(old_rows[key]) == 1 else None
        action, player_id = ("create", None)
        import_id = mapped.import_id if mapped else old.import_id if old else str(uuid4())
        if not name:
            action = "exclude"
        elif counts[normalized(name)] > 1 or len(mappings[key]) > 1:
            action, note = ("unresolved", "Duplicate source name: explicitly resolve each identity")
            import_id = str(uuid4())
        elif mapped:
            action, player_id = ("unchanged", mapped.player_id)
        elif old:
            action, player_id = (old.action, old.existing_player_id)
            name, note = (old.name, old.note)
        elif names[normalized(name)]:
            action, note = ("unresolved", "Name collision: choose an explicit player ID or a distinct person")
        elif has_imports or previous:
            action, note = ("unresolved", "New or renamed source entry: review its identity before applying")
        result.rows.append(
            ReviewRow(
                row=index,
                raw_name=row.name,
                name=name,
                note=note,
                import_id=import_id,
                action=action,
                existing_player_id=player_id,
                allow_name_collision=old.allow_name_collision if old else False,
                candidate_player_ids=names[normalized(name)],
            )
        )
    return result


def apply_review(db: ClubData, payload: bytes, review: Review) -> dict[str, int]:
    """Validate and mutate a private snapshot; Store.execute commits all changes atomically."""
    rows = read_source(payload)
    if not review.reviewed:
        raise ImportProblem("Review the manifest, resolve entries, then set reviewed to true")
    if fingerprint(payload) != review.source_fingerprint:
        raise ImportProblem("Source changed since preview; generate a new review")
    if sorted((row.row for row in review.rows)) != list(range(1, len(rows) + 1)):
        raise ImportProblem("Manifest must cover every source row exactly once")
    if len({row.import_id for row in review.rows}) != len(review.rows):
        raise ImportProblem("Each manifest row must have a unique import_id")
    if any((row.action == "unresolved" for row in review.rows)):
        raise ImportProblem("Resolve or exclude all unresolved entries before applying")
    counts = dict(created=0, matched=0, unchanged=0, excluded=0, unresolved=0)
    if next(
        iter(
            [
                row.id
                for row in [
                    row
                    for row in db.records(User)
                    if row.email
                    in ["admin@lexpickup.club", "captain@lexpickup.club", "player@lexpickup.club"]
                ]
            ]
        ),
        None,
    ):
        raise ImportProblem("Use a separate real-club database; this database contains demo accounts")
    if set([row.id for row in db.records(Team)]) != {1, 2}:
        raise ImportProblem("Initialize the two club teams with python -m app.seed first")
    players = {p.id: p for p in db.records(Player)}
    imports = {m.import_id: m for m in db.records(PlayerImport)}
    target_ids = set()
    accepted_names = Counter((normalized(r.name) for r in review.rows if r.action != "exclude"))
    for row in review.rows:
        original = rows[row.row - 1]
        cleaned, _ = clean_name(original.name)
        key = source_key(cleaned)
        if row.raw_name != original.name:
            raise ImportProblem(f"Raw source name mismatch at row {row.row}")
        if row.action == "exclude":
            counts["excluded"] += 1
            continue
        if not cleaned or not 2 <= len(row.name) <= 80 or clean_name(row.name)[0] != row.name:
            raise ImportProblem(f"Invalid reviewed player name at row {row.row}")
        mapping = imports.get(row.import_id)
        if mapping:
            if mapping.source != review.source:
                raise ImportProblem(f"Import identity belongs to a different source at row {row.row}")
            if row.existing_player_id not in (None, mapping.player_id):
                raise ImportProblem(f"Import identity cannot be reassigned at row {row.row}")
            if mapping.source_key != key:
                if row.action != "match" or row.existing_player_id != mapping.player_id:
                    raise ImportProblem(f"Renamed entry needs an explicit match at row {row.row}")
                mapping.source_key = key
                mapping.source_fingerprint = review.source_fingerprint
            player = players[mapping.player_id]
            counts["unchanged"] += 1
        else:
            if row.action == "unchanged":
                raise ImportProblem(f"Import identity was not found at row {row.row}")
            if row.action == "match":
                player = players.get(row.existing_player_id)
                if player is None:
                    raise ImportProblem(f"Select an existing player ID at row {row.row}")
                if any((m.player_id == player.id for m in imports.values())):
                    raise ImportProblem(f"Reuse this player's existing import_id at row {row.row}")
                counts["matched"] += 1
            else:
                if row.existing_player_id is not None:
                    raise ImportProblem(f"Create cannot select an existing player at row {row.row}")
                collision = (
                    accepted_names[normalized(row.name)] > 1
                    or any((normalized(p.name) == normalized(row.name) for p in players.values()))
                    or any((m.source == review.source and m.source_key == key for m in imports.values()))
                )
                if collision and (not row.allow_name_collision):
                    raise ImportProblem(f"Name/source collision needs explicit review at row {row.row}")
                player = Player(name=row.name, photo_url=original.photoUrl)
                db.insert(player)
                players[player.id] = player
                counts["created"] += 1
            mapping = PlayerImport(
                import_id=row.import_id,
                source=review.source,
                source_key=key,
                source_fingerprint=review.source_fingerprint,
                player_id=player.id,
            )
            db.insert(mapping)
            imports[mapping.import_id] = mapping
        if player.id in target_ids:
            raise ImportProblem(f"Two accepted rows target the same player at row {row.row}")
        target_ids.add(player.id)
    return counts


def read_file(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read(MAX_BYTES + 1)
    with Path(path).open("rb") as handle:
        return handle.read(MAX_BYTES + 1)


def read_review(path: str) -> Review:
    try:
        return Review.model_validate(decode(read_file(path)))
    except ValidationError as exc:
        raise ImportProblem("Invalid review manifest; check its field types and decisions") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="Local source JSON, or - for standard input")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Default: preview without database writes")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--report", help="Write a new review JSON file (never overwrites an existing file)")
    parser.add_argument("--manifest", help="Reviewed manifest required by --apply")
    parser.add_argument("--previous-manifest", help="Carry stable identities into a new dry-run review")
    args = parser.parse_args()
    if args.apply and (not args.manifest or args.previous_manifest or args.report):
        parser.error("--apply requires --manifest and cannot be combined with preview options")
    if not args.apply and args.manifest:
        parser.error("Use --previous-manifest to carry forward an earlier review")
    if args.file == "-" and args.manifest == "-":
        parser.error("Source and manifest cannot both use standard input")
    try:
        payload = read_file(args.file)
        store = get_store()
        if args.apply:
            if get_settings().demo_enabled:
                raise ImportProblem("Set DEMO_ENABLED=false and select the real-club database")
            manifest = read_review(args.manifest)
            counts = store.execute(lambda db: apply_review(db, payload, manifest))
            print(json.dumps(counts))
        else:
            previous = read_review(args.previous_manifest) if args.previous_manifest else None
            review = preview(store.read(), payload, previous)
            output = review.model_dump_json(indent=2) + "\n"
            if args.report:
                import os

                fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(output)
            else:
                print(output, end="")
            print(json.dumps(dict(Counter((r.action for r in review.rows)))), file=sys.stderr)
    except (ImportProblem, OSError, ValueError) as exc:
        parser.exit(2, f"Import stopped: {exc}\n")
    except StorageLimit as exc:
        parser.exit(2, f"Import stopped: {exc}\n")
    except StorageError:
        parser.exit(
            2,
            "Import stopped: database operation failed; retry the same reviewed manifest after checking initialization and connectivity.\n",
        )


if __name__ == "__main__":
    main()
