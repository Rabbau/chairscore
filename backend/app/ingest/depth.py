"""Depth enrichment — pull match events, per-team statistics and player ratings
from API-Football for recently finished matches in ``depth_competitions``.

Runs entirely off the breadth data already in the DB: for each candidate match
it resolves the API-Football fixture id (fuzzy team-name + date match, cached in
``match_external_refs``), then fetches and stores the depth bundle. Bounded per
run by ``depth_max_matches_per_run`` to respect the free-tier daily budget.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Booking,
    Competition,
    Goal,
    Match,
    MatchExternalRef,
    MatchPlayerRating,
    MatchTeamStat,
    Substitution,
)
from app.providers import get_depth_provider
from app.providers.api_football import ApiFootballProvider, _name_overlap
from app.providers.base import NMatch, ProviderError

log = logging.getLogger("chairscore.ingest.depth")

_PROVIDER = "api-football"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _team_id_map(match: Match, nd: NMatch) -> dict[int | None, int | None]:
    """API-Football team id -> our local team id, orientation-checked by name."""
    straight = _name_overlap(match.home_team.name, nd.home_team.name) + _name_overlap(
        match.away_team.name, nd.away_team.name
    )
    swapped = _name_overlap(match.home_team.name, nd.away_team.name) + _name_overlap(
        match.away_team.name, nd.home_team.name
    )
    if swapped > straight:
        return {nd.home_team.provider_id: match.away_team_id,
                nd.away_team.provider_id: match.home_team_id}
    return {nd.home_team.provider_id: match.home_team_id,
            nd.away_team.provider_id: match.away_team_id}


def _replace_events(db: Session, match: Match, nd: NMatch, tmap: dict) -> None:
    db.execute(delete(Goal).where(Goal.match_id == match.id))
    db.execute(delete(Booking).where(Booking.match_id == match.id))
    db.execute(delete(Substitution).where(Substitution.match_id == match.id))
    for g in nd.goals:
        db.add(Goal(
            match_id=match.id, team_id=tmap.get(g.team_provider_id), minute=g.minute,
            injury_time=g.injury_time, type=g.type, scorer_name=g.scorer_name,
            assist_name=g.assist_name,
        ))
    for b in nd.bookings:
        db.add(Booking(
            match_id=match.id, team_id=tmap.get(b.team_provider_id), minute=b.minute,
            player_name=b.player_name, card=b.card,
        ))
    for s in nd.substitutions:
        db.add(Substitution(
            match_id=match.id, team_id=tmap.get(s.team_provider_id), minute=s.minute,
            player_in_name=s.player_in_name, player_out_name=s.player_out_name,
        ))


def _replace_team_stats(db: Session, match: Match, nd: NMatch, tmap: dict) -> None:
    db.execute(delete(MatchTeamStat).where(MatchTeamStat.match_id == match.id))
    for s in nd.team_stats:
        db.add(MatchTeamStat(
            match_id=match.id, team_id=tmap.get(s.team_provider_id), source=_PROVIDER,
            possession=s.possession, shots=s.shots, shots_on_target=s.shots_on_target,
            corners=s.corners, fouls=s.fouls, offsides=s.offsides,
            yellow_cards=s.yellow_cards, red_cards=s.red_cards, passes=s.passes,
            passes_accuracy=s.passes_accuracy, saves=s.saves, xg=s.xg,
        ))


def _replace_player_ratings(db: Session, match: Match, nd: NMatch, tmap: dict) -> None:
    db.execute(delete(MatchPlayerRating).where(MatchPlayerRating.match_id == match.id))
    seen: set[tuple] = set()
    for p in nd.player_ratings:
        key = (p.player_name, tmap.get(p.team_provider_id))
        if key in seen:
            continue
        seen.add(key)
        db.add(MatchPlayerRating(
            match_id=match.id, team_id=tmap.get(p.team_provider_id), player_name=p.player_name,
            player_provider_id=p.player_provider_id, rating=p.rating, minutes=p.minutes,
            position=p.position, number=p.number, is_starter=p.is_starter, captain=p.captain,
            goals=p.goals, assists=p.assists, yellow=p.yellow, red=p.red,
        ))


def _resolve_fixture_id(
    db: Session, depth: ApiFootballProvider, match: Match, code: str
) -> int | None:
    ref = db.scalar(
        select(MatchExternalRef).where(
            MatchExternalRef.match_id == match.id, MatchExternalRef.provider == _PROVIDER
        )
    )
    if ref:
        return ref.external_id

    fixture_id = depth.find_fixture_id(
        code, match.season, match.utc_date.date(), match.home_team.name, match.away_team.name
    )
    if fixture_id is None:
        log.info(
            "no api-football fixture for match %s (%s vs %s on %s)",
            match.id, match.home_team.name, match.away_team.name, match.utc_date.date(),
        )
        return None
    db.add(MatchExternalRef(match_id=match.id, provider=_PROVIDER, external_id=fixture_id))
    db.flush()
    return fixture_id


def _enrich_one(db: Session, depth: ApiFootballProvider, match: Match, code: str) -> bool:
    fixture_id = _resolve_fixture_id(db, depth, match, code)
    if fixture_id is None:
        return False

    nd = depth.get_match_depth(fixture_id)
    tmap = _team_id_map(match, nd)
    _replace_events(db, match, nd, tmap)
    _replace_team_stats(db, match, nd, tmap)
    _replace_player_ratings(db, match, nd, tmap)
    match.depth_synced_at = _now()
    db.commit()
    log.info(
        "depth: %s %s-%s %s  (%d goals, %d stat rows, %d ratings)",
        match.home_team.display_name, match.home_score, match.away_score,
        match.away_team.display_name, len(nd.goals), len(nd.team_stats),
        len(nd.player_ratings),
    )
    return True


def enrich_depth_matches() -> int:
    depth = get_depth_provider()
    if depth is None:
        log.info("depth provider not configured (set API_FOOTBALL_KEY) — skipping")
        return 0

    budget = settings.depth_max_matches_per_run
    since = _now() - timedelta(days=settings.depth_window_days)
    enriched = 0

    with SessionLocal() as db:
        for code in settings.depth_competition_codes:
            if budget <= 0:
                break
            comp = db.scalar(select(Competition).where(Competition.code == code))
            if comp is None:
                log.warning("depth: competition %s not in DB", code)
                continue
            candidates = db.scalars(
                select(Match)
                .options(selectinload(Match.home_team), selectinload(Match.away_team))
                .where(
                    Match.competition_id == comp.id,
                    Match.status.in_(("FINISHED", "AWARDED")),
                    Match.utc_date >= since,
                    Match.depth_synced_at.is_(None),
                )
                .order_by(Match.utc_date.desc())
                .limit(budget)
            ).all()

            for match in candidates:
                try:
                    if _enrich_one(db, depth, match, code):
                        enriched += 1
                except ProviderError as exc:
                    db.rollback()
                    log.warning("depth enrich failed for match %s: %s", match.id, exc)
                    msg = str(exc).lower()
                    if any(k in msg for k in ("budget", "429", "quota", "do not have access")):
                        log.warning("depth: stopping — API limit or plan restriction hit")
                        return enriched
                budget -= 1
                if budget <= 0:
                    break

    log.info("depth enrichment done: %d match(es)", enriched)
    return enriched
