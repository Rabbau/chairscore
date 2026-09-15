from __future__ import annotations

from app.schemas.common import CompetitionOut, PlayerOut, TeamOut
from app.schemas.match import MatchOut


class TeamDetailOut(TeamOut):
    founded: int | None = None
    club_colors: str | None = None
    venue: str | None = None
    website: str | None = None
    coach_name: str | None = None
    area_name: str | None = None
    squad: list[PlayerOut] = []
    competitions: list[CompetitionOut] = []
    recent_matches: list[MatchOut] = []
    upcoming_matches: list[MatchOut] = []


__all__ = ["TeamOut", "PlayerOut", "TeamDetailOut"]
