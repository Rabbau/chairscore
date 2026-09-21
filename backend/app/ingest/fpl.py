"""FPL enrichment — per-player match data (goals, assists, cards, saves, bonus,
BPS, and optionally xG/xA) for finished **Premier League** matches of the current season.

Mirrors ``ingest.depth`` but for the FPL provider: resolve the FPL fixture for a
football-data match (team name + date), fetch the depth bundle, write
``MatchTeamStat`` / ``MatchPlayerRating`` rows tagged ``source="fpl"``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.ingest.sync import current_season_of
from app.models import Competition, Match, MatchExternalRef, MatchPlayerRating, MatchTeamStat
from app.providers import get_fpl_provider
from app.providers.api_football import _name_overlap
from app.providers.fpl import FplProvider

log = logging.getLogger("chairscore.ingest.fpl")

_SOURCE = "fpl"
_FINISHED = ("FINISHED", "AWARDED")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _team_id_map(match: Match, fixture: dict, fpl: FplProvider) -> dict[int, int]:
    """FPL team id -> our local team id, orientation checked by name overlap."""
    h, a = fixture["team_h"], fixture["team_a"]
    straight = _name_overlap(match.home_team.name, fpl.team_name(h)) + _name_overlap(
        match.away_team.name, fpl.team_name(a)
    )
    swapped = _name_overlap(match.home_team.name, fpl.team_name(a)) + _name_overlap(
        match.away_team.name, fpl.team_name(h)
    )
    if swapped > straight:
        return {h: match.away_team_id, a: match.home_team_id}
    return {h: match.home_team_id, a: match.away_team_id}


def _resolve_fixture(db: Session, fpl: FplProvider, match: Match) -> dict | None:
    ref = db.scalar(
        select(MatchExternalRef).where(
            MatchExternalRef.match_id == match.id, MatchExternalRef.provider == _SOURCE
        )
    )
    fixture = fpl.find_fixture(
        match.utc_date.date(),
        match.home_team.name,
        match.away_team.name,
        event_hint=match.matchday,
        home_tla=match.home_team.tla,
        away_tla=match.away_team.tla,
    )
    if fixture is None:
        if ref is None:
            log.info(
                "no FPL fixture for match %s (%s vs %s, %s)",
                match.id, match.home_team.name, match.away_team.name, match.utc_date.date(),
            )
        return None
    if ref is None:
        db.add(MatchExternalRef(match_id=match.id, provider=_SOURCE, external_id=fixture["id"]))
        db.flush()
    return fixture


def _write(db: Session, match: Match, fixture: dict, fpl: FplProvider) -> tuple[int, int]:
    tmap = _team_id_map(match, fixture, fpl)
    team_stats, ratings = fpl.match_depth(
        fixture, want_player_xg=settings.fpl_fetch_player_xg
    )

    db.execute(
        delete(MatchTeamStat).where(
            MatchTeamStat.match_id == match.id, MatchTeamStat.source == _SOURCE
        )
    )
    db.execute(
        delete(MatchPlayerRating).where(
            MatchPlayerRating.match_id == match.id, MatchPlayerRating.source == _SOURCE
        )
    )
    for ts in team_stats:
        db.add(MatchTeamStat(
            match_id=match.id, team_id=tmap.get(ts.team_provider_id), source=_SOURCE,
            xg=ts.xg, saves=ts.saves, yellow_cards=ts.yellow_cards, red_cards=ts.red_cards,
        ))
    for r in ratings:
        db.add(MatchPlayerRating(
            match_id=match.id, team_id=tmap.get(r.team_provider_id), source=_SOURCE,
            player_name=r.player_name, player_provider_id=r.player_provider_id,
            position=r.position, minutes=r.minutes, is_starter=r.is_starter,
            goals=r.goals, assists=r.assists, yellow=r.yellow, red=r.red, saves=r.saves,
            bonus=r.bonus, bps=r.bps, xg=r.xg, xa=r.xa,
        ))
    match.fpl_synced_at = _now()
    db.commit()
    return len(team_stats), len(ratings)


def enrich_fpl_matches() -> int:
    fpl = get_fpl_provider()
    if fpl is None:
        log.info("FPL provider disabled (FPL_ENABLED=false) — skipping")
        return 0

    code = settings.fpl_competition_code
    enriched = 0

    with SessionLocal() as db:
        comp = db.scalar(select(Competition).where(Competition.code == code))
        if comp is None:
            log.warning("FPL: competition %s not in DB", code)
            return 0

        candidates = db.scalars(
            select(Match)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .where(
                Match.competition_id == comp.id,
                Match.status.in_(_FINISHED),
                Match.season == current_season_of(db, comp),
                Match.fpl_synced_at.is_(None),
            )
            .order_by(Match.utc_date.desc())
            .limit(settings.fpl_max_matches_per_run)
        ).all()

        if not candidates:
            log.info("FPL: nothing to enrich")
            return 0

        for match in candidates:
            try:
                fixture = _resolve_fixture(db, fpl, match)
                if fixture is None:
                    continue
                n_stats, n_ratings = _write(db, match, fixture, fpl)
                enriched += 1
                log.info(
                    "FPL: %s %s-%s %s  (%d team stats, %d players)",
                    match.home_team.display_name, match.home_score, match.away_score,
                    match.away_team.display_name, n_stats, n_ratings,
                )
            except Exception:  # noqa: BLE001 - one bad match must not abort the run
                db.rollback()
                log.exception("FPL enrich failed for match %s", match.id)

    fpl.close()
    log.info("FPL enrichment done: %d match(es)", enriched)
    return enriched
