"""Combine what several sources say about the same match.

A match can carry more than one ``MatchTeamStat`` row per team — a Premier League
game has Football-Data.co.uk (shots, corners, cards, xG) and FPL (its own xG,
saves), and a provider gap-fill would add more. ``merge_team_stats`` folds them
into one row per team: for every stat the value from the most trusted source
that has one, and a record of which source that was so the UI can say so.

Filling holes this way is why a missing number is only ever missing when *no*
source has it — enrichers write what they have and never try to reproduce each
other's fields.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

# Most trusted first. Sources that cover different competitions (UEFA vs the
# league CSVs) never actually compete; the order settles overlaps, e.g. a
# Premier League match's xG from Football-Data.co.uk over FPL's.
SOURCE_PRIORITY = ("football-data.co.uk", "uefa", "api-football", "fpl")

STAT_FIELDS = (
    "possession",
    "shots",
    "shots_on_target",
    "corners",
    "fouls",
    "offsides",
    "yellow_cards",
    "red_cards",
    "passes",
    "passes_accuracy",
    "saves",
    "xg",
)


def _rank(source: str) -> tuple[int, str]:
    known = SOURCE_PRIORITY.index(source) if source in SOURCE_PRIORITY else len(SOURCE_PRIORITY)
    return known, source


def merge_team_stats(rows: Iterable[Any]) -> list[dict]:
    """One merged dict per team, from rows exposing ``team_id``, ``source`` and
    the stat fields (ORM ``MatchTeamStat`` rows or anything shaped like them)."""
    by_team: dict[int, list[Any]] = defaultdict(list)
    for row in rows:
        if row.team_id is not None:
            by_team[row.team_id].append(row)

    merged = []
    for team_id, group in by_team.items():
        group.sort(key=lambda r: _rank(r.source))
        out: dict[str, Any] = {"team_id": team_id, "field_sources": {}}
        for name in STAT_FIELDS:
            out[name] = None
            for row in group:
                value = getattr(row, name)
                if value is not None:
                    out[name] = value
                    out["field_sources"][name] = row.source
                    break
        # contributing sources, most trusted first
        out["sources"] = sorted(set(out["field_sources"].values()), key=_rank)
        merged.append(out)
    return merged
