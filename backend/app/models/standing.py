from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Standing(Base):
    """One row of a league table (team + season + table type)."""

    __tablename__ = "standings"
    __table_args__ = (
        UniqueConstraint(
            "competition_id",
            "season",
            "type",
            "group_name",
            "team_id",
            name="uq_standing_row",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    season: Mapped[str] = mapped_column(String(10), index=True)
    stage: Mapped[str | None] = mapped_column(String(40), default="REGULAR_SEASON")
    type: Mapped[str] = mapped_column(String(10), default="TOTAL")  # TOTAL / HOME / AWAY
    group_name: Mapped[str | None] = mapped_column(String(40), default=None)

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    position: Mapped[int] = mapped_column()
    played: Mapped[int] = mapped_column(default=0)
    won: Mapped[int] = mapped_column(default=0)
    draw: Mapped[int] = mapped_column(default=0)
    lost: Mapped[int] = mapped_column(default=0)
    points: Mapped[int] = mapped_column(default=0)
    goals_for: Mapped[int] = mapped_column(default=0)
    goals_against: Mapped[int] = mapped_column(default=0)
    goal_difference: Mapped[int] = mapped_column(default=0)
    form: Mapped[str | None] = mapped_column(String(20), default=None)  # "W,W,D,L,W"

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    team: Mapped[Team] = relationship()  # noqa: F821
