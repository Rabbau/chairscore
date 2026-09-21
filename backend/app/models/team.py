from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    short_name: Mapped[str | None] = mapped_column(String(80), default=None)
    tla: Mapped[str | None] = mapped_column(String(10), default=None)
    crest_url: Mapped[str | None] = mapped_column(String(300), default=None)

    founded: Mapped[int | None] = mapped_column(default=None)
    club_colors: Mapped[str | None] = mapped_column(String(120), default=None)
    venue: Mapped[str | None] = mapped_column(String(160), default=None)
    website: Mapped[str | None] = mapped_column(String(300), default=None)
    coach_name: Mapped[str | None] = mapped_column(String(120), default=None)
    area_name: Mapped[str | None] = mapped_column(String(80), default=None)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    players: Mapped[list[Player]] = relationship(  # noqa: F821
        back_populates="team", cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        return self.short_name or self.name


class TeamExternalRef(Base):
    """A club's id in another provider's system.

    The same club shows up under different ids in football-data.org (its
    league) and UEFA (its European ties); this table is what keeps it one
    ``Team`` row instead of two.
    """

    __tablename__ = "team_external_refs"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_team_external_ref"),
        UniqueConstraint("team_id", "provider", name="uq_team_external_ref_team"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[int] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    team: Mapped[Team] = relationship()
