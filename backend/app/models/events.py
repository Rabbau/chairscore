from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), default=None)

    minute: Mapped[int | None] = mapped_column(default=None)
    injury_time: Mapped[int | None] = mapped_column(default=None)
    type: Mapped[str | None] = mapped_column(String(20), default=None)  # REGULAR / OWN / PENALTY
    scorer_name: Mapped[str | None] = mapped_column(String(120), default=None)
    scorer_provider_id: Mapped[int | None] = mapped_column(default=None)
    assist_name: Mapped[str | None] = mapped_column(String(120), default=None)
    home_score: Mapped[int | None] = mapped_column(default=None)
    away_score: Mapped[int | None] = mapped_column(default=None)

    match: Mapped[Match] = relationship(back_populates="goals")  # noqa: F821
    team: Mapped[Team | None] = relationship()  # noqa: F821


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), default=None)

    minute: Mapped[int | None] = mapped_column(default=None)
    player_name: Mapped[str | None] = mapped_column(String(120), default=None)
    card: Mapped[str | None] = mapped_column(String(20), default=None)  # YELLOW / RED / YELLOW_RED

    match: Mapped[Match] = relationship(back_populates="bookings")  # noqa: F821
    team: Mapped[Team | None] = relationship()  # noqa: F821


class Substitution(Base):
    __tablename__ = "substitutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), default=None)

    minute: Mapped[int | None] = mapped_column(default=None)
    player_in_name: Mapped[str | None] = mapped_column(String(120), default=None)
    player_out_name: Mapped[str | None] = mapped_column(String(120), default=None)

    match: Mapped[Match] = relationship(back_populates="substitutions")  # noqa: F821
    team: Mapped[Team | None] = relationship()  # noqa: F821
