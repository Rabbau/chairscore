from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Scorer(Base):
    """Top-scorer table row for a competition + season."""

    __tablename__ = "scorers"
    __table_args__ = (
        UniqueConstraint(
            "competition_id", "season", "player_name", "team_id", name="uq_scorer_row"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    season: Mapped[str] = mapped_column(String(10), index=True)

    player_provider_id: Mapped[int | None] = mapped_column(default=None)
    player_name: Mapped[str] = mapped_column(String(120))
    position: Mapped[str | None] = mapped_column(String(40), default=None)
    nationality: Mapped[str | None] = mapped_column(String(80), default=None)
    date_of_birth: Mapped[date | None] = mapped_column(default=None)

    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), default=None)
    played_matches: Mapped[int | None] = mapped_column(default=None)
    goals: Mapped[int] = mapped_column(default=0)
    assists: Mapped[int | None] = mapped_column(default=None)
    penalties: Mapped[int | None] = mapped_column(default=None)

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    team: Mapped[Team | None] = relationship()  # noqa: F821
