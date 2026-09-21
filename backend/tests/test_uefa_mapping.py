"""UEFA payloads -> normalized objects, on trimmed copies of real responses
(tests/fixtures/uefa). The Como 4-1 Leipzig match (UEFA id 2049570) doubles as
the check on the event-feed counting: both teams were playing their first
match of the season, so UEFA's own season aggregates for them *are* that
match's official numbers (on target 6/5, corners 1/5, fouls 9/10, yellows 2/3)."""

import json
from datetime import date
from pathlib import Path

from app.providers.uefa import (
    UEFA_ID_OFFSET,
    UefaProvider,
    build_depth,
    current_season,
    map_match,
    map_scorers,
    map_standings,
    map_team,
    season_from_uefa_year,
    uefa_season_year,
)

FIXTURES = Path(__file__).parent / "fixtures" / "uefa"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _match(uefa_id: str):
    raw = next(m for m in _load("matches.json") if m["id"] == uefa_id)
    return map_match(raw, "CL")


COMO, LEIPZIG = 79946, 2603790


# --------------------------------------------------------------------------- #
# matches
# --------------------------------------------------------------------------- #
def test_league_phase_match():
    m = _match("2049570")
    assert m.provider_id == UEFA_ID_OFFSET + 2049570
    assert m.season == "2026"  # UEFA's seasonYear 2027 is our 2026-27
    assert (m.status, m.stage, m.matchday) == ("FINISHED", "LEAGUE_STAGE", 1)
    assert (m.home_score, m.away_score) == (4, 1)
    assert (m.home_score_ht, m.away_score_ht) == (2, 0)  # counted from first-half goals
    assert (m.winner, m.duration) == ("HOME_TEAM", "REGULAR")
    assert m.home_team.name == "Como 1907"
    assert m.venue
    assert {r["type"] for r in m.referees} <= {"REFEREE", "VAR"}
    assert m.referees[0]["type"] == "REFEREE"  # listed ahead of the VAR official


def test_penalty_shootout_final():
    m = _match("2047742")
    assert m.season == "2025"
    assert m.stage == "FINAL"
    assert (m.home_score, m.away_score) == (1, 1)  # shoot-out kept out of the score
    assert (m.home_score_pen, m.away_score_pen) == (4, 3)
    assert (m.duration, m.winner) == ("PENALTY_SHOOTOUT", "HOME_TEAM")
    assert m.matchday is None


def test_own_goal_counts_for_the_other_side_at_half_time():
    m = _match("2045906")  # Tottenham 1-0 Villarreal, own goal by Villarreal's keeper
    assert (m.home_score, m.away_score) == (1, 0)
    assert (m.home_score_ht, m.away_score_ht) == (1, 0)


def test_extra_time_match():
    m = _match("2047770")
    assert (m.home_score, m.away_score) == (3, 2)
    assert m.duration == "EXTRA_TIME"
    assert m.stage == "PLAYOFFS"


def test_upcoming_match_has_no_result():
    m = _match("2049577")
    assert m.status == "TIMED"
    assert (m.home_score, m.away_score, m.winner, m.duration) == (None, None, None, None)
    assert (m.home_score_ht, m.home_score_pen) == (None, None)


def test_team_mapping():
    raw = _load("matches.json")[0]["homeTeam"]
    t = map_team(raw)
    assert t.provider_id == UEFA_ID_OFFSET + COMO
    assert (t.name, t.short_name, t.tla, t.area_name) == ("Como 1907", "Como", "COM", "Italy")
    assert t.crest_url and t.crest_url.startswith("https://")
    assert "Como" in t.aliases and "Como 1907" in t.aliases


# --------------------------------------------------------------------------- #
# tables / scorers
# --------------------------------------------------------------------------- #
def test_standings_league_phase():
    provider = UefaProvider(["CL"])
    st = map_standings(provider._competition("CL", "2026"), "2026", _load("standings.json"))
    assert len(st.rows) == 3
    first = st.rows[0]
    assert (first.position, first.stage, first.group) == (1, "LEAGUE_STAGE", None)
    assert first.type == "TOTAL"
    assert first.points == first.won * 3 + first.draw
    assert first.goal_difference == first.goals_for - first.goals_against


