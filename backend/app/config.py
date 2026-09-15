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
    fpl_max_matches_per_run: int = 12
    fpl_window_days: int = 14

    # Depth source — Football-Data.co.uk (free CSV, no key: shots, corners,
    # cards, and team xG for every tracked league, not just one)
    fdcouk_enabled: bool = True
    fdcouk_base_url: str = "https://football-data.co.uk/mmz4281"
    fdcouk_min_request_interval: float = 1.0
    # One CSV per competition-season covers every match in it, so this is a
    # budget on DB rows touched per run, not on network calls.
    fdcouk_max_matches_per_run: int = 60
    fdcouk_window_days: int = 14

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
    # Match sync window, relative to today (days).
    match_window_past_days: int = 3
    match_window_future_days: int = 10

    @property
    def tracked_competition_codes(self) -> list[str]:
        return [c.strip().upper() for c in self.tracked_competitions.split(",") if c.strip()]

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
