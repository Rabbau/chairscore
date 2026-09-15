"""Shared query helpers for the API routers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import joinedload

from app.models import Match


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def match_query() -> Select:
    """Base SELECT for matches with competition + both teams eager-loaded."""
    return select(Match).options(
        joinedload(Match.competition),
        joinedload(Match.home_team),
        joinedload(Match.away_team),
    )
