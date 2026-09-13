"""Encrypt cached command results, including one-time invitation links, at rest."""

import base64
import hashlib
import hmac
import json

from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings
from .interfaces import StorageUnavailable


def cipher():
    key = hmac.new(get_settings().jwt_secret.encode(), b"lex-command-receipt-v1", hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal(result):
    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
    return {"sealed_v1": cipher().encrypt(payload).decode()}


def open_result(value):
    try:
        return json.loads(cipher().decrypt(value["sealed_v1"].encode()))
    except (KeyError, TypeError, ValueError, InvalidToken) as exc:
        raise StorageUnavailable(
            "Command receipt cannot be read with this deployment's signing secret"
        ) from exc
