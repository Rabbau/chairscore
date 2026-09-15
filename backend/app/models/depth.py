"""Depth data — match events beyond score: statistics, player ratings, and the
cross-provider id map that ties a football-data match to an API-Football fixture.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MatchExternalRef(Base):
    """A match's id in another provider's system (e.g. API-Football fixture id)."""

    __tablename__ = "match_external_refs"
    __table_args__ = (
        UniqueConstraint("match_id", "provider", name="uq_match_external_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[int] = mapped_column(index=True)
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    match: Mapped[Match] = relationship(back_populates="external_refs")  # noqa: F821


class MatchTeamStat(Base):
    __tablename__ = "match_team_stats"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", "source", name="uq_match_team_stat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), default=None)
    source: Mapped[str] = mapped_column(String(40), default="api-football")

    possession: Mapped[int | None] = mapped_column(default=None)
    shots: Mapped[int | None] = mapped_column(default=None)
    shots_on_target: Mapped[int | None] = mapped_column(default=None)
    corners: Mapped[int | None] = mapped_column(default=None)
    fouls: Mapped[int | None] = mapped_column(default=None)
    offsides: Mapped[int | None] = mapped_column(default=None)
    yellow_cards: Mapped[int | None] = mapped_column(default=None)
    red_cards: Mapped[int | None] = mapped_column(default=None)
    passes: Mapped[int | None] = mapped_column(default=None)
    passes_accuracy: Mapped[int | None] = mapped_column(default=None)
    saves: Mapped[int | None] = mapped_column(default=None)
    xg: Mapped[float | None] = mapped_column(Float, default=None)

    match: Mapped[Match] = relationship(back_populates="team_stats")  # noqa: F821
    team: Mapped[Team | None] = relationship()  # noqa: F821


class MatchPlayerRating(Base):
    """A player's line in a match — from API-Football (rating, minutes, position)
    or FPL (bps, bonus, xg, xa). Columns not provided by the source stay null."""

    __tablename__ = "match_player_ratings"
    __table_args__ = (
        UniqueConstraint(
            "match_id", "player_name", "team_id", "source", name="uq_match_player_rating"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), default=None)
    source: Mapped[str] = mapped_column(String(20), default="api-football")

    player_name: Mapped[str] = mapped_column(String(120))
    player_provider_id: Mapped[int | None] = mapped_column(default=None)
    rating: Mapped[float | None] = mapped_column(Float, default=None)
    minutes: Mapped[int | None] = mapped_column(default=None)
    position: Mapped[str | None] = mapped_column(String(20), default=None)
    number: Mapped[int | None] = mapped_column(default=None)
    is_starter: Mapped[bool] = mapped_column(default=False)
    captain: Mapped[bool] = mapped_column(default=False)
    goals: Mapped[int | None] = mapped_column(default=None)
    assists: Mapped[int | None] = mapped_column(default=None)
    yellow: Mapped[int | None] = mapped_column(default=None)
    red: Mapped[int | None] = mapped_column(default=None)
    # FPL extras
    xg: Mapped[float | None] = mapped_column(Float, default=None)
    xa: Mapped[float | None] = mapped_column(Float, default=None)
    bps: Mapped[int | None] = mapped_column(default=None)
    bonus: Mapped[int | None] = mapped_column(default=None)
    saves: Mapped[int | None] = mapped_column(default=None)

    match: Mapped[Match] = relationship(back_populates="player_ratings")  # noqa: F821
    team: Mapped[Team | None] = relationship()  # noqa: F821
