"""Football-Data.co.uk CSV row -> normalized team stats + name matching."""

from app.providers.api_football import _name_overlap
from app.providers.football_data_co_uk import (
    FootballDataCoUkProvider,
    _alias,
    _fdcouk_season,
    _parse_date,
)

ROW = {
    "Div": "E0", "Date": "21/08/2026", "Time": "20:00",
    "HomeTeam": "Arsenal", "AwayTeam": "Coventry",
    "FTHG": "3", "FTAG": "0",
    "Referee": "T Bramall",
    "HxG": "1.88", "AxG": "0.2",
    "HS": "20", "AS": "4", "HST": "6", "AST": "1",
    "HF": "10", "AF": "13", "HC": "8", "AC": "2",
    "HY": "1", "AY": "1", "HR": "0", "AR": "0",
}


def test_team_stats_parses_both_sides():
    home, away = FootballDataCoUkProvider.team_stats(ROW)
    assert (home.shots, home.shots_on_target, home.corners) == (20, 6, 8)
    assert (home.fouls, home.yellow_cards, home.red_cards) == (10, 1, 0)
    assert home.xg == 1.88

    assert (away.shots, away.shots_on_target, away.corners) == (4, 1, 2)
    assert away.xg == 0.2


def test_season_format():
    assert _fdcouk_season("2025") == "2526"
    assert _fdcouk_season("2026") == "2627"
    assert _fdcouk_season("2023") == "2324"


def test_parse_date():
    assert _parse_date("21/08/2026").isoformat() == "2026-08-21"
    assert _parse_date("garbage") is None


def test_aliases_resolve_known_abbreviations():
    # a sample covering every mismatch class found across the 5 tracked
    # leagues' current season (see chairscore-project memory): dropped
    # suffix, whole-word abbreviation, missing qualifier, English/local
    # spelling.
    cases = [
        ("Man City", "Manchester City FC"),
        ("Man United", "Manchester United FC"),
        ("Nott'm Forest", "Nottingham Forest FC"),
        ("Ath Bilbao", "Athletic Club"),
        ("Bayern Munich", "FC Bayern München"),
        ("Inter", "FC Internazionale Milano"),
        ("Brest", "Stade Brestois 29"),
    ]
    for fdcouk_name, db_name in cases:
        score = _name_overlap(_alias(fdcouk_name), db_name)
        assert score >= 0.9, f"{fdcouk_name!r} vs {db_name!r} -> {score}"


def test_accented_names_match_without_alias():
    # diacritic-insensitive matching (no hardcoded alias needed for these)
    assert _name_overlap("Alaves", "Deportivo Alavés") >= 0.9
    assert _name_overlap("FC Koln", "1. FC Köln") >= 0.9
    assert _name_overlap("Malaga", "Málaga CF") >= 0.9
