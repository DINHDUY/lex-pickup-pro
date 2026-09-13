"""SQL persistence. Only this adapter imports SQLAlchemy models into application workflows."""

from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ... import models as M
from ...domain.club import ClubData, key
from ...domain.records import RECORDS
from ..interfaces import StorageConflict, StorageUnavailable
from ..receipts import open_result, seal


def load_data(session, *, allow_maintenance=False):
    state = session.get(M.StorageState, 1)
    if state and state.mode != "ready" and not allow_maintenance:
        raise StorageUnavailable("Club storage is in maintenance mode")
    data = ClubData(counters=dict(state.counters) if state else {})
    for record_type in RECORDS:
        model = getattr(M, record_type.__name__)
        for row in session.scalars(select(model)):
            data.insert(record_type.model_validate(row))
    return data


def persist(session, before, after):
    after.validate()
    # Remove dependent records first, then insert parents before children.
    for kind in reversed(RECORDS):
        model = getattr(M, kind.__name__)
        for record_id in before.tables[kind.table_name].keys() - after.tables[kind.table_name].keys():
            session.delete(session.get(model, record_id))
        session.flush()
    for kind in RECORDS:
        model = getattr(M, kind.__name__)
        for row in after.records(kind):
            old = before.get(kind, key(row))
            if old == row:
                continue
            values = row.model_dump()
            if old is None:
                session.add(model(**values))
            else:
                target = session.get(model, key(row))
                for name, value in values.items():
                    setattr(target, name, value)
        session.flush()
    control = session.get(M.StorageState, 1)
    if control is None:
        session.add(M.StorageState(id=1, counters=after.counters, mode="ready"))
    else:
        control.counters = dict(after.counters)
    if session.bind.dialect.name == "postgresql":
        for kind in RECORDS:
            if "id" in kind.model_fields and after.records(kind):
                name = kind.table_name  # Static schema names, never user input.
                session.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                        f"GREATEST((SELECT MAX(id) FROM {name}), :counter))"
                    ),
                    {"counter": after.counters.get(name, 1)},
                )


class SqlStore:
    def __init__(self, session_factory):
        self.sessions = session_factory

    def health(self):
        try:
            with self.sessions() as session:
                session.execute(select(M.StorageState).limit(1))
                state = session.get(M.StorageState, 1)
                if state and state.mode != "ready":
                    raise StorageUnavailable("Club storage is in maintenance mode")
        except SQLAlchemyError as exc:
            raise StorageUnavailable("SQL storage is unavailable; check connectivity and migrations") from exc

    def read(self, *, allow_maintenance=False):
        try:
            with self.sessions() as session:
                if session.bind.dialect.name == "postgresql":
                    session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
                else:
                    session.execute(text("BEGIN"))
                return load_data(session, allow_maintenance=allow_maintenance)
        except SQLAlchemyError as exc:
            raise StorageUnavailable("SQL storage read failed") from exc

    def execute(self, operation, *, command_id=None, fingerprint="", authorize=None):
        command_id = command_id or uuid4().hex
        try:
            with self.sessions() as session:
                if session.bind.dialect.name == "sqlite":
                    session.execute(text("BEGIN IMMEDIATE"))
                else:
                    session.execute(text("SELECT pg_advisory_xact_lock(725491306)"))
                data = load_data(session)
                if authorize:
                    authorize(data)
                receipt = session.get(M.CommandReceipt, command_id)
                if receipt:
                    if receipt.fingerprint != fingerprint:
                        raise StorageConflict("Idempotency key was already used for another request")
                    return open_result(receipt.result)
                before = data.clone()
                result = jsonable_encoder(operation(data))
                persist(session, before, data)
                session.add(
                    M.CommandReceipt(command_id=command_id, fingerprint=fingerprint, result=seal(result))
                )
                session.commit()
                return result
        except IntegrityError as exc:
            raise StorageConflict("Record identity changed or already exists") from exc
        except SQLAlchemyError as exc:
            raise StorageUnavailable("SQL operation failed; retry with the same idempotency key") from exc

    def close(self):
        pass
