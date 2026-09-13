from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    email: EmailStr
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=128)


class Register(Login):
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=10, max_length=128)
    name: str = Field(min_length=2, max_length=80)
    team_id: Literal[1, 2] | None = None
    invite_code: str = Field(default="", max_length=100)
    invite_token: str = Field(default="", max_length=100)


class InviteInput(Input):
    email: EmailStr


class SeasonInput(Input):
    name: str = Field(min_length=3, max_length=80)


class PlayerFields(Input):
    name: str = Field(min_length=2, max_length=80)
    nickname: str = Field(default="", max_length=40)
    positions: str | None = Field(default=None, max_length=60)
    dominant_foot: Literal["Right", "Left", "Both"] | None = None
    age_group: Literal["18–24", "25–34", "35–44", "45+"] | None = None
    photo_url: str = Field(default="", max_length=500)
    contact_preference: str = Field(default="Messenger", max_length=80)
    preferred_times: str | None = Field(default=None, max_length=200)
    availability: Literal["available", "injured", "away"] | None = None
    injury_note: str = Field(default="", max_length=300)
    skill: float | None = Field(default=None, ge=1, le=10)
    jersey: int | None = Field(default=None, ge=0, le=99)

    @field_validator("photo_url")
    @classmethod
    def https_photo(cls, value):
        if value and not value.startswith("https://"):
            raise ValueError("Photo URL must use HTTPS")
        return value

    @field_validator("positions")
    @classmethod
    def known_positions(cls, value):
        if value is None or not value.strip():
            return None
        positions = [p.strip().upper() for p in value.split(",")]
        if not positions or any(
            p not in {"GK", "CB", "LB", "RB", "CDM", "CM", "CAM", "LW", "RW", "ST"} for p in positions
        ):
            raise ValueError("Use comma-separated soccer positions, e.g. CM,ST")
        return ",".join(dict.fromkeys(positions))


class PlayerCreate(PlayerFields):
    team_id: Literal[1, 2] | None = None


class TeamAssignment(Input):
    team_id: Literal[1, 2] | None


class MemberUpdate(Input):
    team_id: Literal[1, 2] | None = None
    active: bool
    role: Literal["player", "captain", "admin"]


class MatchCreate(Input):
    title: str = Field(default="Saturday morning football", min_length=3, max_length=100)
    starts_at: datetime
    duration_minutes: int = Field(default=90, ge=30, le=180)
    location: str = Field(default="Lexington Recreation Center", min_length=2, max_length=120)
    address: str = Field(default="1625 Massachusetts Ave, Lexington, MA", max_length=250)
    pitch: str = Field(default="Center Field · Pitch 1", max_length=100)
    notes: str = Field(default="Bring a dark and a light shirt. Arrive 15 minutes early.", max_length=2000)
    kind: Literal["classic", "mixed"] = "classic"
    capacity: Literal[10, 12, 14, 16, 18, 20, 22] = 14
    repeat_weeks: int = Field(default=1, ge=1, le=12)

    @field_validator("starts_at")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError("Start time must include a timezone")
        return value


class ResultInput(Input):
    home_score: int = Field(ge=0, le=99)
    away_score: int = Field(ge=0, le=99)
    status: Literal["scheduled", "live", "completed", "cancelled"]


class RSVPInput(Input):
    status: Literal["going", "maybe", "out"]


class Slot(Input):
    player_id: int = Field(gt=0)
    side: Literal["home", "away"]
    slot: int = Field(ge=0, le=10)


class LineupInput(Input):
    formation: Literal["2-3-1", "3-2-1", "2-2", "2-2-1", "3-3-1", "3-3-2", "3-4-2", "4-3-3"] = "2-3-1"
    players: list[Slot] = Field(max_length=22)


class EventInput(Input):
    player_id: int = Field(gt=0)
    assist_player_id: int | None = None
    kind: Literal["goal", "own_goal", "yellow_card", "red_card"] = "goal"
    minute: int = Field(ge=0, le=180)


class RatingInput(Input):
    player_id: int = Field(gt=0)
    value: float = Field(ge=1, le=10)


class NoteInput(Input):
    title: str = Field(min_length=2, max_length=100)
    body: str = Field(min_length=2, max_length=2000)
    category: Literal["general", "pitch", "equipment"] = "general"
