"""SQLAlchemy models. Importing this package registers every mapper."""

from app.models.competition import Competition, CompetitionTeam
from app.models.depth import MatchExternalRef, MatchPlayerRating, MatchTeamStat
from app.models.events import Booking, Goal, Substitution
from app.models.match import Match
from app.models.player import Player
from app.models.scorer import Scorer
from app.models.standing import Standing
from app.models.team import Team

__all__ = [
    "Competition",
    "CompetitionTeam",
    "Team",
    "Player",
    "Match",
    "Goal",
    "Booking",
    "Substitution",
    "Standing",
    "Scorer",
    "MatchExternalRef",
    "MatchTeamStat",
    "MatchPlayerRating",
]
