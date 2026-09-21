from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.common import CompetitionRef, TeamOut


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    minute: int | None = None
    injury_time: int | None = None
    type: str | None = None
    team_id: int | None = None
    scorer_name: str | None = None
    assist_name: str | None = None
    home_score: int | None = None
    away_score: int | None = None


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    minute: int | None = None
    team_id: int | None = None
    player_name: str | None = None
    card: str | None = None


class SubstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    minute: int | None = None
    team_id: int | None = None
    player_in_name: str | None = None
    player_out_name: str | None = None


class RefereeOut(BaseModel):
    name: str | None = None
    type: str | None = None
    nationality: str | None = None


class TeamStatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    team_id: int | None = None
    source: str
    possession: int | None = None
    shots: int | None = None
    shots_on_target: int | None = None
    corners: int | None = None
    fouls: int | None = None
    offsides: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    passes: int | None = None
    passes_accuracy: int | None = None
    saves: int | None = None
    xg: float | None = None


class MergedTeamStatOut(BaseModel):
    """One team's stats with every source folded together (see ``app.merge``)."""

    team_id: int
    sources: list[str] = []
    # stat -> the source its value came from
    field_sources: dict[str, str] = {}
    possession: int | None = None
    shots: int | None = None
    shots_on_target: int | None = None
    corners: int | None = None
    fouls: int | None = None
    offsides: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    passes: int | None = None
    passes_accuracy: int | None = None
    saves: int | None = None
    xg: float | None = None


class PlayerRatingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    team_id: int | None = None
    source: str
    player_name: str
    rating: float | None = None
    minutes: int | None = None
    position: str | None = None
    number: int | None = None
    is_starter: bool = False
    captain: bool = False
    goals: int | None = None
    assists: int | None = None
    yellow: int | None = None
    red: int | None = None
    xg: float | None = None
    xa: float | None = None
    bps: int | None = None
    bonus: int | None = None
    saves: int | None = None


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_id: int
    season: str
    matchday: int | None = None
    stage: str | None = None
    group: str | None = None
    utc_date: datetime
    status: str
    home_score: int | None = None
    away_score: int | None = None
    home_score_ht: int | None = None
    away_score_ht: int | None = None
    home_score_pen: int | None = None
    away_score_pen: int | None = None
    winner: str | None = None
    competition: CompetitionRef
    home_team: TeamOut
    away_team: TeamOut


class HeadToHeadOut(BaseModel):
    """Past meetings, tallied from the current match's home team's perspective."""

    home_wins: int = 0
    draws: int = 0
    away_wins: int = 0
    matches: list[MatchOut] = []


class MatchDetailOut(MatchOut):
    venue: str | None = None
    duration: str | None = None
    referees: list[RefereeOut] = []
    goals: list[GoalOut] = []
    bookings: list[BookingOut] = []
    substitutions: list[SubstitutionOut] = []
    team_stats: list[TeamStatOut] = []
    merged_team_stats: list[MergedTeamStatOut] = []
    player_ratings: list[PlayerRatingOut] = []
    head_to_head: HeadToHeadOut | None = None
    home_form: list[MatchOut] = []
    away_form: list[MatchOut] = []

    @field_validator("referees", mode="before")
    @classmethod
    def _referees_default(cls, v: object) -> object:
        # Match.referees is a nullable JSON column (football-data doesn't
        # always send referees) — None should read as "no referees", not fail.
        return v if v is not None else []
