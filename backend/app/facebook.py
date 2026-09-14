"""Facebook authentication and immediate, atomic roster self-claiming."""

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import EmailStr, TypeAdapter, ValidationError

from . import schemas as S
from .config import get_settings
from .domain.records import ExternalIdentity, FacebookOnboarding, Invitation, Player, Team, User, utcnow
from .security import COOKIE, DB, DUMMY_HASH, password_hasher, set_session, throttle

router = APIRouter(prefix="/auth")
settings = get_settings()
ONBOARDING_COOKIE = "facebook_onboarding"
LIFETIME = 900


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def cookie(response, name, value):
    response.set_cookie(
        name,
        value,
        max_age=LIFETIME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api",
    )


def clear_oauth(response):
    for name in ("facebook_oauth_state", "facebook_oauth_invite"):
        response.delete_cookie(name, path="/api")


def enabled():
    if not settings.facebook_auth_enabled:
        raise HTTPException(403, "Facebook authentication is disabled")


def identity(db, subject):
    return db.first(ExternalIdentity, provider="facebook", app_id=settings.facebook_app_id, subject=subject)


def active_user(db, user_id):
    user = db.get(User, user_id)
    if not user or not db.get(Player, user.player_id).active:
        raise HTTPException(401, "Account is unavailable. Contact your club administrator.")
    return user


def bind_identity(db, subject, user):
    existing = identity(db, subject)
    by_user = db.first(
        ExternalIdentity, provider="facebook", app_id=settings.facebook_app_id, user_id=user.id
    )
    if existing or by_user:
        if existing and existing.user_id == user.id:
            return
        raise HTTPException(409, "This Facebook identity or account is already linked. Sign in again.")
    db.insert(ExternalIdentity(app_id=settings.facebook_app_id, subject=subject, user_id=user.id))


def invitation_for(db, invitation_id, email):
    invitation = db.get(Invitation, invitation_id)
    if not invitation or invitation.used or invitation.expires_at <= utcnow() or invitation.email != email:
        raise HTTPException(409, "Invitation is expired or unavailable. Contact your club administrator.")
    return invitation


