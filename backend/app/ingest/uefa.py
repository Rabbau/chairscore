"""UEFA ingest — Champions League + Europa League.

Breadth (fixtures, league-phase table, top scorers) and depth (lineups, the event
feed, and the team stats counted from it) both come from ``providers.uefa``.

The one real problem here is identity: Arsenal already exists as a football-data.org
team from the Premier League, and UEFA calls it something slightly different under
a different id. ``TeamMatcher`` recognises clubs we already know (by name + UEFA's
three-letter code) and records the link in ``team_external_refs``, so a club is one
``Team`` row — one page, one head-to-head history — across league and Europe.
Clubs with no league team (Sporting, Galatasaray ...) get a standalone row.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.ingest.sync import (
    link_competition_team,
    replace_scorers,
    replace_standings,
    upsert_competition,
    upsert_match,
    upsert_team,
)
from app.models import (
    Booking,
    Competition,
    Goal,
    Match,
    MatchPlayerRating,
    MatchTeamStat,
    Standing,
    Substitution,
    Team,
    TeamExternalRef,
)
from app.providers import get_uefa_provider
from app.providers.base import NCompetition, NTeam, ProviderError
from app.providers.uefa import UEFA_ID_OFFSET, UefaDepth, UefaProvider, current_season, team_pid

log = logging.getLogger("chairscore.ingest.uefa")

_PROVIDER = "uefa"
_SOURCE = "uefa"
_FINISHED = ("FINISHED", "AWARDED")
_TOP5_COUNTRIES = {"England", "Spain", "Germany", "Italy", "France"}

# --------------------------------------------------------------------------- #
# matching UEFA clubs onto league teams
# --------------------------------------------------------------------------- #
# Legal-form / initials noise in club names ("FC", "C.F.", "TSG 1899", "Como 1907").
_STOP = {
    "fc", "cf", "afc", "ac", "sc", "club", "de", "the", "calcio", "cd", "ud", "rc", "rcd",
    "sv", "vfb", "vfl", "tsg", "fsv", "ssc", "as", "us", "ss",
}
_MIN_SCORE = 0.9
_MIN_MARGIN = 0.15
_TLA_BONUS = 0.5


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _tokens(s: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", _strip_accents(s.lower()))
    return {w for w in words if len(w) > 1 and not w.isdigit() and w not in _STOP}


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def match_score(uefa: NTeam, name: str, short_name: str | None, tla: str | None) -> float:
    """How well a UEFA club fits a league team: the best token overlap between any
    of UEFA's spellings and either of ours, plus a bonus when the three-letter
    codes agree. The bonus is what separates PSG from Paris FC — UEFA lists PSG
    as just "Paris" — without needing a hand-kept alias table."""
    theirs = uefa.aliases or [uefa.name]
    best = max(
        (_jaccard(u, ours) for u in theirs for ours in (name, short_name) if ours),
        default=0.0,
    )
    if tla and uefa.tla and tla.upper() == uefa.tla.upper():
        best += _TLA_BONUS
    return best


class TeamMatcher:
    """A ``TeamResolver`` (see ``ingest.sync``) for UEFA teams."""

    def __init__(self) -> None:
        self._loaded = False
        self._by_uefa: dict[int, int] = {}  # uefa team id -> Team.id
        self._claimed: set[int] = set()  # Team.ids already tied to a UEFA id
        self._pool: list[tuple[int, str, str | None, str | None]] = []
        self.created: list[str] = []

    def _load(self, db: Session) -> None:
        for ref in db.scalars(select(TeamExternalRef).where(TeamExternalRef.provider == _PROVIDER)):
            self._by_uefa[ref.external_id] = ref.team_id
            self._claimed.add(ref.team_id)
        rows = db.execute(
            select(Team.id, Team.name, Team.short_name, Team.tla).where(
                Team.provider_id < UEFA_ID_OFFSET
            )
        )
        self._pool = [tuple(r) for r in rows]
        self._loaded = True

    def _best_match(self, n: NTeam) -> int | None:
        ranked = sorted(
            ((match_score(n, name, short, tla), tid) for tid, name, short, tla in self._pool
             if tid not in self._claimed),
            reverse=True,
        )
        if not ranked or ranked[0][0] < _MIN_SCORE:
            return None
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < _MIN_MARGIN:
            log.warning("UEFA team %r is ambiguous between league teams — not linking", n.name)
            return None
        return ranked[0][1]

    def __call__(self, db: Session, n: NTeam) -> Team:
        if not self._loaded:
            self._load(db)
        uefa_id = n.provider_id - UEFA_ID_OFFSET

        if (team_id := self._by_uefa.get(uefa_id)) is not None:
            return db.get(Team, team_id)  # type: ignore[return-value]

        linked = self._best_match(n)
        if linked is not None:
            team = db.get(Team, linked)
        else:
            team = upsert_team(db, n)
            self.created.append(n.name)
            if n.area_name in _TOP5_COUNTRIES:
                log.warning(
                    "UEFA club %r (%s) has no matching league team — created standalone",
                    n.name, n.area_name,
                )
        db.add(TeamExternalRef(team_id=team.id, provider=_PROVIDER, external_id=uefa_id))
        db.flush()
        self._by_uefa[uefa_id] = team.id
        self._claimed.add(team.id)
        return team  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# breadth
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def ensure_competition(db: Session, n: NCompetition) -> Competition:
    comp = db.scalar(select(Competition).where(Competition.code == n.code))
    if comp is None:
        return upsert_competition(db, n)
    comp.current_season = n.current_season or comp.current_season
    comp.emblem_url = comp.emblem_url or n.emblem_url
    comp.area_name = comp.area_name or n.area_name
    return comp


def sync_uefa_matches(
    db: Session,
    provider: UefaProvider,
    matcher: TeamMatcher,
    code: str,
    *,
    season: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> int:
    try:
        matches = provider.get_matches(code, season=season, date_from=date_from, date_to=date_to)
    except ProviderError as exc:
        log.warning("[%s] UEFA matches skipped: %s", code, exc)
        return 0
    comp = db.scalar(select(Competition).where(Competition.code == code))
    linked: set[tuple[int, str]] = set()
    for n in matches:
        match = upsert_match(db, n, matcher)
        for team_id in (match.home_team_id, match.away_team_id):
            if (team_id, n.season) not in linked:
                link_competition_team(db, comp.id, team_id, n.season)
                linked.add((team_id, n.season))
    _update_current_matchday(db, comp, season or comp.current_season)
    db.commit()
    suffix = f" (season {season})" if season else ""
    log.info("[%s] synced %d UEFA matches%s", code, len(matches), suffix)
    return len(matches)


def _update_current_matchday(db: Session, comp: Competition, season: str | None) -> None:
    if not season or season != comp.current_season:
        return
    comp.current_matchday = db.scalar(
        select(func.max(Match.matchday)).where(
            Match.competition_id == comp.id,
            Match.season == season,
            Match.status.in_(_FINISHED),
            Match.matchday.is_not(None),
        )
    )


def sync_uefa_standings(
    db: Session, provider: UefaProvider, matcher: TeamMatcher, code: str, season: str | None = None
) -> None:
    try:
        n = provider.get_standings(code, season=season)
    except ProviderError as exc:
        log.warning("[%s] UEFA standings skipped: %s", code, exc)
        return
    replace_standings(db, n, matcher)
    comp = db.scalar(select(Competition).where(Competition.code == code))
    in_table = select(Standing.team_id).where(
        Standing.competition_id == comp.id, Standing.season == n.season
    )
    for team_id in db.scalars(in_table):
        link_competition_team(db, comp.id, team_id, n.season)
    db.commit()
    suffix = f" (season {season})" if season else ""
    log.info("[%s] synced %d UEFA standing rows%s", code, len(n.rows), suffix)


def sync_uefa_scorers(
    db: Session,
    provider: UefaProvider,
    matcher: TeamMatcher,
    code: str,
    season: str | None = None,
    limit: int = 20,
) -> None:
    try:
        comp_n, scorers = provider.get_scorers(code, season=season, limit=limit)
    except ProviderError as exc:
        log.warning("[%s] UEFA scorers skipped: %s", code, exc)
        return
    comp = ensure_competition(db, comp_n)
    replace_scorers(db, comp, season or comp.current_season or current_season(), scorers, matcher)
    db.commit()
    suffix = f" (season {season})" if season else ""
    log.info("[%s] synced %d UEFA scorers%s", code, len(scorers), suffix)


def _prepare(db: Session, provider: UefaProvider) -> TeamMatcher:
    for n in provider.list_competitions():
        ensure_competition(db, n)
    db.commit()
    return TeamMatcher()


def sync_uefa_full(season: str | None = None) -> None:
    """Whole season for every UEFA competition: matches, table, top scorers."""
    provider = get_uefa_provider()
    if provider is None:
        return
    with SessionLocal() as db:
        matcher = _prepare(db, provider)
        for code in provider.codes:
            try:
                sync_uefa_matches(db, provider, matcher, code, season=season)
                sync_uefa_standings(db, provider, matcher, code, season)
                sync_uefa_scorers(db, provider, matcher, code, season)
            except Exception:  # noqa: BLE001 - one competition must not abort the other
                log.exception("[%s] UEFA sync failed", code)
                db.rollback()
    provider.close()


def sync_uefa_standings_and_scorers() -> None:
    provider = get_uefa_provider()
    if provider is None:
        return
    with SessionLocal() as db:
        matcher = _prepare(db, provider)
        for code in provider.codes:
            sync_uefa_standings(db, provider, matcher, code)
            sync_uefa_scorers(db, provider, matcher, code)
    provider.close()


def sync_uefa_history(seasons: list[str]) -> None:
    for season in seasons:
        sync_uefa_full(season)


def sync_uefa_recent() -> None:
    """Just the recent-match window — or the whole season if we have none of it yet."""
    provider = get_uefa_provider()
    if provider is None:
        return
    today = date.today()
    date_from = today - timedelta(days=settings.match_window_past_days)
    date_to = today + timedelta(days=settings.match_window_future_days)
    season = current_season()
    with SessionLocal() as db:
        matcher = _prepare(db, provider)
        for code in provider.codes:
            comp = db.scalar(select(Competition).where(Competition.code == code))
            have = db.scalar(
                select(func.count(Match.id)).where(
                    Match.competition_id == comp.id, Match.season == season
                )
            )
            try:
                if have:
                    sync_uefa_matches(
                        db, provider, matcher, code, season=season,
                        date_from=date_from, date_to=date_to,
                    )
                else:
                    sync_uefa_matches(db, provider, matcher, code, season=season)
                    sync_uefa_standings(db, provider, matcher, code, season)
                    sync_uefa_scorers(db, provider, matcher, code, season)
            except Exception:  # noqa: BLE001
                log.exception("[%s] UEFA recent sync failed", code)
                db.rollback()
    provider.close()


# --------------------------------------------------------------------------- #
# depth
# --------------------------------------------------------------------------- #
def _write_depth(db: Session, match: Match, depth: UefaDepth, tmap: dict[int, int]) -> None:
    db.execute(delete(Goal).where(Goal.match_id == match.id))
    db.execute(delete(Booking).where(Booking.match_id == match.id))
    db.execute(delete(Substitution).where(Substitution.match_id == match.id))
    for g in depth.goals:
        db.add(Goal(
            match_id=match.id, team_id=tmap.get(g.team_provider_id), minute=g.minute,
            injury_time=g.injury_time, type=g.type, scorer_name=g.scorer_name,
            scorer_provider_id=g.scorer_provider_id, assist_name=g.assist_name,
            home_score=g.home_score, away_score=g.away_score,
        ))
    for b in depth.bookings:
        db.add(Booking(
            match_id=match.id, team_id=tmap.get(b.team_provider_id), minute=b.minute,
            player_name=b.player_name, card=b.card,
        ))
    for s in depth.substitutions:
        db.add(Substitution(
            match_id=match.id, team_id=tmap.get(s.team_provider_id), minute=s.minute,
            player_in_name=s.player_in_name, player_out_name=s.player_out_name,
        ))

    db.execute(
        delete(MatchTeamStat).where(
            MatchTeamStat.match_id == match.id, MatchTeamStat.source == _SOURCE
        )
    )
    for t in depth.team_stats:
        db.add(MatchTeamStat(
            match_id=match.id, team_id=tmap.get(t.team_provider_id), source=_SOURCE,
            shots=t.shots, shots_on_target=t.shots_on_target, corners=t.corners, fouls=t.fouls,
            offsides=t.offsides, yellow_cards=t.yellow_cards, red_cards=t.red_cards, saves=t.saves,
        ))

    db.execute(
        delete(MatchPlayerRating).where(
            MatchPlayerRating.match_id == match.id, MatchPlayerRating.source == _SOURCE
        )
    )
    seen: set[tuple] = set()
    for p in depth.player_ratings:
        team_id = tmap.get(p.team_provider_id)
        if (p.player_name, team_id) in seen:
            continue
        seen.add((p.player_name, team_id))
        db.add(MatchPlayerRating(
            match_id=match.id, team_id=team_id, source=_SOURCE, player_name=p.player_name,
            player_provider_id=p.player_provider_id, minutes=p.minutes, position=p.position,
            number=p.number, is_starter=p.is_starter, goals=p.goals, assists=p.assists,
            yellow=p.yellow, red=p.red, saves=p.saves,
        ))
    match.uefa_synced_at = _now()


def enrich_uefa_matches() -> int:
    """Lineups + events for finished UEFA matches of the current season that still lack them."""
    provider = get_uefa_provider()
    if provider is None:
        log.info("UEFA provider disabled (UEFA_ENABLED=false) — skipping")
        return 0

    enriched = 0
    with SessionLocal() as db:
        candidates = db.scalars(
            select(Match)
            .join(Competition, Match.competition_id == Competition.id)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .where(
                Competition.code.in_(provider.codes),
                Match.provider_id >= UEFA_ID_OFFSET,
                Match.season == Competition.current_season,
                Match.status.in_(_FINISHED),
                Match.uefa_synced_at.is_(None),
            )
            .order_by(Match.utc_date.desc())
            .limit(settings.uefa_max_matches_per_run)
        ).all()
        if not candidates:
            log.info("UEFA: nothing to enrich")
            provider.close()
            return 0

        refs = {
            r.team_id: r.external_id
            for r in db.scalars(
                select(TeamExternalRef).where(
                    TeamExternalRef.provider == _PROVIDER,
                    TeamExternalRef.team_id.in_(
                        {m.home_team_id for m in candidates} | {m.away_team_id for m in candidates}
                    ),
                )
            )
        }
        for match in candidates:
            home_uefa, away_uefa = refs.get(match.home_team_id), refs.get(match.away_team_id)
            if home_uefa is None or away_uefa is None:
                log.warning("UEFA: match %s has a team without a UEFA id — skipping", match.id)
                continue
            try:
                depth = provider.get_match_depth(match.provider_id, str(home_uefa), str(away_uefa))
                if not depth.complete:
                    log.info("UEFA: feed for match %s isn't complete yet — will retry", match.id)
                    continue
                tmap = {
                    team_pid(home_uefa): match.home_team_id,
                    team_pid(away_uefa): match.away_team_id,
                }
                _write_depth(db, match, depth, tmap)
                db.commit()
                enriched += 1
                log.info(
                    "UEFA: %s %s-%s %s  (%d goals, %d cards, %d players)",
                    match.home_team.display_name, match.home_score, match.away_score,
                    match.away_team.display_name, len(depth.goals), len(depth.bookings),
                    len(depth.player_ratings),
                )
            except Exception:  # noqa: BLE001 - one bad match must not abort the run
                db.rollback()
                log.exception("UEFA enrich failed for match %s", match.id)

    provider.close()
    log.info("UEFA enrichment done: %d match(es)", enriched)
    return enriched


def run_uefa_sync() -> None:
    """Fixtures for the recent window, then depth for whatever just finished."""
    sync_uefa_recent()
    enrich_uefa_matches()
