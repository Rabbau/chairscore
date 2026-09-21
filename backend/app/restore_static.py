"""Restore match enrichment from a static export.

    python -m app.restore_static --from ../docs/data

``export_static`` writes each match's full detail — goals, cards, substitutions,
team stats, player lines, each tagged with the source that supplied it — into
``docs/data/matches/{id}.json``, and that folder is committed. So the export is
already a durable copy of everything the enrichment providers collected. This
puts it back into a database that lost it (a wiped Actions cache, a fresh
clone): otherwise the next export would quietly drop the stats of every match
older than the providers' look-back windows.

Only what is *missing* is restored, keyed on stable provider ids, so it is safe
to run any time and never overwrites fresher data. Run it after the breadth
sync (the matches must exist) and before the enrichers (which then skip what
was restored).
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import SessionLocal
from app.models import (
    Booking,
    Goal,
    Match,
    MatchPlayerRating,
    MatchTeamStat,
    Substitution,
)

log = logging.getLogger("chairscore.restore")

# stat/player ``source`` -> the Match column that tells its enricher "already done"
_SYNCED_FLAG = {
    "fpl": "fpl_synced_at",
    "football-data.co.uk": "fdcouk_synced_at",
    "uefa": "uefa_synced_at",
    "api-football": "depth_synced_at",
}

_STAT_FIELDS = (
    "possession", "shots", "shots_on_target", "corners", "fouls", "offsides",
    "yellow_cards", "red_cards", "passes", "passes_accuracy", "saves", "xg",
)
_PLAYER_FIELDS = (
    "rating", "minutes", "position", "number", "is_starter", "captain", "goals", "assists",
    "yellow", "red", "xg", "xa", "bps", "bonus", "saves",
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def restore_match(db: Session, doc: dict) -> Counter:
    """Put one exported match detail back. Returns what was added, by kind."""
    added: Counter = Counter()
    match = db.scalar(
        select(Match)
        .where(Match.provider_id == doc.get("provider_id"))
        .options(
            selectinload(Match.home_team), selectinload(Match.away_team),
            selectinload(Match.goals), selectinload(Match.bookings),
            selectinload(Match.substitutions), selectinload(Match.team_stats),
            selectinload(Match.player_ratings),
        )
    )
    if match is None:
        added["match not in db"] += 1
        return added
    # The export's internal team ids mean nothing here; the two sides are told
    # apart by provider id, which is stable across databases.
    if (
        doc["home_team"]["provider_id"] != match.home_team.provider_id
        or doc["away_team"]["provider_id"] != match.away_team.provider_id
    ):
        added["team mismatch"] += 1
        return added
    team = {
        doc["home_team"]["id"]: match.home_team_id,
        doc["away_team"]["id"]: match.away_team_id,
    }

    if not match.goals:
        for g in doc.get("goals") or []:
            db.add(Goal(
                match_id=match.id, team_id=team.get(g.get("team_id")), minute=g.get("minute"),
                injury_time=g.get("injury_time"), type=g.get("type"),
                scorer_name=g.get("scorer_name"), assist_name=g.get("assist_name"),
                home_score=g.get("home_score"), away_score=g.get("away_score"),
            ))
            added["goals"] += 1
    if not match.bookings:
        for b in doc.get("bookings") or []:
            db.add(Booking(
                match_id=match.id, team_id=team.get(b.get("team_id")), minute=b.get("minute"),
                player_name=b.get("player_name"), card=b.get("card"),
            ))
            added["bookings"] += 1
    if not match.substitutions:
        for s in doc.get("substitutions") or []:
            db.add(Substitution(
                match_id=match.id, team_id=team.get(s.get("team_id")), minute=s.get("minute"),
                player_in_name=s.get("player_in_name"), player_out_name=s.get("player_out_name"),
            ))
            added["substitutions"] += 1

    have_stats = {(t.team_id, t.source) for t in match.team_stats}
    have_players = {(p.team_id, p.source, p.player_name) for p in match.player_ratings}
    sources: set[str] = set()
    for row in doc.get("team_stats") or []:
        team_id = team.get(row.get("team_id"))
        if team_id is None or (team_id, row["source"]) in have_stats:
            continue
        db.add(MatchTeamStat(
            match_id=match.id, team_id=team_id, source=row["source"],
            **{f: row.get(f) for f in _STAT_FIELDS},
        ))
        have_stats.add((team_id, row["source"]))
        sources.add(row["source"])
        added["team stats"] += 1
    for row in doc.get("player_ratings") or []:
        team_id = team.get(row.get("team_id"))
        key = (team_id, row["source"], row["player_name"])
        if team_id is None or key in have_players:
            continue
        db.add(MatchPlayerRating(
            match_id=match.id, team_id=team_id, source=row["source"],
            player_name=row["player_name"], **{f: row.get(f) for f in _PLAYER_FIELDS},
        ))
        have_players.add(key)
        sources.add(row["source"])
        added["players"] += 1

    # Tell the enrichers this match is done — they'd otherwise re-fetch it.
    for source in sources:
        flag = _SYNCED_FLAG.get(source)
        if flag and getattr(match, flag) is None:
            setattr(match, flag, _now())
    return added


def run(src: Path) -> Counter:
    total: Counter = Counter()
    files = sorted((src / "matches").glob("*.json"))
    with SessionLocal() as db:
        for path in files:
            if path.stem == "window":  # the home-feed window, not a match
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                total.update(restore_match(db, doc))
                db.commit()  # per file, so one bad file only rolls back itself
                total["files"] += 1
            except Exception:  # noqa: BLE001 - one bad file must not stop the rest
                db.rollback()
                total["errors"] += 1
                log.exception("could not restore %s", path.name)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="app.restore_static", description="Restore match enrichment from a static export"
    )
    parser.add_argument(
        "--from", dest="src", default="../docs/data",
        help="static export directory (default: ../docs/data)",
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    src = Path(args.src).resolve()
    if not (src / "matches").is_dir():
        log.info("no static export at %s — nothing to restore", src)
        return
    total = run(src)
    log.info(
        "restored from %d match files: %s",
        total.pop("files", 0),
        ", ".join(f"{n} {kind}" for kind, n in sorted(total.items())) or "nothing to add",
    )


if __name__ == "__main__":
    main()
