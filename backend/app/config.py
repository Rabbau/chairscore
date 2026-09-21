"""Application settings, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Breadth source — football-data.org
    football_data_api_token: str = ""
    football_data_base_url: str = "https://api.football-data.org/v4"
    football_data_min_request_interval: float = 6.5
    tracked_competitions: str = "PL,PD,BL1,SA,FL1"

    # Depth source — API-Football (match events, statistics, player ratings)
    depth_enabled: bool = True
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    api_football_min_request_interval: float = 6.5
    api_football_daily_limit: int = 100
    # Competitions to enrich with depth data (subset of tracked_competitions).
    depth_competitions: str = "PL"
    # Per depth-sync run, at most this many fixtures get enriched. Each costs
    # ~4 API-Football calls (7 the first time, incl. fixture-id resolution), so
    # keep this well under the daily budget.
    depth_max_matches_per_run: int = 6
    # Only enrich matches finished within this many days.
    depth_window_days: int = 6

    # Depth source — Fantasy Premier League (free, official, current PL season)
    fpl_enabled: bool = True
    fpl_base_url: str = "https://fantasy.premierleague.com/api"
    fpl_min_request_interval: float = 1.2
    # xG / xA cost one /element-summary call per player; turn off to stay at
    # ~1 call per gameweek.
    fpl_fetch_player_xg: bool = True
    fpl_competition: str = "PL"
    # Per run, at most this many matches (newest first) of the current season
    # that don't have FPL data yet — so the backlog fills in over a few runs.
    fpl_max_matches_per_run: int = 12

    # Depth source — Football-Data.co.uk (free CSV, no key: shots, corners,
    # cards, and team xG for every tracked league, not just one)
    fdcouk_enabled: bool = True
    fdcouk_base_url: str = "https://football-data.co.uk/mmz4281"
    fdcouk_min_request_interval: float = 1.0
    # One CSV per competition-season covers every match in it, so this is a
    # budget on DB rows touched per run, not on network calls.
    fdcouk_max_matches_per_run: int = 60

    # Breadth + depth source for the UEFA club competitions — official uefa.com
    # backends (no key). football-data.org's free plan has the Champions League
    # but not the Europa League, so UEFA owns both: fixtures, tables, scorers,
    # lineups and the event feed that per-match team stats are derived from.
    uefa_enabled: bool = True
    uefa_competitions: str = "CL,EL"
    uefa_matches_url: str = "https://match.uefa.com/v5"
    uefa_standings_url: str = "https://standings.uefa.com/v1"
    uefa_stats_url: str = "https://compstats.uefa.com/v1"
    uefa_min_request_interval: float = 0.4
    # Qualifying rounds (July-August, dozens of small clubs) are skipped by
    # default; the league phase and knockouts are what people follow.
    uefa_include_qualifying: bool = False
    # Depth (lineups + event feed) costs ~4 requests per match.
    uefa_max_matches_per_run: int = 40

    # Database
    database_url: str = "sqlite:///./chairscore.db"

    # App
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    enable_scheduler: bool = True
    sync_on_startup: bool = False
    # Run `alembic upgrade head` on startup. Turn off in prod if migrations run
    # as a separate deploy step.
    run_migrations_on_startup: bool = True
    admin_token: str = "changeme"

    # Scheduler cadence
    sync_reference_hours: int = 24
    sync_standings_hours: int = 6
    sync_matches_minutes: int = 15
    sync_depth_hours: int = 12
    sync_fpl_hours: int = 6
    sync_fdcouk_hours: int = 6
    sync_uefa_minutes: int = 30
    # Match sync window, relative to today (days).
    match_window_past_days: int = 3
    match_window_future_days: int = 10

    @property
    def tracked_competition_codes(self) -> list[str]:
        """Competitions synced from football-data.org. A code owned by UEFA is
        dropped here so the two sources never write the same competition."""
        owned = set(self.uefa_competition_codes)
        return [
            c.strip().upper()
            for c in self.tracked_competitions.split(",")
            if c.strip() and c.strip().upper() not in owned
        ]

    @property
    def uefa_competition_codes(self) -> list[str]:
        if not self.uefa_enabled:
            return []
        return [c.strip().upper() for c in self.uefa_competitions.split(",") if c.strip()]

    @property
    def served_competition_codes(self) -> list[str]:
        """Every competition the site actually has data for."""
        return self.tracked_competition_codes + self.uefa_competition_codes

    @property
    def depth_competition_codes(self) -> list[str]:
        return [c.strip().upper() for c in self.depth_competitions.split(",") if c.strip()]

    @property
    def fpl_competition_code(self) -> str:
        return self.fpl_competition.strip().upper()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
