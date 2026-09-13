"""Idempotent initialization: python -m app.seed [--demo] [--admin-email EMAIL]."""

import argparse
import getpass
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import RSVP, ClubNote, Lineup, Match, MatchEvent, Player, Rating, Season, Team, User
from .security import password_hasher

ROSTER = [
    ("David Mitchell", "Mitch", 1, "CM,CAM", 8.4, 8, "Right", "35–44"),
    ("James O’Connor", "Jimmy", 1, "GK", 7.8, 1, "Right", "45+"),
    ("Michael Chen", "Mike", 1, "CB,CDM", 8.1, 4, "Right", "35–44"),
    ("Carlos Rivera", "El Maestro", 1, "CAM,CM", 8.7, 10, "Left", "35–44"),
    ("Thomas Walsh", "Tommy", 1, "CB,LB", 7.5, 5, "Left", "45+"),
    ("Duy Tran", "Duy", 1, "ST,RW", 8.5, 9, "Right", "35–44"),
    ("Patrick Murphy", "Paddy", 1, "CM,CDM", 7.6, 6, "Both", "45+"),
    ("Andre Silva", "Dre", 1, "LW,ST", 8.2, 11, "Left", "35–44"),
    ("Robert Kim", "Bobby", 1, "RB,CB", 7.4, 2, "Right", "35–44"),
    ("Hassan Ali", "Hass", 1, "CM,RW", 7.9, 7, "Right", "35–44"),
    ("Daniel Brooks", "Brooksy", 1, "ST", 7.7, 14, "Right", "45+"),
    ("Luis Fernandez", "Lucho", 1, "LB,CM", 7.8, 3, "Left", "35–44"),
    ("Alex Parker", "Parks", 2, "ST,LW", 8.8, 9, "Right", "25–34"),
    ("Ethan Williams", "Big E", 2, "GK", 8.0, 1, "Right", "25–34"),
    ("Noah Johnson", "Noah", 2, "CB,RB", 7.6, 4, "Right", "18–24"),
    ("Liam Nguyen", "Liam", 2, "CAM,CM", 8.5, 10, "Both", "25–34"),
    ("Oliver Scott", "Ollie", 2, "CB,CDM", 7.9, 5, "Right", "25–34"),
    ("Ryan Patel", "Rye", 2, "RW,ST", 8.3, 7, "Left", "25–34"),
    ("Jack Thompson", "JT", 2, "CM,CDM", 8.1, 8, "Right", "25–34"),
    ("Ben Anderson", "Benny", 2, "LW,ST", 8.0, 11, "Left", "18–24"),
    ("Marcus Davis", "MD", 2, "RB,CB", 7.7, 2, "Right", "25–34"),
    ("Sam Wilson", "Sammy", 2, "CM,LB", 7.5, 6, "Both", "25–34"),
    ("Tyler Robinson", "Ty", 2, "ST,RW", 7.9, 14, "Right", "18–24"),
    ("Kevin Park", "KP", 2, "LB,CM", 7.8, 3, "Left", "25–34"),
]


