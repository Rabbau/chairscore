from app.api import admin, competitions, matches, search, teams

routers = [
    competitions.router,
    matches.router,
    teams.router,
    search.router,
    admin.router,
]

__all__ = ["routers"]
