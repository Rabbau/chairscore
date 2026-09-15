"""Football-Data.co.uk enrichment — team-level match statistics (shots,
corners, cards, xG where the source has it) for recently finished matches
across every tracked competition this source covers (all 5 by default, not
just one league like the FPL provider).

One CSV per competition-season, cached for the whole run — cheap enough that
there's no need to cache a "found it" external id between runs the way the
other depth sources do; ``matches.fdcouk_synced_at`` alone gates re-work, and
leaving it unset when nothing was found lets a later run (once the source
catches up) pick the match back up.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import Competition, Match, MatchTeamStat
from app.providers import get_fdcouk_provider
from app.providers.football_data_co_uk import FootballDataCoUkProvider

log = logging.getLogger("chairscore.ingest.football_data_co_uk")

_SOURCE = "football-data.co.uk"
_FINISHED = ("FINISHED", "AWARDED")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _write(db: Session, match: Match, row: dict, provider: FootballDataCoUkProvider) -> None:
    home_stats, away_stats = provider.team_stats(row)

    db.execute(
        delete(MatchTeamStat).where(
            MatchTeamStat.match_id == match.id, MatchTeamStat.source == _SOURCE
        )
    )
    for team_id, stats in ((match.home_team_id, home_stats), (match.away_team_id, away_stats)):
        db.add(MatchTeamStat(
            match_id=match.id, team_id=team_id, source=_SOURCE,
            shots=stats.shots, shots_on_target=stats.shots_on_target,
            corners=stats.corners, fouls=stats.fouls,
            yellow_cards=stats.yellow_cards, red_cards=stats.red_cards,
            xg=stats.xg,
        ))
    match.fdcouk_synced_at = _now()
    db.commit()


def enrich_fdcouk_matches() -> int:
    provider = get_fdcouk_provider()
    if provider is None:
        log.info("football-data.co.uk provider disabled (FDCOUK_ENABLED=false) — skipping")
        return 0

    since = _now() - timedelta(days=settings.fdcouk_window_days)
    budget = settings.fdcouk_max_matches_per_run
    enriched = 0

    with SessionLocal() as db:
        for code in settings.tracked_competition_codes:
            if budget <= 0:
                break
            comp = db.scalar(select(Competition).where(Competition.code == code))
            if comp is None:
                continue
            candidates = db.scalars(
                select(Match)
                .options(selectinload(Match.home_team), selectinload(Match.away_team))
                .where(
                    Match.competition_id == comp.id,
                    Match.status.in_(_FINISHED),
                    Match.utc_date >= since,
                    Match.fdcouk_synced_at.is_(None),
                )
                .order_by(Match.utc_date.desc())
                .limit(budget)
            ).all()

            for match in candidates:
                try:
                    row = provider.find_row(
                        code, match.season, match.utc_date.date(),
                        match.home_team.name, match.away_team.name,
                    )
                    if row is None:
                        continue
                    _write(db, match, row, provider)
                    enriched += 1
                    log.info(
                        "[%s] %s %s-%s %s",
                        code, match.home_team.display_name, match.home_score,
                        match.away_score, match.away_team.display_name,
                    )
                except Exception:  # noqa: BLE001 - one bad match must not abort the run
                    db.rollback()
                    log.exception("football-data.co.uk enrich failed for match %s", match.id)
                budget -= 1
                if budget <= 0:
                    break

    provider.close()
    log.info("football-data.co.uk enrichment done: %d match(es)", enriched)
    return enriched
