"""Static JSON export for the GitHub Pages build.

    python -m app.export_static --out ../docs/data

Dumps a read-only snapshot of the database as a tree of JSON files that
``frontend/src/api/staticClient.ts`` reads instead of calling the live API.
Every value is produced by calling the *same* endpoint functions the FastAPI
routes use (imported directly, `db=` passed by hand instead of resolved via
``Depends``) — the static site and the live API can never drift apart in how
a response is shaped.

Scope, to keep the export fast and the output bounded:
* competitions / standings / scorers / match lists — every season on record,
  for every tracked competition (cheap: aggregate queries, not per-match).
* match *detail* (goals, events, head-to-head, form, player stats) — only for
  the current season of each tracked competition. Head-to-head still looks
  across the full history in the DB; only the *page* for an older match is
  skipped. Pass --all-seasons to lift this (slow: one query bundle per match).
* team detail — every team.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.competitions import get_competition_matches, get_scorers, get_standings
from app.api.matches import get_match
from app.api.teams import get_team
from app.config import settings
from app.db import SessionLocal
from app.models import Competition, Team
from app.schemas import CompetitionOut, MatchOut

log = logging.getLogger("chairscore.export")


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _dump(model) -> dict:
    return model.model_dump(mode="json")


def _seasons_for(db: Session, comp: Competition) -> list[str]:
    from app.models import Match, Standing

    seasons = set(
        db.scalars(select(Match.season).where(Match.competition_id == comp.id).distinct())
    )
    seasons |= set(
        db.scalars(select(Standing.season).where(Standing.competition_id == comp.id).distinct())
    )
    return sorted((s for s in seasons if s), reverse=True)


def export_competition(
    db: Session, out: Path, comp: Competition, *, all_seasons: bool
) -> list[int]:
    code = comp.code
    seasons = _seasons_for(db, comp)
    _write(out / "competitions" / code / "index.json", _dump(CompetitionOut.model_validate(comp)))
    _write(out / "competitions" / code / "seasons.json", seasons)

    detail_match_ids: list[int] = []
    detail_seasons = seasons if all_seasons else seasons[:1]

    for season in seasons:
        standings = get_standings(code, season=season, type="TOTAL", db=db)
        _write(out / "competitions" / code / "standings" / f"{season}.json", _dump(standings))

        scorers = get_scorers(code, season=season, limit=50, db=db)
        _write(out / "competitions" / code / "scorers" / f"{season}.json", _dump(scorers))

        # Every Query(...)-defaulted param needs an explicit value here — called
        # directly (no FastAPI request), an omitted one would hand the function
        # a fastapi.params.Query sentinel instead of the value it expects.
        matches = get_competition_matches(
            code, season=season, matchday=None, status=None,
            date_from=None, date_to=None, limit=1000, db=db,
        )
        match_outs = [_dump(MatchOut.model_validate(m)) for m in matches]
        _write(out / "competitions" / code / "matches" / f"{season}.json", match_outs)
        if season in detail_seasons:
            detail_match_ids += [m.id for m in matches]

    return detail_match_ids


def export_match_details(db: Session, out: Path, match_ids: list[int]) -> int:
    written = 0
    for mid in match_ids:
        try:
            detail = get_match(mid, db=db)
        except Exception:  # noqa: BLE001 - one bad match must not abort the export
            log.exception("match %s export failed", mid)
            continue
        _write(out / "matches" / f"{mid}.json", _dump(detail))
        written += 1
    return written


def export_teams(db: Session, out: Path) -> int:
    ids = db.scalars(select(Team.id)).all()
    written = 0
    for tid in ids:
        try:
            detail = get_team(tid, match_limit=10, db=db)
        except Exception:  # noqa: BLE001
            log.exception("team %s export failed", tid)
            continue
        _write(out / "teams" / f"{tid}.json", _dump(detail))
        written += 1
    return written


def export_home_window(db: Session, out: Path) -> int:
    """Matches across all tracked competitions, for the home page — the client
    groups these by day itself, same as the live /api/matches feed does."""
    from datetime import timedelta

    from app.api.deps import match_query
    from app.models import Match

    start = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=settings.match_window_past_days)
    end = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=settings.match_window_future_days)
    stmt = (
        match_query()
        .where(Match.utc_date >= start, Match.utc_date < end)
        .order_by(Match.utc_date, Match.id)
    )
    matches = db.scalars(stmt).unique().all()
    out_list = [_dump(MatchOut.model_validate(m)) for m in matches]
    _write(out / "matches" / "window.json", out_list)
    return len(out_list)


def export_search_index(db: Session, out: Path) -> None:
    from app.schemas.common import TeamOut

    comps = db.scalars(
        select(Competition).where(Competition.code.in_(settings.served_competition_codes))
    ).all()
    teams = db.scalars(select(Team)).all()
    _write(
        out / "search-index.json",
        {
            "competitions": [_dump(CompetitionOut.model_validate(c)) for c in comps],
            "teams": [_dump(TeamOut.model_validate(t)) for t in teams],
        },
    )


def run(out_dir: Path, *, all_seasons: bool = False) -> None:
    t0 = time.monotonic()
    out_dir.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        comps = db.scalars(
            select(Competition)
            .where(Competition.code.in_(settings.served_competition_codes))
            .order_by(Competition.name)
        ).all()
        _write(
            out_dir / "competitions.json",
            [_dump(CompetitionOut.model_validate(c)) for c in comps],
        )
        export_search_index(db, out_dir)

        n_home = export_home_window(db, out_dir)
        log.info("home window: %d matches", n_home)

        detail_ids: list[int] = []
        tracked = set(settings.served_competition_codes)
        for comp in comps:
            ids = export_competition(db, out_dir, comp, all_seasons=all_seasons)
            detail_ids += ids
            log.info("[%s] exported (%d matches queued for detail)", comp.code, len(ids))

        n_detail = export_match_details(db, out_dir, sorted(set(detail_ids)))
        log.info("match detail: %d files", n_detail)

        n_teams = export_teams(db, out_dir)
        log.info("teams: %d files", n_teams)

        _write(
            out_dir / "meta.json",
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "tracked_competitions": sorted(tracked),
                "match_detail_count": n_detail,
                "team_count": n_teams,
            },
        )

    log.info("export done in %.1fs -> %s", time.monotonic() - t0, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="app.export_static", description="Export a static JSON snapshot"
    )
    parser.add_argument(
        "--out", default="../docs/data", help="output directory (default: ../docs/data)"
    )
    parser.add_argument(
        "--all-seasons", action="store_true",
        help="export match-detail JSON for every season, not just the current one (slow)",
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    run(Path(args.out).resolve(), all_seasons=args.all_seasons)


if __name__ == "__main__":
    main()
