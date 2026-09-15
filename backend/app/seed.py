"""Seed the competitions table with football-data.org's free-tier list.

Lets the API and UI render before a token is configured or a sync has run.
Real syncs fill in current matchday, season dates, emblems, etc.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Competition

log = logging.getLogger("chairscore.seed")

# (provider_id, code, name, type, area)
FREE_TIER_COMPETITIONS: list[tuple[int, str, str, str, str]] = [
    (2001, "CL", "UEFA Champions League", "CUP", "Europe"),
    (2002, "BL1", "Bundesliga", "LEAGUE", "Germany"),
    (2003, "DED", "Eredivisie", "LEAGUE", "Netherlands"),
    (2013, "BSA", "Campeonato Brasileiro Série A", "LEAGUE", "Brazil"),
    (2014, "PD", "Primera División", "LEAGUE", "Spain"),
    (2015, "FL1", "Ligue 1", "LEAGUE", "France"),
    (2016, "ELC", "Championship", "LEAGUE", "England"),
    (2017, "PPL", "Primeira Liga", "LEAGUE", "Portugal"),
    (2019, "SA", "Serie A", "LEAGUE", "Italy"),
    (2021, "PL", "Premier League", "LEAGUE", "England"),
    (2000, "WC", "FIFA World Cup", "CUP", "World"),
    (2018, "EC", "European Championship", "CUP", "Europe"),
    (2152, "CLI", "Copa Libertadores", "CUP", "South America"),
]

EMBLEM = "https://crests.football-data.org/{code}.png"


def seed_competitions() -> int:
    created = 0
    with SessionLocal() as db:
        for provider_id, code, name, ctype, area in FREE_TIER_COMPETITIONS:
            exists = db.scalar(select(Competition).where(Competition.code == code))
            if exists:
                continue
            db.add(
                Competition(
                    provider_id=provider_id,
                    code=code,
                    name=name,
                    type=ctype,
                    area_name=area,
                    emblem_url=EMBLEM.format(code=code),
                )
            )
            created += 1
        db.commit()
    if created:
        log.info("seeded %d competitions", created)
    return created
