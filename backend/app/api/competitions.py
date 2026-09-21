from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import match_query
from app.config import settings
from app.db import get_db
from app.models import Competition, Match, Scorer, Standing
from app.schemas import CompetitionOut, MatchOut, ScorersOut, StandingsOut
from app.schemas.scorer import ScorerOut
from app.schemas.standing import StandingRowOut, StandingsGroupOut

router = APIRouter(prefix="/api/competitions", tags=["competitions"])


def _get_competition(db: Session, code: str) -> Competition:
    comp = db.scalar(select(Competition).where(Competition.code == code.upper()))
    if comp is None:
        raise HTTPException(404, f"competition '{code}' not found")
    return comp


def _resolve_season(db: Session, model, comp_id: int, season: str | None) -> str | None:
    if season:
        return season
    if latest := db.scalar(
        select(func.max(model.season)).where(model.competition_id == comp_id)
    ):
        return latest
    return None


@router.get("", response_model=list[CompetitionOut])
def list_competitions(db: Session = Depends(get_db)):
    order = func.coalesce(Competition.type, "").desc()  # LEAGUE before CUP
    # The table is seeded with every football-data.org free-tier competition;
    # only the ones we sync have anything to show.
    stmt = select(Competition).where(Competition.code.in_(settings.served_competition_codes))
    return db.scalars(stmt.order_by(order, Competition.name)).all()


@router.get("/{code}", response_model=CompetitionOut)
def get_competition(code: str, db: Session = Depends(get_db)):
    return _get_competition(db, code)


@router.get("/{code}/seasons", response_model=list[str])
def list_seasons(code: str, db: Session = Depends(get_db)):
    """Seasons that have data stored, newest first."""
    comp = _get_competition(db, code)
    seasons = set(
        db.scalars(select(Match.season).where(Match.competition_id == comp.id).distinct()).all()
    )
    seasons |= set(
        db.scalars(
            select(Standing.season).where(Standing.competition_id == comp.id).distinct()
        ).all()
    )
    return sorted((s for s in seasons if s), reverse=True)


@router.get("/{code}/standings", response_model=StandingsOut)
def get_standings(
    code: str,
    season: str | None = Query(None, description="e.g. 2024; defaults to latest stored"),
    type: str = Query("TOTAL", description="TOTAL / HOME / AWAY"),
    db: Session = Depends(get_db),
):
    comp = _get_competition(db, code)
    resolved = _resolve_season(db, Standing, comp.id, season)
    rows = (
        db.scalars(
            select(Standing)
            .where(
                Standing.competition_id == comp.id,
                Standing.season == resolved,
                Standing.type == type.upper(),
            )
            .order_by(Standing.group_name, Standing.position)
        ).all()
        if resolved
        else []
    )

    groups: dict[tuple, StandingsGroupOut] = {}
    for row in rows:
        key = (row.type, row.group_name)
        grp = groups.get(key)
        if grp is None:
            grp = StandingsGroupOut(type=row.type, group_name=row.group_name, stage=row.stage)
            groups[key] = grp
        grp.rows.append(StandingRowOut.model_validate(row))

    return StandingsOut(
        competition=CompetitionOut.model_validate(comp),
        season=resolved,
        groups=list(groups.values()),
    )


@router.get("/{code}/matches", response_model=list[MatchOut])
def get_competition_matches(
    code: str,
    season: str | None = None,
    matchday: int | None = None,
    status: str | None = Query(None, description="SCHEDULED / FINISHED / IN_PLAY ..."),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(300, le=1000),
    db: Session = Depends(get_db),
):
    comp = _get_competition(db, code)
    stmt = match_query().where(Match.competition_id == comp.id)
    if season:
        stmt = stmt.where(Match.season == season)
    if matchday is not None:
        stmt = stmt.where(Match.matchday == matchday)
    if status:
        stmt = stmt.where(Match.status == status.upper())
    if date_from:
        stmt = stmt.where(Match.utc_date >= date_from)
    if date_to:
        stmt = stmt.where(Match.utc_date < date_to)
    stmt = stmt.order_by(Match.utc_date).limit(limit)
    return db.scalars(stmt).unique().all()


@router.get("/{code}/scorers", response_model=ScorersOut)
def get_scorers(
    code: str,
    season: str | None = None,
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    comp = _get_competition(db, code)
    resolved = _resolve_season(db, Scorer, comp.id, season)
    rows = (
        db.scalars(
            select(Scorer)
            .where(Scorer.competition_id == comp.id, Scorer.season == resolved)
            .order_by(Scorer.goals.desc(), Scorer.assists.desc().nullslast())
            .limit(limit)
        ).all()
        if resolved
        else []
    )
    scorers = [
        ScorerOut(
            rank=i,
            player_name=r.player_name,
            position=r.position,
            nationality=r.nationality,
            played_matches=r.played_matches,
            goals=r.goals,
            assists=r.assists,
            penalties=r.penalties,
            team=r.team,
        )
        for i, r in enumerate(rows, start=1)
    ]
    return ScorersOut(
        competition=CompetitionOut.model_validate(comp), season=resolved, scorers=scorers
    )
