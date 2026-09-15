"""Shared response schemas (no cross-imports -> no circular deps)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_id: int
    name: str
    short_name: str | None = None
    tla: str | None = None
    crest_url: str | None = None


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    position: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    shirt_number: int | None = None


class CompetitionRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    emblem_url: str | None = None


class CompetitionOut(CompetitionRef):
    type: str | None = None
    area_name: str | None = None
    area_flag: str | None = None
    current_season: str | None = None
    current_season_start: date | None = None
    current_season_end: date | None = None
    current_matchday: int | None = None
    last_synced_at: datetime | None = None
