"""Database-independent club records. Public IDs remain numeric."""

from datetime import datetime, timezone
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utcnow():
    return datetime.now(timezone.utc)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    table_name: ClassVar[str]

    @field_validator("*", mode="after")
    @classmethod
    def utc_dates(cls, value):
        if isinstance(value, datetime):
            return (
                value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
            )
        return value


class Team(Record):
    table_name: ClassVar[str] = "teams"
    id: int = 0
    name: str
    short_name: str
    color: str
    motto: str


class Player(Record):
    table_name: ClassVar[str] = "players"
    id: int = 0
    name: str
    nickname: str = ""
    team_id: int | None = None
    positions: str | None = None
    dominant_foot: str | None = None
    age_group: str | None = None
    photo_url: str = ""
    contact_preference: str = "Messenger"
    preferred_times: str | None = None
    availability: str | None = None
    injury_note: str = ""
    skill: float | None = None
    jersey: int | None = None
    is_captain: bool = False
    active: bool = True
    joined_at: datetime = Field(default_factory=utcnow)


class PlayerImport(Record):
    table_name: ClassVar[str] = "player_imports"
    import_id: str
    source: str
    source_key: str
    player_id: int
    source_fingerprint: str
    created_at: datetime = Field(default_factory=utcnow)


class User(Record):
    table_name: ClassVar[str] = "users"
    id: int = 0
    email: str
    password_hash: str
    role: str = "player"
    player_id: int
    session_version: int = 1
    created_at: datetime = Field(default_factory=utcnow)


class Season(Record):
    table_name: ClassVar[str] = "seasons"
    id: int = 0
    name: str
    active: bool = True


class Invitation(Record):
    table_name: ClassVar[str] = "invitations"
    id: int = 0
    player_id: int
    email: str
    token_hash: str
    expires_at: datetime
    used: bool = False


class Match(Record):
    table_name: ClassVar[str] = "matches"
    id: int = 0
    season_id: int
    title: str = "Saturday morning football"
    starts_at: datetime
    duration_minutes: int = 90
    location: str = "Lexington Recreation Center"
    address: str = "1625 Massachusetts Ave, Lexington, MA"
    pitch: str = "Center Field · Pitch 1"
    notes: str = "Bring a dark and a light shirt. Arrive 15 minutes early."
    kind: str = "classic"
    status: str = "scheduled"
    home_score: int = 0
    away_score: int = 0
    capacity: int = 14
    formation: str = "2-3-1"
    recurrence_id: str | None = None
    reminder_sent_at: datetime | None = None
    created_by: int | None = None


class RSVP(Record):
    table_name: ClassVar[str] = "rsvps"
    id: int = 0
    match_id: int
    player_id: int
    status: str
    updated_at: datetime = Field(default_factory=utcnow)


class Lineup(Record):
    table_name: ClassVar[str] = "lineups"
    id: int = 0
    match_id: int
    player_id: int
    side: str
    slot: int


class MatchEvent(Record):
    table_name: ClassVar[str] = "match_events"
    id: int = 0
    match_id: int
    player_id: int
    assist_player_id: int | None = None
    side: str
    kind: str = "goal"
    minute: int


class Rating(Record):
    table_name: ClassVar[str] = "ratings"
    id: int = 0
    match_id: int
    player_id: int
    author_id: int
    value: float


class ClubNote(Record):
    table_name: ClassVar[str] = "club_notes"
    id: int = 0
    title: str
    body: str
    category: str = "general"
    updated_at: datetime = Field(default_factory=utcnow)


class ReminderDispatch(Record):
    table_name: ClassVar[str] = "reminder_dispatches"
    dispatch_id: str
    match_id: int
    owner: str
    lease_until: datetime
    sent_at: datetime | None = None


RECORDS = (
    Team,
    Player,
    PlayerImport,
    User,
    Season,
    Invitation,
    Match,
    RSVP,
    Lineup,
    MatchEvent,
    Rating,
    ClubNote,
    ReminderDispatch,
)