def seed(demo=False, admin_email=None, admin_player_id=None):
    if admin_player_id is not None and (not admin_email or demo):
        raise SystemExit("--admin-player-id requires --admin-email and cannot be used with --demo")
    if admin_email:
        try:
            admin_email = str(TypeAdapter(EmailStr).validate_python(admin_email)).lower()
        except ValidationError:
            raise SystemExit("Enter a valid administrator email address") from None
    settings = get_settings()
    if demo and (settings.app_env == "production" or not settings.demo_enabled):
        raise SystemExit("Demo seeding requires DEMO_ENABLED=true and a non-production environment")
    with SessionLocal() as db:
        if not db.get(Team, 1):
            db.add_all(
                [
                    Team(
                        id=1,
                        name="Old Gentlemen",
                        short_name="OG",
                        color="#245b46",
                        motto="Class is permanent.",
                    ),
                    Team(
                        id=2,
                        name="Young Boys",
                        short_name="YB",
                        color="#dbab53",
                        motto="The next generation.",
                    ),
                ]
            )
        if not db.scalar(select(Season).where(Season.active.is_(True))):
            db.add(Season(name=f"{datetime.now().year} season", active=True))
        db.commit()
        if demo:
            if db.scalar(select(User).where(User.email == "admin@lexpickup.club")):
                print("Demo data already exists. No changes made.")
                return
            if db.scalar(select(Player)):
                raise SystemExit("Demo seeding requires an empty roster; use a separate demo database")
            players = []
            for index, (name, nickname, team, positions, skill, jersey, foot, age) in enumerate(ROSTER, 1):
                p = Player(
                    name=name,
                    nickname=nickname,
                    team_id=team,
                    positions=positions,
                    skill=skill,
                    jersey=jersey,
                    dominant_foot=foot,
                    age_group=age,
                    is_captain=index in (1, 13),
                    availability="injured" if index == 11 else "available",
                    preferred_times="Saturday mornings",
                    injury_note="Recovering from an ankle sprain. Back in two weeks." if index == 11 else "",
                )
                db.add(p)
                players.append(p)
            db.flush()
            users = []
            for email, role, pid in [
                ("admin@lexpickup.club", "admin", 1),
                ("captain@lexpickup.club", "captain", 13),
                ("player@lexpickup.club", "player", 6),
            ]:
                u = User(
                    email=email,
                    role=role,
                    player_id=pid,
                    password_hash=password_hasher.hash("PickupPro2026!"),
                )
                db.add(u)
                users.append(u)
            db.flush()
            rng = random.Random(42)
            local = datetime.now(ZoneInfo("America/New_York"))
            next_game = (local + timedelta(days=(5 - local.weekday()) % 7)).replace(
                hour=10, minute=0, second=0, microsecond=0
            )
            if next_game <= local + timedelta(hours=1):
                next_game += timedelta(days=7)
            season = db.scalar(select(Season).where(Season.active.is_(True)))
            for week in range(-18, 5):
                historical = week < 0
                m = Match(
                    title="Saturday morning football" if week % 4 else "The Lexington derby",
                    starts_at=(next_game + timedelta(weeks=week)).astimezone(timezone.utc),
                    season_id=season.id,
                    status="completed" if historical else "scheduled",
                    kind="mixed" if week in (-12, -8, -4, 2) else "classic",
                    home_score=rng.randint(1, 6) if historical else 0,
                    away_score=rng.randint(0, 5) if historical else 0,
                    created_by=users[0].id,
                )
                db.add(m)
                db.flush()
                sides = {
                    "home": [players[1]] + rng.sample([p for p in players[:12] if p.id not in (2, 11)], 6),
                    "away": [players[13]] + rng.sample([p for p in players[12:] if p.id != 14], 6),
                }
                if m.kind == "mixed":
                    sides["home"][3], sides["away"][3] = sides["away"][3], sides["home"][3]
                if historical:
                    for side, squad in sides.items():
                        for slot, p in enumerate(squad):
                            db.add(Lineup(match_id=m.id, player_id=p.id, side=side, slot=slot))
                            db.add(RSVP(match_id=m.id, player_id=p.id, status="going"))
                            author = users[1] if p.id == users[0].player_id else users[0]
                            db.add(
                                Rating(
                                    match_id=m.id,
                                    player_id=p.id,
                                    author_id=author.id,
                                    value=round(min(10, max(5, p.skill + rng.uniform(-1, 1))), 1),
                                )
                            )
                        for _ in range(m.home_score if side == "home" else m.away_score):
                            scorer = rng.choices(squad[1:], weights=[p.skill**3 for p in squad[1:]])[0]
                            assist = rng.choice([p for p in squad[1:] if p.id != scorer.id])
                            db.add(
                                MatchEvent(
                                    match_id=m.id,
                                    player_id=scorer.id,
                                    assist_player_id=assist.id,
                                    side=side,
                                    kind="goal",
                                    minute=rng.randint(2, 89),
                                )
                            )
                else:
                    # Leave room for the signed-in demo player to respond.
                    going = [p for squad in sides.values() for p in squad if p.id not in (1, 6, 13)][:11]
                    for p in players:
                        if p.id in (1, 6, 13):
                            continue
                        state = (
                            "going" if p in going else ("out" if p.id == 11 else rng.choice(["maybe", "out"]))
                        )
                        db.add(RSVP(match_id=m.id, player_id=p.id, status=state))
                    if week == 0:
                        for side, squad in sides.items():
                            for slot, p in enumerate(squad):
                                if p in going:
                                    db.add(Lineup(match_id=m.id, player_id=p.id, side=side, slot=slot))
            db.add_all(
                [
                    ClubNote(
                        title="A little earlier, a little more football",
                        category="general",
                        body="Let’s aim to be at the pitch by 9:45. A quick warm-up means we can kick off at 10 sharp. See you Saturday!",
                    ),
                    ClubNote(
                        title="Pitch & parking",
                        category="pitch",
                        body="Center Field, Pitch 1. Use the Worthen Road parking lot. Booking is 10–11:30 am; captains should confirm the town permit before each session.",
                    ),
                    ClubNote(
                        title="The kit checklist",
                        category="equipment",
                        body="David: match balls and pump. Alex: bibs and cones. Everyone: water, shin guards, and both a light and a dark shirt.",
                    ),
                ]
            )
            db.commit()
            print("Created 24 players, 23 matches, and 3 demo accounts. Password: PickupPro2026!")
        elif admin_email:
            if db.scalar(select(User).where(User.email == admin_email.lower())):
                raise SystemExit("An account with that email already exists")
            if admin_player_id is not None:
                p = db.get(Player, admin_player_id)
                if not p or not p.active or db.scalar(select(User).where(User.player_id == p.id)):
                    raise SystemExit("Select an active player without an account")
            else:
                name = input("Admin display name: ").strip()
                if not 2 <= len(name) <= 80:
                    raise SystemExit("Name must have 2–80 characters")
                p = Player(name=name)
                db.add(p)
            password = getpass.getpass("New admin password (10–128 characters): ")
            if not 10 <= len(password) <= 128:
                raise SystemExit("Password must have 10–128 characters")
            if password != getpass.getpass("Confirm admin password: "):
                raise SystemExit("Passwords do not match")
            db.flush()
            db.add(
                User(
                    email=admin_email.lower(),
                    password_hash=password_hasher.hash(password),
                    role="admin",
                    player_id=p.id,
                )
            )
            db.commit()
            print("Administrator created.")
        else:
            print("Teams and active season initialized. Use --admin-email to create an administrator.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--admin-email")
    parser.add_argument("--admin-player-id", type=int)
    args = parser.parse_args()
    seed(args.demo, args.admin_email, args.admin_player_id)
