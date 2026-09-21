from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Competition, Team
from app.schemas.search import SearchOut

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchOut)
def search(
    q: str = Query(min_length=2, max_length=60),
    limit: int = Query(8, le=25),
    db: Session = Depends(get_db),
):
    like = f"%{q.strip()}%"
    teams = db.scalars(
        select(Team)
        .where(or_(Team.name.ilike(like), Team.short_name.ilike(like), Team.tla.ilike(q.strip())))
        .order_by(func.length(Team.name), Team.name)
        .limit(limit)
    ).all()
    comps = db.scalars(
        select(Competition)
        .where(
            or_(Competition.name.ilike(like), Competition.code.ilike(q.strip())),
            Competition.code.in_(settings.served_competition_codes),
        )
        .order_by(Competition.name)
        .limit(5)
    ).all()
    return SearchOut(teams=list(teams), competitions=list(comps))
