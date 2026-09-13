"""A bounded club snapshot used by pure business operations, never a SQL session."""

from copy import deepcopy

from .records import RECORDS, PlayerImport, ReminderDispatch


def key(record):
    if isinstance(record, PlayerImport):
        return record.import_id
    if isinstance(record, ReminderDispatch):
        return record.dispatch_id
    return record.id


class ClubData:
    def __init__(self, tables=None, counters=None):
        self.tables = tables or {model.table_name: {} for model in RECORDS}
        self.counters = counters or {}
        self.store = None
        self.request = None

    def records(self, model, **filters):
        return [
            r
            for r in self.tables[model.table_name].values()
            if all(getattr(r, name) == value for name, value in filters.items())
        ]

    def first(self, model, **filters):
        return next(iter(self.records(model, **filters)), None)

    def get(self, model, record_id):
        return self.tables[model.table_name].get(record_id)

    def insert(self, record):
        name = record.table_name
        if hasattr(record, "id"):
            maximum = max(self.counters.get(name, 0), max(self.tables[name], default=0))
            if record.id == 0:
                record.id = maximum + 1
            self.counters[name] = max(maximum, record.id)
        if key(record) in self.tables[name]:
            raise ValueError(f"Duplicate identity in {name}")
        self.tables[name][key(record)] = record
        return record

    def insert_many(self, records):
        for record in records:
            self.insert(record)

    def remove(self, record):
        self.tables[record.table_name].pop(key(record), None)

    def remove_where(self, model, **filters):
        for record in self.records(model, **filters):
            self.remove(record)

    def clone(self):
        return ClubData(deepcopy(self.tables), dict(self.counters))

    def dump(self):
        return {
            "tables": {
                name: [
                    r.model_dump(mode="json")
                    for r in sorted(records.values(), key=lambda record: str(key(record)))
                ]
                for name, records in self.tables.items()
            },
            "counters": self.counters,
        }

    @classmethod
    def load(cls, value):
        data = cls(counters=dict(value.get("counters", {})))
        if set(value["tables"]) != {m.table_name for m in RECORDS}:
            raise ValueError("Unknown or missing snapshot tables")
        for model in RECORDS:
            for record in value["tables"][model.table_name]:
                data.insert(model.model_validate(record))
        data.validate()
        return data

    def validate(self):
        from . import records as R

        references = {
            R.Player: {"team_id": R.Team},
            R.PlayerImport: {"player_id": R.Player},
            R.User: {"player_id": R.Player},
            R.Invitation: {"player_id": R.Player},
            R.Match: {"season_id": R.Season, "created_by": R.User},
            R.RSVP: {"match_id": R.Match, "player_id": R.Player},
            R.Lineup: {"match_id": R.Match, "player_id": R.Player},
            R.MatchEvent: {"match_id": R.Match, "player_id": R.Player, "assist_player_id": R.Player},
            R.Rating: {"match_id": R.Match, "player_id": R.Player, "author_id": R.User},
            R.ReminderDispatch: {"match_id": R.Match},
        }
        unique = {
            R.User: [("email",), ("player_id",)],
            R.PlayerImport: [("player_id",)],
            R.Invitation: [("token_hash",)],
            R.RSVP: [("match_id", "player_id")],
            R.Lineup: [("match_id", "player_id"), ("match_id", "side", "slot")],
            R.Rating: [("match_id", "player_id", "author_id")],
        }
        for model, fields in references.items():
            for record in self.records(model):
                for field, target in fields.items():
                    value = getattr(record, field)
                    if value is not None and self.get(target, value) is None:
                        raise ValueError(f"Missing {target.table_name} reference in {model.table_name}")
        for model, constraints in unique.items():
            for fields in constraints:
                values = [tuple(getattr(r, f) for f in fields) for r in self.records(model)]
                if len(set(values)) != len(values):
                    raise ValueError(f"Duplicate {model.table_name} identity")
        if any(t.id not in (1, 2) for t in self.records(R.Team)):
            raise ValueError("Only the two fixed club teams are supported")
        if len(self.records(R.Season, active=True)) > 1:
            raise ValueError("Only one season may be active")
        for user in self.records(R.User):
            if user.role not in ("player", "captain", "admin") or user.email != user.email.lower():
                raise ValueError("Invalid account role or email normalization")
        for player in self.records(R.Player):
            if player.skill is not None and not 1 <= player.skill <= 10:
                raise ValueError("Invalid player skill")
        for match in self.records(R.Match):
            if match.status not in ("scheduled", "live", "completed", "cancelled") or match.kind not in (
                "classic",
                "mixed",
            ):
                raise ValueError("Invalid match state")
            if min(match.home_score, match.away_score) < 0:
                raise ValueError("Invalid match score")
        for row in self.records(R.RSVP):
            if row.status not in ("going", "maybe", "out"):
                raise ValueError("Invalid RSVP")
        for row in self.records(R.Lineup):
            if row.side not in ("home", "away") or not 0 <= row.slot <= 10:
                raise ValueError("Invalid lineup")
        for row in self.records(R.Rating):
            if not 1 <= row.value <= 10:
                raise ValueError("Invalid rating")
