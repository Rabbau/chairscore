"""Mapping between football-data.org competition codes and API-Football league ids.

API-Football league ids are stable. Extend as more competitions get tracked.
"""

from __future__ import annotations

# football-data.org code -> API-Football league id
CODE_TO_API_FOOTBALL_LEAGUE: dict[str, int] = {
    "PL": 39,     # Premier League (England)
    "PD": 140,    # La Liga (Spain)
    "BL1": 78,    # Bundesliga (Germany)
    "SA": 135,    # Serie A (Italy)
    "FL1": 61,    # Ligue 1 (France)
    "DED": 88,    # Eredivisie (Netherlands)
    "PPL": 94,    # Primeira Liga (Portugal)
    "ELC": 40,    # Championship (England)
    "CL": 2,      # UEFA Champions League
    "EL": 3,      # UEFA Europa League
    "BSA": 71,    # Brasileirão Série A
    "CLI": 13,    # Copa Libertadores
    "WC": 1,      # FIFA World Cup
    "EC": 4,      # UEFA European Championship
}

API_FOOTBALL_LEAGUE_TO_CODE: dict[int, str] = {v: k for k, v in CODE_TO_API_FOOTBALL_LEAGUE.items()}


def to_league_id(code: str) -> int:
    try:
        return CODE_TO_API_FOOTBALL_LEAGUE[code.upper()]
    except KeyError as exc:
        raise KeyError(
            f"no API-Football league id mapped for competition code '{code}' "
            f"— add it to app/providers/leagues.py"
        ) from exc
