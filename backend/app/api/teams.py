from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import match_query, utcnow
from app.db import get_db
from app.models import Competition, CompetitionTeam, Match, Team
from app.schemas import MatchOut
from app.schemas.common import CompetitionOut, PlayerOut
from app.schemas.team import TeamDetailOut

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("/{team_id}", response_model=TeamDetailOut)
def get_team(
    team_id: int,
    match_limit: int = Query(8, le=30),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id, options=[selectinload(Team.players)])
    if team is None:
        raise HTTPException(404, f"team {team_id} not found")

    comps = db.scalars(
        select(Competition)
        .join(CompetitionTeam, CompetitionTeam.competition_id == Competition.id)
        .where(CompetitionTeam.team_id == team_id)
        .order_by(Competition.name)
    ).all()

    plays_for_team = or_(Match.home_team_id == team_id, Match.away_team_id == team_id)
    now = utcnow()

    recent = db.scalars(
        match_query()
        .where(plays_for_team, Match.utc_date < now)
        .order_by(Match.utc_date.desc())
        .limit(match_limit)
    ).unique().all()

    upcoming = db.scalars(
        match_query()
        .where(plays_for_team, Match.utc_date >= now)
        .order_by(Match.utc_date.asc())
        .limit(match_limit)
    ).unique().all()

    squad = sorted(
        team.players,
        key=lambda p: (p.shirt_number is None, p.shirt_number or 0, p.name),
    )

    detail = TeamDetailOut.model_validate(team)
    detail.squad = [PlayerOut.model_validate(p) for p in squad]
    detail.competitions = [CompetitionOut.model_validate(c) for c in comps]
    detail.recent_matches = [MatchOut.model_validate(m) for m in recent]
    detail.upcoming_matches = [MatchOut.model_validate(m) for m in upcoming]
    return detail
