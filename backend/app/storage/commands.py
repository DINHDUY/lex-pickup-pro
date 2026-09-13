"""Run a named business command atomically; retries rerun validation on fresh data."""

import hashlib
import hmac
import json
import re
from functools import wraps
from uuid import uuid4

from fastapi import HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder

from ..config import get_settings
from ..domain.records import Player, User


def command(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        data = kwargs["db"]
        user = kwargs.get("user")
        request = data.request
        supplied = request.headers.get("Idempotency-Key") if request else None
        if supplied and not re.fullmatch(r"[a-zA-Z0-9_-]{16,128}", supplied):
            raise HTTPException(400, "Idempotency-Key must contain 16–128 URL-safe characters")
        command_id = hashlib.sha256(
            f"{user.id if user else 0}:{supplied or uuid4().hex}".encode()
        ).hexdigest()
        values = {
            k: v
            for k, v in kwargs.items()
            if k not in ("db", "user") and not isinstance(v, (Request, Response))
        }
        payload = json.dumps({"operation": fn.__name__, "values": jsonable_encoder(values)}, sort_keys=True)
        digest = hmac.new(get_settings().jwt_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

        def authorize(state):
            if user:
                current = state.get(User, user.id)
                if (
                    not current
                    or current.session_version != user.session_version
                    or not state.get(Player, current.player_id).active
                ):
                    raise HTTPException(401, "Account changed. Please sign in again.")

        def execute(state):
            bound = {**kwargs, "db": state}
            if user:
                bound["user"] = state.get(User, user.id)
            return fn(*args, **bound)

        return data.store.execute(execute, command_id=command_id, fingerprint=digest, authorize=authorize)

    return wrapped
