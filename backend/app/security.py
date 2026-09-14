from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Response
from pwdlib import PasswordHash

from .config import get_settings
from .domain.club import ClubData
from .domain.records import Player, User
from .storage.factory import get_data

password_hasher = PasswordHash.recommended()
DUMMY_HASH = password_hasher.hash("constant-time-unknown-account-check")
DB = Annotated[ClubData, Depends(get_data)]
COOKIE = get_settings().session_cookie_name
_attempts: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def throttle(request: Request, *, bucket="auth", limit=20):
    key = f"{bucket}:{request.client.host if request.client else 'unknown'}"
    now = monotonic()
    with _lock:
        # Bound memory and expire inactive IPs. Put a shared limiter at the edge for multiple workers.
        for old in [k for k, v in _attempts.items() if not v or now - v[-1] > 600]:
            del _attempts[old]
        queue = _attempts[key]
        while queue and now - queue[0] > 600:
            queue.popleft()
        if len(queue) >= limit:
            raise HTTPException(
                429, "Too many attempts. Please try again in 10 minutes.", headers={"Retry-After": "600"}
            )
        queue.append(now)


def set_session(response: Response, user: User):
    settings = get_settings()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(hours=12),
            "iss": "lex-pickup-pro",
            "aud": "lex-club",
            "ver": user.session_version,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    response.set_cookie(
        COOKIE,
        token,
        max_age=43200,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api",
    )


def get_user(request: Request, db: DB):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Please sign in to continue")
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=["HS256"],
            issuer="lex-pickup-pro",
            audience="lex-club",
            options={"require": ["sub", "exp", "iat"]},
        )
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Your session has expired. Please sign in again") from None
    if not user or payload.get("ver") != user.session_version or not db.get(Player, user.player_id).active:
        raise HTTPException(401, "Account is unavailable")
    return user


CurrentUser = Annotated[User, Depends(get_user)]


def get_captain(user: CurrentUser):
    if user.role not in ("captain", "admin"):
        raise HTTPException(403, "Only captains and admins can organize matches")
    return user


def get_admin(user: CurrentUser):
    if user.role != "admin":
        raise HTTPException(403, "Only admins can manage the club")
    return user


Captain = Annotated[User, Depends(get_captain)]
Admin = Annotated[User, Depends(get_admin)]
