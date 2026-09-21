from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from app.api.deps import match_query
from app.db import get_db
from app.merge import merge_team_stats
from app.models import Competition, Match
from app.schemas import MatchDetailOut, MatchOut
from app.schemas.match import HeadToHeadOut, MergedTeamStatOut

router = APIRouter(prefix="/api/matches", tags=["matches"])

_FINISHED = ("FINISHED", "AWARDED")


@router.get("", response_model=list[MatchOut])
def list_matches(
    on: date | None = Query(None, alias="date", description="single day (UTC), default today"),
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
    competition: str | None = Query(None, description="competition code, e.g. PL"),
    limit: int = Query(500, le=1000),
    db: Session = Depends(get_db),
):
    if date_from or date_to:
        start = datetime.combine(date_from or date.today(), time.min)
        end = datetime.combine(date_to or (date_from or date.today()), time.min) + timedelta(days=1)
    else:
        day = on or date.today()
        start = datetime.combine(day, time.min)
        end = start + timedelta(days=1)

    stmt = match_query().where(Match.utc_date >= start, Match.utc_date < end)
    if status:
        stmt = stmt.where(Match.status == status.upper())
    if competition:
        stmt = stmt.join(Competition, Match.competition_id == Competition.id).where(
            Competition.code == competition.upper()
        )
    stmt = stmt.order_by(Match.utc_date, Match.id).limit(limit)
    return db.scalars(stmt).unique().all()


def _team_form(db: Session, team_id: int, before: datetime, limit: int = 5) -> list[Match]:
    stmt = (
        match_query()
        .where(
            or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
            Match.utc_date < before,
            Match.status.in_(_FINISHED),
        )
        .order_by(Match.utc_date.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).unique().all())


def _head_to_head(db: Session, match: Match, limit: int = 10) -> HeadToHeadOut:
    a, b = match.home_team_id, match.away_team_id
    stmt = (
        match_query()
        .where(
            Match.id != match.id,
            Match.status.in_(_FINISHED),
            or_(
                and_(Match.home_team_id == a, Match.away_team_id == b),
                and_(Match.home_team_id == b, Match.away_team_id == a),
            ),
        )
        .order_by(Match.utc_date.desc())
        .limit(limit)
    )
    past = list(db.scalars(stmt).unique().all())

    h2h = HeadToHeadOut(matches=[MatchOut.model_validate(m) for m in past])
    for m in past:
        if m.home_score is None or m.away_score is None:
            continue
        # score from the current match's home team ("a") perspective
        a_for = m.home_score if m.home_team_id == a else m.away_score
        a_against = m.away_score if m.home_team_id == a else m.home_score
        if a_for > a_against:
            h2h.home_wins += 1
        elif a_for < a_against:
            h2h.away_wins += 1
        else:
            h2h.draws += 1
    return h2h


@router.get("/{match_id}", response_model=MatchDetailOut)
def get_match(match_id: int, db: Session = Depends(get_db)):
    stmt = (
        match_query()
        .where(Match.id == match_id)
        .options(
            selectinload(Match.goals),
            selectinload(Match.bookings),
            selectinload(Match.substitutions),
            selectinload(Match.team_stats),
            selectinload(Match.player_ratings),
        )
    )
    match = db.scalars(stmt).unique().one_or_none()
    if match is None:
        raise HTTPException(404, f"match {match_id} not found")

    detail = MatchDetailOut.model_validate(match)
    detail.merged_team_stats = [
        MergedTeamStatOut(**m) for m in merge_team_stats(match.team_stats)
    ]
    # best performers first: API-Football rating, else FPL bps
    detail.player_ratings.sort(
        key=lambda r: (r.rating or 0, r.bps or 0, r.goals or 0), reverse=True
    )
    detail.head_to_head = _head_to_head(db, match)
    detail.home_form = [
        MatchOut.model_validate(m) for m in _team_form(db, match.home_team_id, match.utc_date)
    ]
    detail.away_form = [
        MatchOut.model_validate(m) for m in _team_form(db, match.away_team_id, match.utc_date)
    ]
    return detail
