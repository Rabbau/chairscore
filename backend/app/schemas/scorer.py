from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.common import CompetitionOut, TeamOut


class ScorerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    player_name: str
    position: str | None = None
    nationality: str | None = None
    played_matches: int | None = None
    goals: int
    assists: int | None = None
    penalties: int | None = None
    team: TeamOut | None = None


class ScorersOut(BaseModel):
    competition: CompetitionOut
    season: str | None = None
    scorers: list[ScorerOut] = []