def test_scorers():
    scorers = map_scorers(_load("scorers.json"))
    assert len(scorers) == 3
    top = scorers[0]
    assert top.goals >= scorers[-1].goals
    assert top.team is not None and top.position == "FWD" and top.played_matches == 1


# --------------------------------------------------------------------------- #
# depth: lineups + event feed
# --------------------------------------------------------------------------- #
def _depth():
    return build_depth(_load("lineups.json"), _load("events.json"))


def test_team_stats_match_uefas_official_numbers():
    depth = _depth()
    assert depth.complete
    by_team = {t.team_provider_id - UEFA_ID_OFFSET: t for t in depth.team_stats}
    como, leipzig = by_team[COMO], by_team[LEIPZIG]
    assert (como.shots_on_target, como.corners, como.fouls, como.yellow_cards) == (6, 1, 9, 2)
    assert (leipzig.shots_on_target, leipzig.corners) == (5, 5)
    assert (leipzig.fouls, leipzig.yellow_cards) == (10, 3)
    # UEFA's "attempts": on target + off target + blocked
    assert (como.shots, leipzig.shots) == (12, 13)
    # a goalkeeper's saves are the shots on target that weren't goals
    assert (como.saves, leipzig.saves) == (4, 2)
    assert (como.possession, como.passes) == (None, None)  # not available per match


def test_goals_carry_running_score_and_assists():
    goals = _depth().goals
    assert [(g.home_score, g.away_score) for g in goals] == [(1, 0), (2, 0), (3, 0), (3, 1), (4, 1)]
    assert [g.minute for g in goals] == [15, 38, 54, 58, 90]
    assert goals[1].scorer_name == "Tasos Douvikas" and goals[1].assist_name == "Martin Baturina"
    assert goals[0].assist_name is None  # unassisted
    assert all(g.type == "REGULAR" for g in goals)
    assert goals[0].team_provider_id == UEFA_ID_OFFSET + COMO
    assert goals[3].team_provider_id == UEFA_ID_OFFSET + LEIPZIG


def test_players_minutes_and_marks():
    depth = _depth()
    players = {p.player_name: p for p in depth.player_ratings}
    assert len(players) == 45
    assert sum(p.is_starter for p in depth.player_ratings) == 22

    douvikas = players["Tasos Douvikas"]  # scored, then subbed off on 65'
    assert (douvikas.is_starter, douvikas.minutes) == (True, 65)
    assert (douvikas.goals, douvikas.number) == (1, 9)
    assert douvikas.position == "FWD"
    kean = players["Moise Kean"]  # came on for Douvikas
    assert (kean.is_starter, kean.minutes) == (False, 25)
    unused = [p for p in depth.player_ratings if not p.is_starter and p.minutes == 0]
    assert len(unused) == 13
    assert players["Máximo Perrone"].yellow == 1 and players["Máximo Perrone"].goals == 1


def test_bookings_and_substitutions():
    depth = _depth()
    assert [(b.minute, b.card) for b in depth.bookings] == [
        (2, "YELLOW"), (24, "YELLOW"), (47, "YELLOW"), (64, "YELLOW"), (90, "YELLOW"),
    ]
    assert len(depth.substitutions) == 10
    first = depth.substitutions[0]
    assert (first.minute, first.player_out_name, first.player_in_name) == (
        60, "Nicolas Seiwald", "Tidiam Gomis",
    )


# -- feed edge cases, on hand-built events -----------------------------------
def _ev(kind, team, person=None, phase="SECOND_HALF", minute=70, **extra):
    actor = {"type": "PLAYER", "team": {"id": str(team)}, "person": person or {}}
    return {"type": kind, "phase": phase, "time": {"minute": minute, "second": 0},
            "timestamp": f"2026-09-10T20:{minute % 60:02d}:00.000Z", "primaryActor": actor, **extra}


