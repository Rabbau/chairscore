"""API-Football JSON -> normalized dataclass mapping."""

import pytest

from app.providers.api_football import ApiFootballProvider, _matchday_from_round, _name_overlap

FIXTURE = {
    "fixture": {
        "id": 1035037,
        "referee": "Michael Oliver, England",
        "date": "2024-08-17T14:00:00+00:00",
        "status": {"long": "Match Finished", "short": "FT", "elapsed": 90},
        "venue": {"id": 556, "name": "Anfield", "city": "Liverpool"},
    },
    "league": {"id": 39, "name": "Premier League", "country": "England", "season": 2024,
               "round": "Regular Season - 1"},
    "teams": {
        "home": {"id": 40, "name": "Liverpool", "logo": "l.png", "winner": True},
        "away": {"id": 35, "name": "Bournemouth", "logo": "b.png", "winner": False},
    },
    "goals": {"home": 2, "away": 0},
    "score": {
        "halftime": {"home": 1, "away": 0},
        "fulltime": {"home": 2, "away": 0},
        "extratime": {"home": None, "away": None},
        "penalty": {"home": None, "away": None},
    },
}


def test_matchday_from_round():
    assert _matchday_from_round("Regular Season - 12") == 12
    assert _matchday_from_round("Group Stage - 3") == 3
    assert _matchday_from_round("8th Finals") == 8
    assert _matchday_from_round(None) is None


def test_name_overlap():
    assert _name_overlap("Liverpool FC", "Liverpool") == pytest.approx(1.0)
    assert _name_overlap("Manchester United FC", "Manchester United") == pytest.approx(1.0)
    assert _name_overlap("Inter", "Internazionale") == 0.0
    assert _name_overlap("Arsenal", "Chelsea") == 0.0


def test_fixture_mapping():
    m = ApiFootballProvider._match(FIXTURE, "PL")
    assert m.provider_id == 1035037
    assert m.competition_code == "PL"
    assert m.competition_provider_id == 39
    assert m.season == "2024"
    assert m.status == "FINISHED"
    assert m.matchday == 1
    assert m.home_team.provider_id == 40
    assert m.away_team.name == "Bournemouth"
    assert (m.home_score, m.away_score) == (2, 0)
    assert (m.home_score_ht, m.away_score_ht) == (1, 0)
    assert m.winner == "HOME_TEAM"
    assert m.venue == "Anfield"
    assert m.referees == [{"name": "Michael Oliver", "type": "REFEREE"}]
    assert m.utc_date.year == 2024 and m.utc_date.hour == 14


def test_status_mapping():
    for short, expected in [("NS", "SCHEDULED"), ("1H", "IN_PLAY"), ("HT", "PAUSED"),
                            ("FT", "FINISHED"), ("PEN", "FINISHED"), ("PST", "POSTPONED"),
                            ("AWD", "AWARDED")]:
        fx = {**FIXTURE, "fixture": {**FIXTURE["fixture"], "status": {"short": short}}}
        assert ApiFootballProvider._match(fx, "PL").status == expected


def test_draw_winner():
    fx = {
        **FIXTURE,
        "teams": {
            "home": {"id": 1, "name": "A", "winner": None},
            "away": {"id": 2, "name": "B", "winner": None},
        },
        "goals": {"home": 1, "away": 1},
    }
    assert ApiFootballProvider._match(fx, "PL").winner == "DRAW"


def _provider_with(rows_by_path):
    p = ApiFootballProvider(key="test")
    p._get = lambda path, params=None, _retries=3: rows_by_path.get(path, [])  # type: ignore
    return p


def test_events_mapping():
    rows = [
        {"time": {"elapsed": 23, "extra": None}, "team": {"id": 40}, "player": {"name": "Salah"},
         "assist": {"name": "Diaz"}, "type": "Goal", "detail": "Normal Goal"},
        {"time": {"elapsed": 55, "extra": None}, "team": {"id": 40}, "player": {"name": "Nunez"},
         "assist": {"name": None}, "type": "Goal", "detail": "Penalty"},
        {"time": {"elapsed": 61, "extra": None}, "team": {"id": 35}, "player": {"name": "Cook"},
         "assist": {"name": None}, "type": "Card", "detail": "Yellow Card"},
        {"time": {"elapsed": 70, "extra": None}, "team": {"id": 40}, "player": {"name": "Jota"},
         "assist": {"name": "Gakpo"}, "type": "subst", "detail": "Substitution 1"},
        {"time": {"elapsed": 80, "extra": None}, "team": {"id": 35}, "player": {"name": "X"},
         "assist": {"name": None}, "type": "Goal", "detail": "Missed Penalty"},
    ]
    goals, bookings, subs = _provider_with({"fixtures/events": rows}).get_fixture_events(1)
    assert [g.type for g in goals] == ["REGULAR", "PENALTY"]  # missed penalty dropped
    assert goals[0].scorer_name == "Salah" and goals[0].assist_name == "Diaz"
    assert bookings[0].card == "YELLOW"
    assert subs[0].player_out_name == "Jota" and subs[0].player_in_name == "Gakpo"


def test_statistics_mapping():
    rows = [
        {"team": {"id": 40}, "statistics": [
            {"type": "Ball Possession", "value": "62%"},
            {"type": "Total Shots", "value": 14},
            {"type": "Shots on Goal", "value": 6},
            {"type": "Passes %", "value": "88%"},
            {"type": "expected_goals", "value": "2.35"},
        ]},
    ]
    stats = _provider_with({"fixtures/statistics": rows}).get_fixture_statistics(1)
    assert stats[0].team_provider_id == 40
    assert stats[0].possession == 62
    assert stats[0].shots == 14
    assert stats[0].shots_on_target == 6
    assert stats[0].passes_accuracy == 88
    assert stats[0].xg == pytest.approx(2.35)


def test_player_ratings_mapping():
    rows = [
        {"team": {"id": 40}, "players": [
            {"player": {"id": 306, "name": "Salah"},
             "statistics": [{"games": {"minutes": 90, "position": "F", "rating": "8.4",
                                       "captain": False, "substitute": False, "number": 11},
                             "goals": {"total": 1, "assists": 1},
                             "cards": {"yellow": 0, "red": 0}}]},
        ]},
    ]
    ratings = _provider_with({"fixtures/players": rows}).get_fixture_player_ratings(1)
    r = ratings[0]
    assert r.player_name == "Salah" and r.rating == pytest.approx(8.4)
    assert r.minutes == 90 and r.is_starter is True and r.goals == 1


def test_standings_mapping():
    team_all = {"played": 3, "win": 3, "draw": 0, "lose": 0, "goals": {"for": 9, "against": 2}}
    rows = [{
        "league": {"id": 39, "season": 2024, "standings": [[
            {"rank": 1, "team": {"id": 50, "name": "Man City", "logo": "c.png"}, "points": 9,
             "goalsDiff": 7, "group": "Premier League", "form": "WWW", "all": team_all},
        ]]},
    }]
    st = _provider_with({"standings": rows}).get_standings("PL", season="2024")
    assert st.season == "2024"
    row = st.rows[0]
    assert row.position == 1 and row.points == 9 and row.won == 3
    assert row.goals_for == 9 and row.goal_difference == 7
    assert row.form == "W,W,W"
