"""Normalized data shapes + the provider interface.

These dataclasses are the contract between a data source and the ingestion
layer. A provider's job is: raw API JSON -> these objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(slots=True)
class NPlayer:
    name: str
    provider_id: int | None = None
    position: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    shirt_number: int | None = None


@dataclass(slots=True)
class NTeam:
    provider_id: int
    name: str
    short_name: str | None = None
    tla: str | None = None
    crest_url: str | None = None
    founded: int | None = None
    club_colors: str | None = None
    venue: str | None = None
    website: str | None = None
    coach_name: str | None = None
    area_name: str | None = None
    squad: list[NPlayer] = field(default_factory=list)


@dataclass(slots=True)
class NCompetition:
    provider_id: int
    code: str
    name: str
    type: str | None = None
    emblem_url: str | None = None
    area_name: str | None = None
    area_code: str | None = None
    area_flag: str | None = None
    current_season: str | None = None
    current_season_start: date | None = None
    current_season_end: date | None = None
    current_matchday: int | None = None


@dataclass(slots=True)
class NGoal:
    minute: int | None = None
    injury_time: int | None = None
    type: str | None = None
    team_provider_id: int | None = None
    scorer_name: str | None = None
    scorer_provider_id: int | None = None
    assist_name: str | None = None
    home_score: int | None = None
    away_score: int | None = None


@dataclass(slots=True)
class NBooking:
    minute: int | None = None
    team_provider_id: int | None = None
    player_name: str | None = None
    card: str | None = None


@dataclass(slots=True)
class NSubstitution:
    minute: int | None = None
    team_provider_id: int | None = None
    player_in_name: str | None = None
    player_out_name: str | None = None


@dataclass(slots=True)
class NTeamMatchStats:
    """Per-team match statistics (depth provider only)."""

    team_provider_id: int | None = None
    possession: int | None = None  # percent
    shots: int | None = None
    shots_on_target: int | None = None
    corners: int | None = None
    fouls: int | None = None
    offsides: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    passes: int | None = None
    passes_accuracy: int | None = None  # percent
    saves: int | None = None
    xg: float | None = None


@dataclass(slots=True)
class NPlayerRating:
    """A player's line in a match.

    API-Football fills ``rating`` / ``position`` / ``number``; FPL fills
    ``bps`` / ``bonus`` / ``xg`` / ``xa``. Whatever the source doesn't provide
    stays ``None``.
    """

    player_name: str
    team_provider_id: int | None = None
    player_provider_id: int | None = None
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


@dataclass(slots=True)
class NMatch:
    provider_id: int
    competition_code: str
    competition_provider_id: int | None
    season: str
    utc_date: datetime
    status: str
    home_team: NTeam
    away_team: NTeam
    matchday: int | None = None
    stage: str | None = None
    group: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    home_score_ht: int | None = None
    away_score_ht: int | None = None
    winner: str | None = None
    duration: str | None = None
    venue: str | None = None
    provider_updated_at: datetime | None = None
    referees: list[dict] = field(default_factory=list)
    goals: list[NGoal] = field(default_factory=list)
    bookings: list[NBooking] = field(default_factory=list)
    substitutions: list[NSubstitution] = field(default_factory=list)
    team_stats: list[NTeamMatchStats] = field(default_factory=list)
    player_ratings: list[NPlayerRating] = field(default_factory=list)


@dataclass(slots=True)
class NStandingRow:
    team: NTeam
    position: int
    played: int = 0
    won: int = 0
    draw: int = 0
    lost: int = 0
    points: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    form: str | None = None
    stage: str | None = "REGULAR_SEASON"
    type: str = "TOTAL"
    group: str | None = None


@dataclass(slots=True)
class NStandings:
    competition: NCompetition
    season: str
    rows: list[NStandingRow] = field(default_factory=list)


@dataclass(slots=True)
class NScorer:
    player_name: str
    goals: int = 0
    player_provider_id: int | None = None
    team: NTeam | None = None
    position: str | None = None
    nationality: str | None = None
    date_of_birth: date | None = None
    played_matches: int | None = None
    assists: int | None = None
    penalties: int | None = None


class ProviderError(RuntimeError):
    """Raised on unrecoverable provider failures (auth, bad response, ...)."""


class BaseProvider(ABC):
    """Interface every data source implements."""

    name: str = "base"
    # True if the provider exposes match events / statistics / player ratings.
    supports_depth: bool = False

    @abstractmethod
    def list_competitions(self) -> list[NCompetition]: ...

    @abstractmethod
    def get_teams(
        self, code: str, season: str | None = None
    ) -> tuple[NCompetition, list[NTeam]]: ...

    @abstractmethod
    def get_standings(self, code: str, season: str | None = None) -> NStandings: ...

    @abstractmethod
    def get_matches(
        self,
        code: str,
        *,
        season: str | None = None,
        matchday: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[NMatch]: ...

    @abstractmethod
    def get_match(self, provider_id: int) -> NMatch: ...

    @abstractmethod
    def get_scorers(
        self, code: str, season: str | None = None, limit: int = 20
    ) -> tuple[NCompetition, list[NScorer]]: ...
