"""The football-data.org JSON -> normalized dataclass mapping."""

from app.providers.football_data import FootballDataProvider

SAMPLE_MATCH = {
    "id": 497420,
    "utcDate": "2024-08-17T14:00:00Z",
    "status": "FINISHED",
    "matchday": 1,
    "stage": "REGULAR_SEASON",
    "group": None,
    "lastUpdated": "2024-08-17T16:10:00Z",
    "season": {"startDate": "2024-08-16", "endDate": "2025-05-25", "currentMatchday": 1},
    "homeTeam": {"id": 64, "name": "Liverpool FC", "shortName": "Liverpool", "tla": "LIV",
                 "crest": "https://crests.football-data.org/64.png"},
    "awayTeam": {"id": 1044, "name": "AFC Bournemouth", "shortName": "Bournemouth", "tla": "BOU",
                 "crest": "https://crests.football-data.org/1044.png"},
    "score": {
        "winner": "HOME_TEAM",
        "duration": "REGULAR",
        "fullTime": {"home": 2, "away": 0},
        "halfTime": {"home": 1, "away": 0},
    },
    "goals": [
        {"minute": 37, "injuryTime": None, "type": "REGULAR",
         "team": {"id": 64, "name": "Liverpool FC"},
         "scorer": {"id": 7801, "name": "Diogo Jota"},
         "assist": {"id": 3754, "name": "Mohamed Salah"},
         "score": {"home": 1, "away": 0}},
    ],
    "bookings": [
        {"minute": 40, "team": {"id": 1044}, "player": {"id": 1, "name": "Marcos Senesi"},
         "card": "YELLOW"},
    ],
    "substitutions": [
        {"minute": 66, "team": {"id": 64}, "playerOut": {"name": "Diogo Jota"},
         "playerIn": {"name": "Darwin Núñez"}},
    ],
}


def test_match_mapping():
    m = FootballDataProvider._match(SAMPLE_MATCH, "PL", 2021)
    assert m.provider_id == 497420
    assert m.season == "2024"
    assert m.status == "FINISHED"
    assert m.home_team.tla == "LIV"
    assert m.away_team.name == "AFC Bournemouth"
    assert (m.home_score, m.away_score) == (2, 0)
    assert (m.home_score_ht, m.away_score_ht) == (1, 0)
    assert m.winner == "HOME_TEAM"
    assert m.utc_date.year == 2024 and m.utc_date.hour == 14

    assert len(m.goals) == 1
    g = m.goals[0]
    assert g.minute == 37 and g.scorer_name == "Diogo Jota" and g.assist_name == "Mohamed Salah"
    assert g.team_provider_id == 64

    assert m.bookings[0].card == "YELLOW"
    assert m.substitutions[0].player_in_name == "Darwin Núñez"


def test_competition_mapping():
    raw = {
        "id": 2021, "code": "PL", "name": "Premier League", "type": "LEAGUE",
        "emblem": "https://crests.football-data.org/PL.png",
        "area": {"name": "England", "code": "ENG", "flag": "https://flags/770.svg"},
        "currentSeason": {"startDate": "2024-08-16", "endDate": "2025-05-25", "currentMatchday": 4},
    }
    c = FootballDataProvider._competition(raw)
    assert c.code == "PL"
    assert c.area_name == "England"
    assert c.current_season == "2024"
    assert c.current_matchday == 4
