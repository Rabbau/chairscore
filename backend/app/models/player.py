from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int | None] = mapped_column(unique=True, index=True, default=None)
    name: Mapped[str] = mapped_column(String(120), index=True)
    position: Mapped[str | None] = mapped_column(String(40), default=None)
    date_of_birth: Mapped[date | None] = mapped_column(default=None)
    nationality: Mapped[str | None] = mapped_column(String(80), default=None)
    shirt_number: Mapped[int | None] = mapped_column(default=None)

    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), index=True, default=None)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    team: Mapped[Team | None] = relationship(back_populates="players")  # noqa: F821