def _p(pid, name="P"):
    return {"id": str(pid), "internationalName": f"{name}{pid}", "fieldPosition": "MIDFIELDER"}


HOME, AWAY = "1", "2"


def _feed(*events):
    return build_depth(None, [*events, {"type": "FULL_TIME", "phase": "SECOND_HALF"}], HOME, AWAY)


def test_own_goal_is_credited_to_the_opponent_and_is_no_shot():
    depth = _feed(_ev("GOAL", HOME, _p(10), subType="OWN"))
    goal = depth.goals[0]
    assert goal.type == "OWN"
    assert goal.team_provider_id == UEFA_ID_OFFSET + int(AWAY)
    assert (goal.home_score, goal.away_score) == (0, 1)
    stats = {t.team_provider_id - UEFA_ID_OFFSET: t for t in depth.team_stats}
    assert stats[int(HOME)].shots == 0 and stats[int(AWAY)].shots == 0


def test_second_yellow_is_one_dismissal():
    depth = _feed(
        _ev("YELLOW_CARD", HOME, _p(10), minute=30),
        _ev("YELLOW_CARD_SECOND", HOME, _p(10), minute=60),
        _ev("RED_YELLOW_CARD", HOME, _p(10), minute=60),
    )
    assert [(b.minute, b.card) for b in depth.bookings] == [(30, "YELLOW"), (60, "YELLOW_RED")]
    home = next(t for t in depth.team_stats if t.team_provider_id == UEFA_ID_OFFSET + int(HOME))
    assert (home.yellow_cards, home.red_cards) == (2, 1)


def test_cards_shown_to_staff_are_ignored():
    staff = {"type": "COACH", "team": {"id": HOME}, "person": {"person": {"id": "9"}}}
    depth = _feed({"type": "YELLOW_CARD", "phase": "SECOND_HALF", "primaryActor": staff})
    assert depth.bookings == []
    home = next(t for t in depth.team_stats if t.team_provider_id == UEFA_ID_OFFSET + int(HOME))
    assert home.yellow_cards == 0


def test_shootout_kicks_are_not_match_events():
    depth = _feed(
        _ev("PENALTY", HOME, _p(10), phase="PENALTY", subType="SCORED"),
        _ev("GOAL", HOME, _p(11), phase="PENALTY"),
    )
    assert depth.goals == []
    assert all(t.shots == 0 for t in depth.team_stats)


def test_penalty_goal_type_and_extra_time_length():
    depth = build_depth(
        {
            "homeTeam": {"team": {"id": HOME}, "field": [
                {"jerseyNumber": 9, "player": _p(10)}], "bench": []},
            "awayTeam": {"team": {"id": AWAY}, "field": [], "bench": []},
        },
        [
            _ev("GOAL", HOME, _p(10), phase="EXTRA_TIME_FIRST_HALF", minute=105, subType="PENALTY"),
            {"type": "FULL_TIME", "phase": "EXTRA_TIME_SECOND_HALF"},
        ],
    )
    assert depth.goals[0].type == "PENALTY"
    # a full match that went to extra time is 120 minutes long
    assert depth.player_ratings[0].minutes == 120


def test_feed_without_full_time_is_incomplete():
    depth = build_depth(None, [_ev("CORNER", HOME)], HOME, AWAY)
    assert depth.complete is False


# --------------------------------------------------------------------------- #
# seasons
# --------------------------------------------------------------------------- #
def test_season_conventions():
    assert uefa_season_year("2026") == "2027"
    assert season_from_uefa_year("2027") == "2026"
    assert current_season(date(2026, 9, 21)) == "2026"
    assert current_season(date(2027, 6, 30)) == "2026"  # UEFA rolls over on 1 July
    assert current_season(date(2027, 7, 1)) == "2027"
