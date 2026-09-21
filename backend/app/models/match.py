from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# football-data.org match statuses
MATCH_STATUSES = (
    "SCHEDULED",
    "TIMED",
    "IN_PLAY",
    "PAUSED",
    "FINISHED",
    "SUSPENDED",
    "POSTPONED",
    "CANCELLED",
    "AWARDED",
)
LIVE_STATUSES = ("IN_PLAY", "PAUSED")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(unique=True, index=True)

    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    season: Mapped[str] = mapped_column(String(10), index=True)
    matchday: Mapped[int | None] = mapped_column(index=True, default=None)
    stage: Mapped[str | None] = mapped_column(String(40), default=None)
    group: Mapped[str | None] = mapped_column(String(40), default=None)

    utc_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="SCHEDULED")

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)

    home_score: Mapped[int | None] = mapped_column(default=None)
    away_score: Mapped[int | None] = mapped_column(default=None)
    home_score_ht: Mapped[int | None] = mapped_column(default=None)
    away_score_ht: Mapped[int | None] = mapped_column(default=None)
    # Penalty shoot-out score (cup ties only); home/away_score exclude it.
    home_score_pen: Mapped[int | None] = mapped_column(default=None)
    away_score_pen: Mapped[int | None] = mapped_column(default=None)
    winner: Mapped[str | None] = mapped_column(String(12), default=None)
    duration: Mapped[str | None] = mapped_column(String(20), default=None)
    venue: Mapped[str | None] = mapped_column(String(160), default=None)
    # [{"name": ..., "type": ..., "nationality": ...}] — free tier gives referees.
    referees: Mapped[list[dict] | None] = mapped_column(JSON, default=None)

    provider_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set when the depth provider (API-Football events/stats/ratings) last enriched this match.
    depth_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set when the FPL provider (per-player goals/assists/bonus/bps/xg) last enriched this match.
    fpl_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set when football-data.co.uk (shots/corners/cards/xG) last enriched this match.
    fdcouk_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set when UEFA's lineups + event feed last enriched this match.
    uefa_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    competition: Mapped[Competition] = relationship()  # noqa: F821
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])  # noqa: F821
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])  # noqa: F821

    goals: Mapped[list[Goal]] = relationship(  # noqa: F821
        back_populates="match", cascade="all, delete-orphan", order_by="Goal.minute"
    )
    bookings: Mapped[list[Booking]] = relationship(  # noqa: F821
        back_populates="match", cascade="all, delete-orphan", order_by="Booking.minute"
    )
    substitutions: Mapped[list[Substitution]] = relationship(  # noqa: F821
        back_populates="match", cascade="all, delete-orphan", order_by="Substitution.minute"
    )
    team_stats: Mapped[list[MatchTeamStat]] = relationship(  # noqa: F821
        back_populates="match", cascade="all, delete-orphan"
    )
    player_ratings: Mapped[list[MatchPlayerRating]] = relationship(  # noqa: F821
        back_populates="match", cascade="all, delete-orphan"
    )
    external_refs: Mapped[list[MatchExternalRef]] = relationship(  # noqa: F821
        back_populates="match", cascade="all, delete-orphan"
    )

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES

    @property
    def is_finished(self) -> bool:
        return self.status in ("FINISHED", "AWARDED")
