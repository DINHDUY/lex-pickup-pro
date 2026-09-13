from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    short_name: Mapped[str] = mapped_column(String(5))
    color: Mapped[str] = mapped_column(String(7))
    motto: Mapped[str] = mapped_column(String(120))


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    nickname: Mapped[str] = mapped_column(String(40), default="")
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True, nullable=True)
    positions: Mapped[str | None] = mapped_column(String(60), nullable=True)
    dominant_foot: Mapped[str | None] = mapped_column(String(10), nullable=True)
    age_group: Mapped[str | None] = mapped_column(String(12), nullable=True)
    photo_url: Mapped[str] = mapped_column(String(500), default="")
    contact_preference: Mapped[str] = mapped_column(String(80), default="Messenger")
    preferred_times: Mapped[str | None] = mapped_column(String(200), nullable=True)
    availability: Mapped[str | None] = mapped_column(String(20), nullable=True)
    injury_note: Mapped[str] = mapped_column(String(300), default="")
    skill: Mapped[float | None] = mapped_column(Float, nullable=True)
    jersey: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("skill >= 1 AND skill <= 10"),)


class PlayerImport(Base):
    """Local source identity; never used to grant application permissions."""

    __tablename__ = "player_imports"
    import_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), index=True)
    source_key: Mapped[str] = mapped_column(String(64), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), unique=True)
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="player")
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), unique=True)
    session_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("role IN ('player', 'captain', 'admin')"),)


class Season(Base):
    __tablename__ = "seasons"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    title: Mapped[str] = mapped_column(String(100), default="Saturday morning football")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=90)
    location: Mapped[str] = mapped_column(String(120), default="Lexington Recreation Center")
    address: Mapped[str] = mapped_column(String(250), default="1625 Massachusetts Ave, Lexington, MA")
    pitch: Mapped[str] = mapped_column(String(100), default="Center Field · Pitch 1")
    notes: Mapped[str] = mapped_column(
        Text, default="Bring a dark and a light shirt. Arrive 15 minutes early."
    )
    kind: Mapped[str] = mapped_column(String(10), default="classic")
    status: Mapped[str] = mapped_column(String(12), default="scheduled", index=True)
    home_score: Mapped[int] = mapped_column(Integer, default=0)
    away_score: Mapped[int] = mapped_column(Integer, default=0)
    capacity: Mapped[int] = mapped_column(Integer, default=14)
    formation: Mapped[str] = mapped_column(String(10), default="2-3-1")
    recurrence_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    __table_args__ = (
        CheckConstraint("home_score >= 0 AND away_score >= 0"),
        CheckConstraint("status IN ('scheduled', 'live', 'completed', 'cancelled')"),
        CheckConstraint("kind IN ('classic', 'mixed')"),
    )


class RSVP(Base):
    __tablename__ = "rsvps"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    status: Mapped[str] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("match_id", "player_id"),
        CheckConstraint("status IN ('going', 'maybe', 'out')"),
    )


class Lineup(Base):
    __tablename__ = "lineups"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    side: Mapped[str] = mapped_column(String(4))
    slot: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("match_id", "player_id"),
        UniqueConstraint("match_id", "side", "slot"),
        CheckConstraint("side IN ('home', 'away')"),
        CheckConstraint("slot >= 0 AND slot <= 10"),
    )


class MatchEvent(Base):
    __tablename__ = "match_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    assist_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    side: Mapped[str] = mapped_column(String(4))
    kind: Mapped[str] = mapped_column(String(15), default="goal")
    minute: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        CheckConstraint("side IN ('home', 'away')"),
        CheckConstraint("kind IN ('goal', 'own_goal', 'yellow_card', 'red_card')"),
    )


class Rating(Base):
    __tablename__ = "ratings"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    value: Mapped[float] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", "author_id"),
        CheckConstraint("value >= 1 AND value <= 10"),
    )


class ClubNote(Base):
    __tablename__ = "club_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20), default="general")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
