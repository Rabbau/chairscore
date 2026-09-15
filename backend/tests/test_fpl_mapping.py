"""FPL fixture-stats -> normalized dataclasses (offline)."""

from app.providers.fpl import FplProvider

BOOTSTRAP_TEAMS = {1: {"id": 1, "name": "Arsenal", "short_name": "ARS"},
                   7: {"id": 7, "name": "Chelsea", "short_name": "CHE"}}
BOOTSTRAP_PLAYERS = {
    11: {"name": "Odegaard", "team": 1, "position": "MID"},
    12: {"name": "Havertz", "team": 1, "position": "FWD"},
    70: {"name": "Palmer", "team": 7, "position": "MID"},
    71: {"name": "James", "team": 7, "position": "DEF"},
}

FIXTURE = {
    "id": 29,
    "event": 3,
    "team_h": 1,
    "team_a": 7,
    "team_h_score": 2,
    "team_a_score": 1,
    "kickoff_time": "2026-09-06T14:00:00Z",
    "finished": True,
    "stats": [
        {"identifier": "goals_scored",
         "h": [{"value": 1, "element": 11}, {"value": 1, "element": 12}],
         "a": [{"value": 1, "element": 70}]},
        {"identifier": "assists", "h": [{"value": 1, "element": 12}], "a": []},
        {"identifier": "yellow_cards", "h": [], "a": [{"value": 1, "element": 71}]},
        {"identifier": "bonus",
         "h": [{"value": 3, "element": 11}, {"value": 1, "element": 12}], "a": []},
        {"identifier": "bps",
         "h": [{"value": 47, "element": 11}, {"value": 33, "element": 12}],
         "a": [{"value": 21, "element": 70}, {"value": 14, "element": 71}]},
        {"identifier": "saves", "h": [], "a": [{"value": 4, "element": 71}]},
    ],
}


def _provider() -> FplProvider:
    p = FplProvider()
    p._bootstrap = {"teams": list(BOOTSTRAP_TEAMS.values()), "elements": [], "events": []}
    p._teams = BOOTSTRAP_TEAMS
    p._players = BOOTSTRAP_PLAYERS
    return p


def test_match_depth_player_lines():
    p = _provider()
    team_stats, ratings = p.match_depth(FIXTURE, want_player_xg=False)

    by_name = {r.player_name: r for r in ratings}
    assert set(by_name) == {"Odegaard", "Havertz", "Palmer", "James"}

    ode = by_name["Odegaard"]
    assert ode.goals == 1 and ode.bonus == 3 and ode.bps == 47
    assert ode.team_provider_id == 1

    hav = by_name["Havertz"]
    assert (hav.goals, hav.assists, hav.bonus) == (1, 1, 1)

    james = by_name["James"]
    assert james.yellow == 1 and james.saves == 4 and james.team_provider_id == 7


def test_match_depth_team_rollups():
    p = _provider()
    team_stats, _ = p.match_depth(FIXTURE, want_player_xg=False)
    stats = {s.team_provider_id: s for s in team_stats}

    assert stats[1].saves is None  # Arsenal keeper made no saves in the sample
    assert stats[7].saves == 4
    assert stats[7].yellow_cards == 1
    assert stats[1].xg is None  # want_player_xg=False -> no xG rollup
