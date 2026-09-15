from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(unique=True, index=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str | None] = mapped_column(String(20), default=None)
    emblem_url: Mapped[str | None] = mapped_column(String(300), default=None)

    area_name: Mapped[str | None] = mapped_column(String(80), default=None)
    area_code: Mapped[str | None] = mapped_column(String(10), default=None)
    area_flag: Mapped[str | None] = mapped_column(String(300), default=None)

    current_season: Mapped[str | None] = mapped_column(String(10), default=None)
    current_season_start: Mapped[date | None] = mapped_column(default=None)
    current_season_end: Mapped[date | None] = mapped_column(default=None)
    current_matchday: Mapped[int | None] = mapped_column(default=None)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teams: Mapped[list[CompetitionTeam]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )


class CompetitionTeam(Base):
    """Team participation in a competition for a given season."""

    __tablename__ = "competition_teams"
    __table_args__ = (
        UniqueConstraint("competition_id", "team_id", "season", name="uq_competition_team_season"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    season: Mapped[str] = mapped_column(String(10), index=True)

    competition: Mapped[Competition] = relationship(back_populates="teams")
    team: Mapped[Team] = relationship()  # noqa: F821
