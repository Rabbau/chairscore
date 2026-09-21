"""Where are the holes? A coverage report over the finished matches in the database.

    python -m app.report            # current season of every served competition
    python -m app.report --season 2025
    python -m app.report --missing 5   # also list a few matches with no stats at all

For each competition: how many finished matches have team stats (from any source),
which sources supplied them, which stat fields are filled, and how many have a
goal/card timeline and lineups. It answers "what is still missing, and would
another source help?" without guessing.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.merge import STAT_FIELDS, merge_team_stats
from app.models import Competition, Goal, Match, MatchPlayerRating

_FINISHED = ("FINISHED", "AWARDED")


def coverage(db: Session, code: str, season: str | None = None) -> dict | None:
    comp = db.scalar(select(Competition).where(Competition.code == code))
    if comp is None:
        return None
    season = season or db.scalar(
        select(func.max(Match.season)).where(Match.competition_id == comp.id)
    )
    if season is None:
        return None

    matches = db.scalars(
        select(Match)
        .where(
            Match.competition_id == comp.id,
            Match.season == season,
            Match.status.in_(_FINISHED),
        )
        .options(selectinload(Match.team_stats))
        .order_by(Match.utc_date.desc())
    ).all()
    ids = [m.id for m in matches]

    with_goals = set(db.scalars(select(Goal.match_id).where(Goal.match_id.in_(ids)).distinct()))
    with_lineups = set(
        db.scalars(
            select(MatchPlayerRating.match_id)
            .where(MatchPlayerRating.match_id.in_(ids), MatchPlayerRating.number.is_not(None))
            .distinct()
        )
    )
    with_players = set(
        db.scalars(
            select(MatchPlayerRating.match_id).where(MatchPlayerRating.match_id.in_(ids)).distinct()
        )
    )

    sources: Counter = Counter()
    fields: Counter = Counter()
    bare: list[Match] = []
    for m in matches:
        merged = merge_team_stats(m.team_stats)
        if not merged:
            bare.append(m)
            continue
        sources.update({s for row in merged for s in row["sources"]})
        for name in STAT_FIELDS:
            if all(row[name] is not None for row in merged) and len(merged) == 2:
                fields[name] += 1

    return {
        "code": code,
        "season": season,
        "finished": len(matches),
        "with_stats": len(matches) - len(bare),
        "sources": dict(sources),
        "fields": {name: fields[name] for name in STAT_FIELDS},
        "with_events": len(with_goals),
        "with_lineups": len(with_lineups),
        "with_players": len(with_players),
        "bare": bare,
    }


def _pct(n: int, total: int) -> str:
    return f"{n:>4} ({100 * n // total:>3}%)" if total else f"{n:>4}      "


def render(report: dict, missing: int = 0) -> str:
    total = report["finished"]
    lines = [f"{report['code']} {report['season']}: {total} finished matches"]
    if not total:
        return lines[0]
    lines.append(f"  team stats   {_pct(report['with_stats'], total)}   "
                 + (", ".join(f"{s} {n}" for s, n in sorted(report["sources"].items())) or "-"))
    filled = [f"{name} {n}" for name, n in report["fields"].items() if n]
    lines.append("  stat fields  " + (", ".join(filled) or "none complete for both teams"))
    lines.append(f"  events       {_pct(report['with_events'], total)}")
    lines.append(f"  lineups      {_pct(report['with_lineups'], total)}")
    if report["with_players"] != report["with_lineups"]:
        lines.append(f"  player lines {_pct(report['with_players'], total)}")
    for m in report["bare"][:missing]:
        lines.append(f"    no stats: {m.utc_date:%Y-%m-%d} "
                     f"{m.home_team.display_name} {m.home_score}-{m.away_score} "
                     f"{m.away_team.display_name}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.report", description="Data coverage report")
    parser.add_argument("--season", help="season start year (default: latest per competition)")
    parser.add_argument("--code", help="comma-separated competition codes (default: all served)")
    parser.add_argument("--missing", type=int, default=0, help="list N matches with no stats")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    codes = [c.strip().upper() for c in args.code.split(",")] if args.code else (
        settings.served_competition_codes
    )
    with SessionLocal() as db:
        for code in codes:
            report = coverage(db, code, args.season)
            if report:
                print(render(report, args.missing))
                print()


if __name__ == "__main__":
    main()
