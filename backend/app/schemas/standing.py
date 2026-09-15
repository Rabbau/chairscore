from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.common import CompetitionOut, TeamOut


class StandingRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    played: int
    won: int
    draw: int
    lost: int
    points: int
    goals_for: int
    goals_against: int
    goal_difference: int
    form: str | None = None
    team: TeamOut


class StandingsGroupOut(BaseModel):
    type: str = "TOTAL"
    group_name: str | None = None
    stage: str | None = None
    rows: list[StandingRowOut] = []


class StandingsOut(BaseModel):
    competition: CompetitionOut
    season: str | None = None
    groups: list[StandingsGroupOut] = []