@router.get("/facebook/login")
def facebook_login(request: Request):
    enabled()
    throttle(request)
    now = utcnow()
    state = jwt.encode(
        {
            "nonce": secrets.token_urlsafe(32),
            "iat": now,
            "exp": now + timedelta(seconds=LIFETIME),
            "aud": "facebook-oauth",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    params = {
        "client_id": settings.facebook_app_id,
        "redirect_uri": settings.facebook_redirect_uri,
        "scope": "email,public_profile",
        "response_type": "code",
        "state": state,
    }
    if request.query_params.get("rerequest") == "1":
        params["auth_type"] = "rerequest"
    response = RedirectResponse("https://www.facebook.com/v20.0/dialog/oauth?" + urlencode(params), 302)
    cookie(response, "facebook_oauth_state", state)
    response.delete_cookie(ONBOARDING_COOKIE, path="/api")
    invite = request.query_params.get("invite", "")
    if invite:
        cookie(response, "facebook_oauth_invite", invite)
    else:
        response.delete_cookie("facebook_oauth_invite", path="/api")
    return response


def callback_result(request, db):
    enabled()
    throttle(request)
    state = request.query_params.get("state", "")
    stored = request.cookies.get("facebook_oauth_state", "")
    if not state or not stored or not secrets.compare_digest(state.encode(), stored.encode()):
        raise HTTPException(400, "Facebook sign-in was cancelled or expired. Please try again.")
    try:
        jwt.decode(
            state,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience="facebook-oauth",
            options={"require": ["exp", "iat", "nonce"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(400, "Facebook sign-in expired. Please try again.") from None
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(400, "Facebook sign-in was cancelled. Please try again and allow email access.")
    try:
        response = httpx.post(
            "https://graph.facebook.com/v20.0/oauth/access_token",
            data={
                "client_id": settings.facebook_app_id,
                "client_secret": settings.facebook_app_secret,
                "redirect_uri": settings.facebook_redirect_uri,
                "code": code,
            },
            timeout=10,
        )
        response.raise_for_status()
        access_token = response.json().get("access_token")
        if not access_token:
            raise ValueError("Missing access token")
        response = httpx.get(
            "https://graph.facebook.com/v20.0/me",
            params={"fields": "id,email,name", "access_token": access_token},
            timeout=10,
        )
        response.raise_for_status()
        profile = response.json()
        subject = str(profile.get("id") or "").strip()
        if not subject or len(subject) > 200:
            raise ValueError("Missing Facebook identity")
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        raise HTTPException(502, "Facebook sign-in failed. Please try again shortly.") from None

    token = secrets.token_urlsafe(32)
    invite_token = request.cookies.get("facebook_oauth_invite", "")

    def finish(current):
        linked = identity(current, subject)
        if linked:
            return {"user_id": active_user(current, linked.user_id).id}
        try:
            email = str(TypeAdapter(EmailStr).validate_python(profile.get("email", ""))).lower()
        except ValidationError:
            raise HTTPException(
                400, "Facebook did not share an email address. Try again and allow email access."
            ) from None
        existing = current.first(User, email=email)
        invitation = None
        if invite_token:
            invitation = current.first(Invitation, token_hash=token_hash(invite_token))
            invitation = invitation_for(current, invitation.id if invitation else None, email)
        if not existing and not invitation and not settings.facebook_roster_claiming_enabled:
            if not settings.registration_enabled:
                raise HTTPException(403, "Registration is closed. Contact a captain.")
            # Preserve open registration when the roster-claim rollout flag is off.
            player = current.insert(Player(name=str(profile.get("name") or "Facebook User")[:80]))
            user = current.insert(
                User(
                    email=email,
                    password_hash=password_hasher.hash(secrets.token_urlsafe(32)),
                    player_id=player.id,
                )
            )
            bind_identity(current, subject, user)
            return {"user_id": user.id}
        # Bounded cleanup stays within the Cosmos transactional batch limit.
        expired = sorted(current.records(FacebookOnboarding), key=lambda row: row.expires_at)
        for old in [row for row in expired if row.expires_at <= utcnow()][:20]:
            current.remove(old)
        current.insert(
            FacebookOnboarding(
                token_hash=token_hash(token),
                app_id=settings.facebook_app_id,
                subject=subject,
                email=email,
                name=str(profile.get("name") or "Facebook member")[:200],
                expires_at=utcnow() + timedelta(seconds=LIFETIME),
                invitation_id=invitation.id if invitation else None,
            )
        )
        return {"onboarding": True}

    result = db.store.execute(finish)
    response = RedirectResponse(
        settings.frontend_url.rstrip("/")
        + ("/onboarding/claim-profile" if result.get("onboarding") else "/"),
        302,
    )
    if result.get("onboarding"):
        cookie(response, ONBOARDING_COOKIE, token)
        response.delete_cookie(COOKIE, path="/api")
    else:
        set_session(response, active_user(db.store.read(), result["user_id"]))
        response.delete_cookie(ONBOARDING_COOKIE, path="/api")
    return response


@router.get("/facebook/callback")
def facebook_callback(request: Request, db: DB):
    try:
        response = callback_result(request, db)
    except HTTPException as exc:
        response = RedirectResponse(
            settings.frontend_url.rstrip("/") + "/login?" + urlencode({"facebook_error": exc.detail}),
            302,
        )
        response.delete_cookie(ONBOARDING_COOKIE, path="/api")
    clear_oauth(response)
    return response


def pending_session(db, digest):
    enabled()
    pending = db.first(FacebookOnboarding, token_hash=digest)
    if not pending or pending.expires_at <= utcnow() or pending.app_id != settings.facebook_app_id:
        raise HTTPException(401, "Your Facebook sign-in expired. Please sign in again.")
    return pending


def session_digest(request):
    token = request.cookies.get(ONBOARDING_COOKIE, "")
    if not token or len(token) > 100:
        raise HTTPException(401, "Please sign in with Facebook to choose a profile.")
    return token_hash(token)


def selection_allowed(db, pending):
    if pending.user_id or identity(db, pending.subject) or db.first(User, email=pending.email):
        raise HTTPException(409, "This account already exists. Sign in or link your existing account.")
    if not pending.invitation_id and not settings.facebook_roster_claiming_enabled:
        raise HTTPException(403, "Profile claiming is currently closed. Contact your club administrator.")


@router.get("/onboarding")
def onboarding(request: Request, db: DB):
    throttle(request, bucket="onboarding-read", limit=180)
    pending = pending_session(db, session_digest(request))
    existing = db.first(User, email=pending.email)
    return {
        "name": pending.name,
        "email": pending.email,
        "expires_at": pending.expires_at,
        "status": "completed" if pending.user_id else "link_required" if existing else "selection",
        "completed_player_id": db.get(User, pending.user_id).player_id if pending.user_id else None,
        "invited_player_id": db.get(Invitation, pending.invitation_id).player_id
        if pending.invitation_id
        else None,
    }


@router.get("/onboarding/players")
def candidates(
    request: Request,
    db: DB,
    search: str = Query(default="", max_length=80),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
):
    throttle(request, bucket="onboarding-read", limit=180)
    pending = pending_session(db, session_digest(request))
    selection_allowed(db, pending)
    invitation = invitation_for(db, pending.invitation_id, pending.email) if pending.invitation_id else None
    claimed = {user.player_id for user in db.records(User)}
    term = search.strip().casefold()
    players = sorted(
        (
            p
            for p in db.records(Player)
            if p.active
            and p.id not in claimed
            and (not invitation or p.id == invitation.player_id)
            and term in f"{p.name} {p.nickname}".casefold()
        ),
        key=lambda p: (p.name.casefold(), p.id),
    )
    return {
        "total": len(players),
        "players": [
            {
                "id": p.id,
                "name": p.name,
                "nickname": p.nickname,
                "photo_url": p.photo_url,
                "team_id": p.team_id,
                "team_name": db.get(Team, p.team_id).name if p.team_id else "Unassigned",
            }
            for p in players[offset : offset + limit]
        ],
    }


def complete(db, digest, *, player_id=None, password=None):
    """Run inside Store.execute: serialize competing claims and recheck every binding."""
    pending = pending_session(db, digest)
    if pending.user_id:
        user = active_user(db, pending.user_id)
        if user.session_version != pending.session_version:
            raise HTTPException(401, "Account changed. Please sign in again.")
        if player_id is not None and user.player_id != player_id:
            raise HTTPException(409, "This sign-in already claimed another profile. Sign in again.")
        return user.id
    if password is not None:
        user = db.first(User, email=pending.email)
        verified = password_hasher.verify(password, user.password_hash if user else DUMMY_HASH)
        if not user or not verified:
            raise HTTPException(401, "The existing account password is incorrect.")
        active_user(db, user.id)
        if pending.invitation_id:
            invitation = invitation_for(db, pending.invitation_id, pending.email)
            if invitation.player_id != user.player_id:
                raise HTTPException(
                    409, "This invitation is for another profile. Contact your administrator."
                )
    else:
        selection_allowed(db, pending)
        invitation = (
            invitation_for(db, pending.invitation_id, pending.email) if pending.invitation_id else None
        )
        if invitation and invitation.player_id != player_id:
            raise HTTPException(409, "Choose the profile specified by your invitation.")
        player = db.get(Player, player_id)
        if not player or not player.active or db.first(User, player_id=player_id):
            raise HTTPException(409, "This profile is no longer available. Please choose another profile.")
        user = db.insert(
            User(
                email=pending.email,
                player_id=player.id,
                password_hash=password_hasher.hash(secrets.token_urlsafe(32)),
            )
        )
        if invitation:
            invitation.used = True
    bind_identity(db, pending.subject, user)
    pending.user_id = user.id
    pending.session_version = user.session_version
    pending.completed_at = utcnow()
    return user.id


def finish_session(response, db, digest, user_id):
    current = db.store.read()
    pending = pending_session(current, digest)
    user = active_user(current, user_id)
    if pending.user_id != user.id or pending.session_version != user.session_version:
        raise HTTPException(401, "Account changed. Please sign in again.")
    set_session(response, user)
    # Retain the restricted cookie until expiry so a lost response can safely be retried.
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "player": current.get(Player, user.player_id).model_dump(mode="json"),
    }


@router.post("/onboarding/claim")
def claim(data: S.FacebookClaim, request: Request, response: Response, db: DB):
    throttle(request)
    digest = session_digest(request)
    user_id = db.store.execute(lambda current: complete(current, digest, player_id=data.player_id))
    return finish_session(response, db, digest, user_id)


@router.post("/onboarding/link")
def link(data: S.FacebookLink, request: Request, response: Response, db: DB):
    throttle(request)
    digest = session_digest(request)
    user_id = db.store.execute(lambda current: complete(current, digest, password=data.password))
    return finish_session(response, db, digest, user_id)


@router.post("/onboarding/cancel", status_code=204)
def cancel(request: Request, response: Response, db: DB):
    throttle(request)
    digest = session_digest(request)

    def remove(current):
        pending = current.first(FacebookOnboarding, token_hash=digest)
        if pending:
            current.remove(pending)

    db.store.execute(remove)
    response.delete_cookie(ONBOARDING_COOKIE, path="/api")
