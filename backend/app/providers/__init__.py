"""Data-source providers.

Every provider maps a third-party API onto the normalized dataclasses in
``app.providers.base``. The ingestion layer only ever sees normalized objects,
so swapping or adding a provider never touches the DB code.

* ``get_provider()``       — the breadth source (football-data.org): competitions,
  standings, fixtures, scorers, squads across all tracked competitions.
* ``get_depth_provider()`` — the optional depth source (API-Football): match
  events, per-team statistics and player ratings for a subset of competitions.
* ``get_fpl_provider()``   — the optional depth source for the current Premier
  League season (Fantasy Premier League: per-player goals/assists/bonus/BPS/xG).
* ``get_fdcouk_provider()`` — the optional depth source for team-level match
  stats (shots/corners/cards/xG) across every tracked competition (Football-Data.co.uk).
"""

from __future__ import annotations

from app.config import settings
from app.providers.api_football import ApiFootballProvider
from app.providers.base import BaseProvider
from app.providers.football_data import FootballDataProvider
from app.providers.football_data_co_uk import FootballDataCoUkProvider
from app.providers.fpl import FplProvider


def get_provider() -> BaseProvider:
    """The breadth provider (football-data.org)."""
    return FootballDataProvider(
        token=settings.football_data_api_token,
        base_url=settings.football_data_base_url,
        min_request_interval=settings.football_data_min_request_interval,
    )


def get_depth_provider() -> ApiFootballProvider | None:
    """The depth provider (API-Football), or None if not configured/enabled."""
    if not settings.depth_enabled or not settings.api_football_key:
        return None
    return ApiFootballProvider(
        key=settings.api_football_key,
        base_url=settings.api_football_base_url,
        min_request_interval=settings.api_football_min_request_interval,
        daily_limit=settings.api_football_daily_limit,
    )


def get_fpl_provider() -> FplProvider | None:
    """The FPL depth provider (current PL season), or None if disabled."""
    if not settings.fpl_enabled:
        return None
    return FplProvider(
        base_url=settings.fpl_base_url,
        min_request_interval=settings.fpl_min_request_interval,
    )


def get_fdcouk_provider() -> FootballDataCoUkProvider | None:
    """The Football-Data.co.uk depth provider, or None if disabled."""
    if not settings.fdcouk_enabled:
        return None
    return FootballDataCoUkProvider(
        base_url=settings.fdcouk_base_url,
        min_request_interval=settings.fdcouk_min_request_interval,
    )


__all__ = [
    "BaseProvider",
    "FootballDataProvider",
    "ApiFootballProvider",
    "FplProvider",
    "FootballDataCoUkProvider",
    "get_provider",
    "get_depth_provider",
    "get_fpl_provider",
    "get_fdcouk_provider",
]
