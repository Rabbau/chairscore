from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import CompetitionRef, TeamOut


class SearchOut(BaseModel):
    teams: list[TeamOut] = []
    competitions: list[CompetitionRef] = []
