import csv
import hashlib
import io
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from . import schemas as S
from .config import get_settings
from .models import RSVP, ClubNote, Invitation, Lineup, Match, MatchEvent, Player, Rating, Season, Team, User
from .security import (
    COOKIE,
    DB,
    DUMMY_HASH,
    Admin,
    Captain,
    CurrentUser,
    password_hasher,
    set_session,
    throttle,
)
from .services import match_summaries, row_dict, statistics

settings = get_settings()
app = FastAPI(
    title="Lex Pickup Pro",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
api = APIRouter(prefix="/api/v1")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if origin and origin.rstrip("/") not in {o.rstrip("/") for o in settings.cors_origins}:
            return JSONResponse({"detail": "Request origin is not allowed"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site" and not origin:
            return JSONResponse({"detail": "Cross-site request is not allowed"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(IntegrityError)
async def conflict_handler(request, exc):
    return JSONResponse(
        {"detail": "This record changed or already exists. Refresh and try again."}, status_code=409
    )


def require(db, model, record_id):
    obj = db.get(model, record_id)
    if obj is None:
        raise HTTPException(404, "Record not found")
    return obj


def locked_match(db, match_id):
    match = db.scalar(select(Match).where(Match.id == match_id).with_for_update())
    if not match:
        raise HTTPException(404, "Match not found")
    return match


def user_payload(user, db):
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "player": row_dict(db.get(Player, user.player_id)),
    }


@api.get("/health")
def health(db: DB):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@api.get("/config")
def public_config():
    return {"demo_enabled": settings.demo_enabled, "registration_enabled": settings.registration_enabled}


@api.post("/auth/login")
def login(data: S.Login, request: Request, response: Response, db: DB):
    throttle(request)
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    verified = password_hasher.verify(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not verified or not db.get(Player, user.player_id).active:
        raise HTTPException(401, "Email or password is incorrect")
    set_session(response, user)
    return user_payload(user, db)


@api.post("/auth/register", status_code=201)
def register(data: S.Register, request: Request, response: Response, db: DB):
    throttle(request)
    if not settings.registration_enabled and not data.invite_token:
        raise HTTPException(403, "Registration is closed. Contact a captain.")
    if data.invite_token:
        invitation = db.scalar(
            select(Invitation)
            .where(
                Invitation.token_hash == hashlib.sha256(data.invite_token.encode()).hexdigest(),
                Invitation.used.is_(False),
                Invitation.expires_at > datetime.now(timezone.utc),
            )
            .with_for_update()
        )
        if not invitation or invitation.email != data.email.lower():
            raise HTTPException(403, "Invitation is invalid, expired, or for a different email address")
        player = require(db, Player, invitation.player_id)
        if not player.active or db.scalar(select(User).where(User.player_id == player.id)):
            raise HTTPException(409, "This profile cannot be claimed. Contact your administrator.")
        invitation.used = True
    else:
        if not secrets.compare_digest(data.invite_code, settings.club_invite_code):
            raise HTTPException(403, "Invalid club invitation code. Ask your captain for the current code.")
        if data.team_id is not None:
            require(db, Team, data.team_id)
        player = Player(name=data.name, team_id=data.team_id)
        db.add(player)
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(409, "Unable to register this email. Try signing in.")
    db.flush()
    user = User(
        email=data.email.lower(), password_hash=password_hasher.hash(data.password), player_id=player.id
    )
    db.add(user)
    db.commit()
    set_session(response, user)
    return user_payload(user, db)


@api.post("/auth/logout", status_code=204)
def logout(response: Response, user: CurrentUser, db: DB):
    user.session_version += 1
    db.commit()
    response.delete_cookie(COOKIE, path="/api", httponly=True, secure=settings.cookie_secure, samesite="lax")


@api.get("/auth/me")
def me(user: CurrentUser, db: DB):
    return user_payload(user, db)


@api.get("/teams")
def teams(user: CurrentUser, db: DB):
    return [row_dict(t) for t in db.scalars(select(Team).order_by(Team.id))]


@api.get("/seasons")
def seasons(user: CurrentUser, db: DB):
    return [row_dict(s) for s in db.scalars(select(Season).order_by(Season.id.desc()))]


@api.get("/players")
def players(user: CurrentUser, db: DB):
    return [
        row_dict(p) for p in db.scalars(select(Player).where(Player.active.is_(True)).order_by(Player.name))
    ]


@api.post("/seasons", status_code=201)
def create_season(data: S.SeasonInput, user: Admin, db: DB):
    for old in db.scalars(select(Season).where(Season.active.is_(True))):
        old.active = False
    season = Season(name=data.name, active=True)
    db.add(season)
    db.commit()
    return row_dict(season)


@api.post("/players", status_code=201)
def create_player(data: S.PlayerCreate, user: Admin, db: DB):
    if data.team_id is not None:
        require(db, Team, data.team_id)
    p = Player(**data.model_dump())
    db.add(p)
    db.commit()
    return row_dict(p)


@api.get("/players/{player_id}")
def player_detail(player_id: int, user: CurrentUser, db: DB):
    p = require(db, Player, player_id)
    stats = next(s for s in statistics(db)["players"] if s["player_id"] == player_id)
    ids = select(Lineup.match_id).where(Lineup.player_id == player_id)
    matches = list(
        db.scalars(
            select(Match)
            .where(Match.id.in_(ids), Match.status == "completed")
            .order_by(Match.starts_at.desc())
            .limit(10)
        )
    )
    return {**row_dict(p), "stats": stats, "matches": match_summaries(db, matches, user.player_id)}


@api.put("/players/{player_id}")
def update_player(player_id: int, data: S.PlayerFields, user: CurrentUser, db: DB):
    if user.player_id != player_id and user.role != "admin":
        raise HTTPException(403, "You can only edit your own profile")
    p = require(db, Player, player_id)
    for key, value in data.model_dump().items():
        setattr(p, key, value)
    db.commit()
    return row_dict(p)


@api.patch("/players/{player_id}/team")
def assign_team(player_id: int, data: S.TeamAssignment, user: Captain, db: DB):
    player = require(db, Player, player_id)
    if data.team_id is not None:
        require(db, Team, data.team_id)
    player.team_id = data.team_id
    db.commit()
    return row_dict(player)


@api.get("/admin/members")
def members(user: Admin, db: DB):
    users = {u.player_id: u for u in db.scalars(select(User))}
    return [
        {
            **row_dict(p),
            "email": users[p.id].email if p.id in users else None,
            "role": users[p.id].role if p.id in users else "player",
            "has_account": p.id in users,
        }
        for p in db.scalars(select(Player).order_by(Player.name))
    ]


@api.post("/admin/members/{player_id}/invite")
def invite_member(player_id: int, data: S.InviteInput, user: Admin, db: DB):
    player = require(db, Player, player_id)
    if not player.active or db.scalar(select(User).where(User.player_id == player_id)):
        raise HTTPException(400, "Only active players without accounts can be invited")
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(409, "This email already has a club account")
    db.execute(delete(Invitation).where(Invitation.player_id == player_id))
    token = secrets.token_urlsafe(32)
    db.add(
        Invitation(
            player_id=player_id,
            email=data.email.lower(),
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
    )
    db.commit()
    return {
        "url": f"{settings.frontend_url}/login?invite={token}",
        "expires_in_days": 7,
        "name": player.name,
        "email": data.email.lower(),
    }


@api.patch("/admin/members/{player_id}")
def update_member(player_id: int, data: S.MemberUpdate, user: Admin, db: DB):
    p = require(db, Player, player_id)
    account = db.scalar(select(User).where(User.player_id == player_id))
    if player_id == user.player_id and (data.role != "admin" or not data.active):
        raise HTTPException(400, "You cannot demote or deactivate your own administrator account")
    if not account and data.role != "player":
        raise HTTPException(400, "This player needs an account before assigning a role")
    p.team_id, p.active, p.is_captain = data.team_id, data.active, data.role in ("captain", "admin")
    if account:
        if account.role != data.role or not data.active:
            account.session_version += 1
        account.role = data.role
    db.commit()
    return {"ok": True}


@api.get("/matches")
def matches(user: CurrentUser, db: DB):
    return match_summaries(
        db, list(db.scalars(select(Match).order_by(Match.starts_at.desc()))), user.player_id
    )


@api.post("/matches", status_code=201)
def create_match(data: S.MatchCreate, user: Captain, db: DB):
    if data.starts_at < datetime.now(timezone.utc) - timedelta(minutes=5):
        raise HTTPException(400, "Schedule a game in the future")
    season = db.scalar(select(Season).where(Season.active.is_(True)))
    if not season:
        raise HTTPException(400, "No active season. Run the database initialization command.")
    values = data.model_dump(exclude={"repeat_weeks", "starts_at"})
    recurrence = str(uuid4()) if data.repeat_weeks > 1 else None
    local = data.starts_at.astimezone(ZoneInfo("America/New_York"))
    created = []
    formations = {10: "2-2", 12: "2-2-1", 14: "2-3-1", 16: "3-3-1", 18: "3-3-2", 20: "3-4-2", 22: "4-3-3"}
    for week in range(data.repeat_weeks):
        m = Match(
            **values,
            starts_at=(local + timedelta(weeks=week)).astimezone(timezone.utc),
            season_id=season.id,
            recurrence_id=recurrence,
            created_by=user.id,
            formation=formations[data.capacity],
        )
        db.add(m)
        created.append(m)
    db.commit()
    return match_summaries(db, created, user.player_id)


@api.put("/matches/{match_id}")
def update_match(match_id: int, data: S.MatchCreate, user: Captain, db: DB):
    m = locked_match(db, match_id)
    if m.status != "scheduled":
        raise HTTPException(400, "Only scheduled games can be rescheduled")
    if data.starts_at <= datetime.now(timezone.utc):
        raise HTTPException(400, "Schedule a game in the future")
    if data.repeat_weeks != 1:
        raise HTTPException(400, "Edit one game at a time; create a new series to repeat")
    if m.capacity != data.capacity:
        if db.scalar(select(Lineup).where(Lineup.match_id == match_id).limit(1)):
            raise HTTPException(400, "Clear the lineup before changing the game size")
        going = db.scalar(
            select(func.count()).select_from(RSVP).where(RSVP.match_id == match_id, RSVP.status == "going")
        )
        if going > data.capacity:
            raise HTTPException(400, "Capacity cannot be lower than the number of confirmed players")
        m.formation = {
            10: "2-2",
            12: "2-2-1",
            14: "2-3-1",
            16: "3-3-1",
            18: "3-3-2",
            20: "3-4-2",
            22: "4-3-3",
        }[data.capacity]
    m.reminder_sent_at = None
    for key, value in data.model_dump(exclude={"repeat_weeks"}).items():
        setattr(m, key, value)
    db.commit()
    return match_summaries(db, [m], user.player_id)


@api.get("/matches/{match_id}")
def match_detail(match_id: int, user: CurrentUser, db: DB):
    m = require(db, Match, match_id)
    summary = match_summaries(db, [m], user.player_id)[0]
    return {
        **summary,
        "players": [
            row_dict(p)
            for p in db.scalars(
                select(Player).where(
                    Player.id.in_(select(Lineup.player_id).where(Lineup.match_id == match_id))
                )
            )
        ],
        "rsvps": [row_dict(r) for r in db.scalars(select(RSVP).where(RSVP.match_id == match_id))],
        "lineup": [row_dict(r) for r in db.scalars(select(Lineup).where(Lineup.match_id == match_id))],
        "events": [
            row_dict(r)
            for r in db.scalars(
                select(MatchEvent).where(MatchEvent.match_id == match_id).order_by(MatchEvent.minute)
            )
        ],
        "my_ratings": [
            row_dict(r)
            for r in db.scalars(
                select(Rating).where(Rating.match_id == match_id, Rating.author_id == user.id)
            )
        ],
    }


@api.put("/matches/{match_id}/rsvp")
def rsvp(match_id: int, data: S.RSVPInput, user: CurrentUser, db: DB):
    # Serialize attendance admission on PostgreSQL. The uniqueness constraint handles duplicate submissions.
    m = db.scalar(select(Match).where(Match.id == match_id).with_for_update())
    if not m:
        raise HTTPException(404, "Match not found")
    starts = m.starts_at.replace(tzinfo=timezone.utc) if m.starts_at.tzinfo is None else m.starts_at
    if m.status != "scheduled" or starts <= datetime.now(timezone.utc):
        raise HTTPException(400, "Availability is closed for this game")
    existing = db.scalar(select(RSVP).where(RSVP.match_id == match_id, RSVP.player_id == user.player_id))
    if data.status == "going" and (not existing or existing.status != "going"):
        count = db.scalar(
            select(func.count()).select_from(RSVP).where(RSVP.match_id == match_id, RSVP.status == "going")
        )
        if count >= m.capacity:
            raise HTTPException(409, "This game is full. Choose Maybe to join the reserve list.")
    if existing:
        existing.status = data.status
    else:
        db.add(RSVP(match_id=match_id, player_id=user.player_id, status=data.status))
    db.commit()
    return {"status": data.status}


def validate_scores(db, match_id, home, away):
    counts = {"home": 0, "away": 0}
    for e in db.scalars(select(MatchEvent).where(MatchEvent.match_id == match_id)):
        if e.kind in ("goal", "own_goal"):
            counts[e.side] += 1
    if counts["home"] > home or counts["away"] > away:
        raise HTTPException(
            400, "The score cannot be lower than recorded goal events. Remove incorrect events first."
        )


@api.patch("/matches/{match_id}/result")
def result(match_id: int, data: S.ResultInput, user: Captain, db: DB):
    m = locked_match(db, match_id)
    validate_scores(db, match_id, data.home_score, data.away_score)
    if data.status == "completed":
        sides = set(db.scalars(select(Lineup.side).where(Lineup.match_id == match_id)))
        if sides != {"home", "away"}:
            raise HTTPException(400, "Assign players to both sides before completing the game")
    if m.status == "completed" and data.status in ("scheduled", "live"):
        raise HTTPException(400, "Completed games can be corrected, but cannot be reopened")
    for key, value in data.model_dump().items():
        setattr(m, key, value)
    db.commit()
    return row_dict(m)


@api.put("/matches/{match_id}/lineup")
def save_lineup(match_id: int, data: S.LineupInput, user: Captain, db: DB):
    m = locked_match(db, match_id)
    if m.status != "scheduled":
        raise HTTPException(400, "Lineups can only be changed before kickoff")
    size = m.capacity // 2
    if sum(map(int, data.formation.split("-"))) + 1 != size:
        raise HTTPException(400, "Formation must match the number of players per side")
    ids = [p.player_id for p in data.players]
    slots = [(p.side, p.slot) for p in data.players]
    if (
        len(set(ids)) != len(ids)
        or len(set(slots)) != len(slots)
        or any(p.slot >= size for p in data.players)
    ):
        raise HTTPException(400, "Each player and pitch position can only appear once")
    active = set(db.scalars(select(Player.id).where(Player.active.is_(True), Player.id.in_(ids))))
    if set(ids) != active:
        raise HTTPException(400, "Lineup contains an unavailable player")
    declined = set(db.scalars(select(RSVP.player_id).where(RSVP.match_id == match_id, RSVP.status == "out")))
    if set(ids) & declined:
        raise HTTPException(400, "A selected player is not going. Update availability first.")
    db.execute(delete(Lineup).where(Lineup.match_id == match_id))
    db.flush()
    db.add_all([Lineup(match_id=match_id, **p.model_dump()) for p in data.players])
    m.formation = data.formation
    db.commit()
    return {"ok": True}


@api.post("/matches/{match_id}/balance")
def balance(match_id: int, user: Captain, db: DB):
    m = locked_match(db, match_id)
    if m.status != "scheduled":
        raise HTTPException(400, "Only upcoming games can be balanced")
    available = list(
        db.scalars(
            select(Player)
            .join(RSVP, RSVP.player_id == Player.id)
            .where(RSVP.match_id == match_id, RSVP.status == "going", Player.active.is_(True))
        )
    )
    if len(available) < 2:
        raise HTTPException(400, "At least two players must be Going to build teams")
    # Greedy skill balancing with a goalkeeper on each side where available.
    available.sort(
        key=lambda p: (
            "GK" not in (p.positions or "").split(","),
            -(p.skill if p.skill is not None else 5.5),
            p.id,
        )
    )
    squads, totals = {"home": [], "away": []}, {"home": 0.0, "away": 0.0}
    for p in available[: m.capacity]:
        choices = [side for side in squads if len(squads[side]) < m.capacity // 2]
        side = min(choices, key=lambda s: (totals[s], len(squads[s]), s != "home"))
        squads[side].append(p)
        totals[side] += p.skill if p.skill is not None else 5.5
    db.execute(delete(Lineup).where(Lineup.match_id == match_id))
    db.flush()
    for side, squad in squads.items():
        for slot, p in enumerate(squad):
            db.add(Lineup(match_id=match_id, player_id=p.id, side=side, slot=slot))
    m.kind = "mixed"
    db.commit()
    return {
        "ok": True,
        "team_skill": totals,
        "estimated_player_ids": [p.id for squad in squads.values() for p in squad if p.skill is None],
        "estimated_skill": 5.5,
    }


@api.post("/matches/{match_id}/events", status_code=201)
def add_event(match_id: int, data: S.EventInput, user: Captain, db: DB):
    m = locked_match(db, match_id)
    if m.status not in ("live", "completed"):
        raise HTTPException(400, "Start the game or record a result before adding events")
    lineup = {p.player_id: p for p in db.scalars(select(Lineup).where(Lineup.match_id == match_id))}
    if data.player_id not in lineup:
        raise HTTPException(400, "Select a player in this game's lineup")
    side = lineup[data.player_id].side
    if data.assist_player_id:
        assist = lineup.get(data.assist_player_id)
        if (
            data.kind != "goal"
            or not assist
            or assist.side != side
            or data.assist_player_id == data.player_id
        ):
            raise HTTPException(400, "An assist must be a different teammate on a goal")
    if data.minute > m.duration_minutes:
        raise HTTPException(400, "Event minute exceeds the match duration")
    if data.kind == "own_goal":
        side = "away" if side == "home" else "home"
    e = MatchEvent(match_id=match_id, side=side, **data.model_dump())
    db.add(e)
    db.flush()
    if m.status == "live" and e.kind in ("goal", "own_goal"):
        setattr(m, f"{side}_score", getattr(m, f"{side}_score") + 1)
    else:
        validate_scores(db, match_id, m.home_score, m.away_score)
    db.commit()
    return row_dict(e)


@api.delete("/matches/{match_id}/events/{event_id}", status_code=204)
def remove_event(match_id: int, event_id: int, user: Captain, db: DB):
    m = locked_match(db, match_id)
    e = require(db, MatchEvent, event_id)
    if e.match_id != match_id:
        raise HTTPException(404, "Event not found in this game")
    if m.status == "live" and e.kind in ("goal", "own_goal"):
        setattr(m, f"{e.side}_score", max(0, getattr(m, f"{e.side}_score") - 1))
    db.delete(e)
    db.commit()


@api.put("/matches/{match_id}/ratings")
def rate(match_id: int, data: S.RatingInput, user: CurrentUser, db: DB):
    m = require(db, Match, match_id)
    ids = set(db.scalars(select(Lineup.player_id).where(Lineup.match_id == match_id)))
    if m.status != "completed" or data.player_id not in ids:
        raise HTTPException(400, "Rate a player who participated in a completed game")
    if user.player_id not in ids and user.role not in ("captain", "admin"):
        raise HTTPException(403, "Only participants and organizers can rate this game")
    if data.player_id == user.player_id:
        raise HTTPException(400, "You cannot rate yourself")
    existing = db.scalar(
        select(Rating).where(
            Rating.match_id == match_id, Rating.player_id == data.player_id, Rating.author_id == user.id
        )
    )
    if existing:
        existing.value = data.value
    else:
        db.add(Rating(match_id=match_id, author_id=user.id, **data.model_dump()))
    db.commit()
    return {"ok": True}


@api.get("/stats")
def stats(user: CurrentUser, db: DB, season_id: int | None = None, active_season: bool = False):
    if active_season:
        active = db.scalar(select(Season).where(Season.active.is_(True)))
        season_id = active.id if active else -1
    if season_id is not None:
        require(db, Season, season_id)
    return statistics(db, season_id)


@api.get("/notes")
def notes(user: CurrentUser, db: DB):
    return [row_dict(n) for n in db.scalars(select(ClubNote).order_by(ClubNote.updated_at.desc()))]


@api.post("/notes", status_code=201)
def add_note(data: S.NoteInput, user: Admin, db: DB):
    n = ClubNote(**data.model_dump())
    db.add(n)
    db.commit()
    return row_dict(n)


@api.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, user: Admin, db: DB):
    db.delete(require(db, ClubNote, note_id))
    db.commit()


@api.get("/export/{kind}")
def export(kind: str, user: CurrentUser, db: DB):
    if kind == "players":
        rows = statistics(db)["players"]
        team_names = {t.id: t.name for t in db.scalars(select(Team))}
        for row in rows:
            row["team"] = team_names.get(row["team_id"], "Unassigned")
        fields = [
            "name",
            "team_id",
            "team",
            "positions",
            "games",
            "goals",
            "assists",
            "wins",
            "win_rate",
            "rating",
            "attendance",
            "reliability",
            "clean_sheets",
        ]
    elif kind == "matches":
        rows = [row_dict(m) for m in db.scalars(select(Match).order_by(Match.starts_at.desc()))]
        fields = ["id", "title", "starts_at", "location", "kind", "status", "home_score", "away_score"]
    else:
        raise HTTPException(404, "Unknown export")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Neutralize spreadsheet formulas in user-controlled fields.
        writer.writerow(
            {
                k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v)
                for k, v in row.items()
                if k in fields
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="lex-{kind}.csv"'},
    )


@api.get("/matches/{match_id}/calendar")
def calendar(match_id: int, user: CurrentUser, db: DB):
    m = require(db, Match, match_id)

    def escape(s):
        return (
            s.replace("\\", "\\\\")
            .replace("\r", "")
            .replace("\n", "\\n")
            .replace(",", "\\,")
            .replace(";", "\\;")
        )

    def stamp(d):
        return d.strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Lex Pickup Pro//EN",
        "BEGIN:VEVENT",
        f"UID:match-{m.id}@lex-pickup-pro",
        f"DTSTAMP:{stamp(datetime.now(timezone.utc))}",
        f"DTSTART:{stamp(m.starts_at)}",
        f"DTEND:{stamp(m.starts_at + timedelta(minutes=m.duration_minutes))}",
        f"SUMMARY:{escape(m.title)}",
        f"LOCATION:{escape(m.location + ', ' + m.address)}",
        f"DESCRIPTION:{escape(m.notes)}",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
    # Fold by UTF-8 byte length as required by RFC 5545.
    folded = []
    for line in lines:
        part = ""
        for char in line:
            if len((part + char).encode()) > 73:
                folded.append(part)
                part = " "
            part += char
        folded.append(part)
    return Response(
        "\r\n".join(folded),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="lex-match-{m.id}.ics"'},
    )


app.include_router(api)
