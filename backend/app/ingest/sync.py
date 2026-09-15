"""Upsert normalized provider data into the database.

Design notes
------------
* Every write is idempotent and keyed on the provider id.
* Child collections that the provider always sends in full (goals, bookings,
  substitutions, standing rows, scorer rows) are replaced wholesale on each
  sync — simplest way to stay correct when events get edited upstream.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Booking,
    Competition,
    CompetitionTeam,
    Goal,
    Match,
    Player,
    Scorer,
    Standing,
    Substitution,
    Team,
)
from app.providers import get_provider
from app.providers.base import (
    BaseProvider,
    NCompetition,
    NMatch,
    NScorer,
    NStandings,
    NTeam,
    ProviderError,
)

log = logging.getLogger("chairscore.ingest")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


# --------------------------------------------------------------------------- #
# upserts
# --------------------------------------------------------------------------- #
def upsert_team(db: Session, n: NTeam) -> Team:
    team = db.scalar(select(Team).where(Team.provider_id == n.provider_id))
    if team is None:
        team = Team(provider_id=n.provider_id, name=n.name)
        db.add(team)

    team.name = n.name or team.name
    for attr in ("short_name", "tla", "crest_url", "founded", "club_colors", "venue",
                 "website", "coach_name", "area_name"):
        val = getattr(n, attr)
        if val is not None:
            setattr(team, attr, val)
    team.last_synced_at = _now()
    db.flush()

    if n.squad:
        _replace_squad(db, team, n)
    return team


def _replace_squad(db: Session, team: Team, n: NTeam) -> None:
    existing = {p.provider_id: p for p in team.players if p.provider_id is not None}
    seen: set[int] = set()
    for np in n.squad:
        seen.add(np.provider_id) if np.provider_id is not None else None
        player = existing.get(np.provider_id)
        if player is None:
            player = Player(name=np.name, provider_id=np.provider_id, team_id=team.id)
            db.add(player)
        player.name = np.name
        player.position = np.position
        player.date_of_birth = np.date_of_birth
        player.nationality = np.nationality
        player.shirt_number = np.shirt_number
        player.team_id = team.id
        player.last_synced_at = _now()
    # drop players who left the squad
    for pid, player in existing.items():
        if pid not in seen:
            db.delete(player)
    db.flush()


def upsert_competition(db: Session, n: NCompetition) -> Competition:
    comp = db.scalar(select(Competition).where(Competition.provider_id == n.provider_id))
    if comp is None:
        comp = Competition(provider_id=n.provider_id, code=n.code, name=n.name)
        db.add(comp)
    comp.code = n.code or comp.code
    comp.name = n.name or comp.name
    for attr in ("type", "emblem_url", "area_name", "area_code", "area_flag",
                 "current_season", "current_season_start", "current_season_end",
                 "current_matchday"):
        val = getattr(n, attr)
        if val is not None:
            setattr(comp, attr, val)
    comp.last_synced_at = _now()
    db.flush()
    return comp


def _get_or_create_competition(db: Session, code: str, provider_id: int | None) -> Competition:
    stmt = select(Competition)
    if provider_id is not None:
        stmt = stmt.where(Competition.provider_id == provider_id)
    else:
        stmt = stmt.where(Competition.code == code)
    comp = db.scalar(stmt)
    if comp is None:
        comp = Competition(provider_id=provider_id or 0, code=code or "UNK", name=code or "Unknown")
        db.add(comp)
        db.flush()
    return comp


def upsert_match(db: Session, n: NMatch) -> Match:
    comp = _get_or_create_competition(db, n.competition_code, n.competition_provider_id)
    home = upsert_team(db, n.home_team)
    away = upsert_team(db, n.away_team)

    match = db.scalar(select(Match).where(Match.provider_id == n.provider_id))
    if match is None:
        match = Match(provider_id=n.provider_id, competition_id=comp.id, season=n.season,
                      utc_date=_naive_utc(n.utc_date), home_team_id=home.id, away_team_id=away.id)
        db.add(match)

    match.competition_id = comp.id
    match.season = n.season
    match.matchday = n.matchday
    match.stage = n.stage
    match.group = n.group
    match.utc_date = _naive_utc(n.utc_date)
    match.status = n.status
    match.home_team_id = home.id
    match.away_team_id = away.id
    match.home_score = n.home_score
    match.away_score = n.away_score
    match.home_score_ht = n.home_score_ht
    match.away_score_ht = n.away_score_ht
    match.winner = n.winner
    match.duration = n.duration
    match.venue = n.venue
    if n.referees:
        match.referees = n.referees
    match.provider_updated_at = _naive_utc(n.provider_updated_at)
    match.last_synced_at = _now()
    db.flush()

    _replace_match_events(db, match, n, {t.provider_id: t.id for t in (home, away)})
    return match


def _replace_match_events(db: Session, match: Match, n: NMatch, team_ids: dict[int, int]) -> None:
    if not (n.goals or n.bookings or n.substitutions):
        return
    db.execute(delete(Goal).where(Goal.match_id == match.id))
    db.execute(delete(Booking).where(Booking.match_id == match.id))
    db.execute(delete(Substitution).where(Substitution.match_id == match.id))
    for g in n.goals:
        db.add(Goal(
            match_id=match.id, team_id=team_ids.get(g.team_provider_id),
            minute=g.minute, injury_time=g.injury_time, type=g.type,
            scorer_name=g.scorer_name, scorer_provider_id=g.scorer_provider_id,
            assist_name=g.assist_name, home_score=g.home_score, away_score=g.away_score,
        ))
    for b in n.bookings:
        db.add(Booking(
            match_id=match.id, team_id=team_ids.get(b.team_provider_id),
            minute=b.minute, player_name=b.player_name, card=b.card,
        ))
    for s in n.substitutions:
        db.add(Substitution(
            match_id=match.id, team_id=team_ids.get(s.team_provider_id),
            minute=s.minute, player_in_name=s.player_in_name, player_out_name=s.player_out_name,
        ))
    db.flush()


def replace_standings(db: Session, n: NStandings) -> None:
    comp = upsert_competition(db, n.competition)
    season = n.season or comp.current_season or str(_now().year)
    db.execute(
        delete(Standing).where(Standing.competition_id == comp.id, Standing.season == season)
    )
    for row in n.rows:
        team = upsert_team(db, row.team)
        db.add(Standing(
            competition_id=comp.id, season=season, stage=row.stage, type=row.type,
            group_name=row.group, team_id=team.id, position=row.position, played=row.played,
            won=row.won, draw=row.draw, lost=row.lost, points=row.points,
            goals_for=row.goals_for, goals_against=row.goals_against,
            goal_difference=row.goal_difference, form=row.form, updated_at=_now(),
        ))
    db.flush()


def replace_scorers(db: Session, comp: Competition, season: str, scorers: list[NScorer]) -> None:
    db.execute(
        delete(Scorer).where(Scorer.competition_id == comp.id, Scorer.season == season)
    )
    for s in scorers:
        team = upsert_team(db, s.team) if s.team else None
        db.add(Scorer(
            competition_id=comp.id, season=season, player_provider_id=s.player_provider_id,
            player_name=s.player_name, position=s.position, nationality=s.nationality,
            date_of_birth=s.date_of_birth, team_id=team.id if team else None,
            played_matches=s.played_matches, goals=s.goals, assists=s.assists,
            penalties=s.penalties, updated_at=_now(),
        ))
    db.flush()


def link_competition_team(db: Session, competition_id: int, team_id: int, season: str) -> None:
    exists = db.scalar(
        select(CompetitionTeam).where(
            CompetitionTeam.competition_id == competition_id,
            CompetitionTeam.team_id == team_id,
            CompetitionTeam.season == season,
        )
    )
    if not exists:
        db.add(CompetitionTeam(competition_id=competition_id, team_id=team_id, season=season))


# --------------------------------------------------------------------------- #
# sync tasks
# --------------------------------------------------------------------------- #
def sync_competitions(db: Session, provider: BaseProvider) -> int:
    try:
        comps = provider.list_competitions()
    except ProviderError as exc:
        log.warning("competitions list skipped: %s", exc)
        return 0
    for n in comps:
        upsert_competition(db, n)
    db.commit()
    log.info("synced %d competitions", len(comps))
    return len(comps)


def sync_competition_teams(db: Session, provider: BaseProvider, code: str) -> int:
    try:
        comp_n, teams = provider.get_teams(code)
    except ProviderError as exc:
        log.warning("[%s] teams skipped: %s", code, exc)
        return 0
    comp = upsert_competition(db, comp_n)
    season = comp.current_season or str(_now().year)
    for tn in teams:
        team = upsert_team(db, tn)
        link_competition_team(db, comp.id, team.id, season)
    db.commit()
    log.info("[%s] synced %d teams", code, len(teams))
    return len(teams)


def sync_standings(
    db: Session, provider: BaseProvider, code: str, season: str | None = None
) -> None:
    try:
        n = provider.get_standings(code, season=season)
    except ProviderError as exc:
        log.warning("[%s] standings skipped: %s", code, exc)
        return
    replace_standings(db, n)
    db.commit()
    log.info("[%s] synced %d standing rows%s", code, len(n.rows),
             f" (season {season})" if season else "")


def sync_scorers(
    db: Session, provider: BaseProvider, code: str, season: str | None = None, limit: int = 20
) -> None:
    try:
        comp_n, scorers = provider.get_scorers(code, season=season, limit=limit)
    except ProviderError as exc:
        log.warning("[%s] scorers skipped: %s", code, exc)
        return
    comp = upsert_competition(db, comp_n)
    resolved = season or comp.current_season or str(_now().year)
    replace_scorers(db, comp, resolved, scorers)
    db.commit()
    log.info("[%s] synced %d scorers%s", code, len(scorers),
             f" (season {season})" if season else "")


def sync_matches(
    db: Session,
    provider: BaseProvider,
    code: str,
    *,
    season: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    matchday: int | None = None,
) -> int:
    try:
        matches = provider.get_matches(
            code, season=season, date_from=date_from, date_to=date_to, matchday=matchday
        )
    except ProviderError as exc:
        log.warning("[%s] matches skipped: %s", code, exc)
        return 0
    for mn in matches:
        upsert_match(db, mn)
    db.commit()
    suffix = f" (season {season})" if season else ""
    log.info("[%s] synced %d matches%s", code, len(matches), suffix)
    return len(matches)


# --------------------------------------------------------------------------- #
# orchestration (used by CLI + scheduler)
# --------------------------------------------------------------------------- #
def _codes() -> list[str]:
    return settings.tracked_competition_codes


def run_full_sync(codes: list[str] | None = None) -> None:
    codes = codes or _codes()
    provider = get_provider()
    with SessionLocal() as db:
        sync_competitions(db, provider)
        for code in codes:
            try:
                sync_competition_teams(db, provider, code)
                sync_standings(db, provider, code)
                sync_scorers(db, provider, code)
                sync_matches(db, provider, code)
            except Exception:  # noqa: BLE001 - one bad competition must not abort the rest
                log.exception("[%s] sync failed", code)
                db.rollback()
    log.info("full sync complete for %s", ", ".join(codes))


def sync_reference_data() -> None:
    provider = get_provider()
    with SessionLocal() as db:
        sync_competitions(db, provider)
        for code in _codes():
            sync_competition_teams(db, provider, code)


def sync_standings_and_scorers() -> None:
    provider = get_provider()
    with SessionLocal() as db:
        for code in _codes():
            sync_standings(db, provider, code)
            sync_scorers(db, provider, code)


def sync_history(seasons: list[str], codes: list[str] | None = None) -> None:
    """Backfill past seasons — results, final tables, top scorers — for the
    season switcher and head-to-head."""
    codes = codes or _codes()
    provider = get_provider()
    with SessionLocal() as db:
        for season in seasons:
            for code in codes:
                sync_matches(db, provider, code, season=season)
                sync_standings(db, provider, code, season=season)
                sync_scorers(db, provider, code, season=season)
    log.info("history backfill complete: seasons %s", ", ".join(seasons))


def sync_recent_matches() -> None:
    provider = get_provider()
    today = date.today()
    date_from = today - timedelta(days=settings.match_window_past_days)
    date_to = today + timedelta(days=settings.match_window_future_days)
    with SessionLocal() as db:
        for code in _codes():
            sync_matches(db, provider, code, date_from=date_from, date_to=date_to)
