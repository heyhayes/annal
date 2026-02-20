"""Annal memory dashboard -- web UI for browsing and managing agent memories."""

from __future__ import annotations

from pathlib import Path
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from annal.dashboard.routes import create_routes

PACKAGE_DIR = Path(__file__).parent


def create_dashboard_app(pool, config) -> Starlette:
    """Create the dashboard Starlette application."""
    routes = create_routes(pool, config)
    routes.append(
        Mount("/static", app=StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
    )
    return Starlette(routes=routes)
