"""FastAPI application factory for the lab publications API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from pubs_api.routers import exports, researchers, stats, works


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance with all routers mounted.
    """
    application = FastAPI(
        title="Lab Publications API",
        description="REST API for querying DScotheque lab publications",
        version="0.1.0",
        default_response_class=ORJSONResponse,
    )

    application.include_router(researchers.router)
    application.include_router(works.router)
    application.include_router(exports.router)
    application.include_router(stats.router)

    return application


app = create_app()
