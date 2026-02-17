"""Router for export endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from labpubs.core import LabPubs

from pubs_api.dependencies import get_engine

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/bibtex", response_class=PlainTextResponse)
def export_bibtex(
    researcher: str | None = Query(None, description="Filter by researcher"),
    year: int | None = Query(None, description="Filter by year"),
    engine: LabPubs = Depends(get_engine),
) -> str:
    """Export publications as BibTeX.

    Args:
        researcher: Optional researcher name filter.
        year: Optional year filter.
        engine: Injected LabPubs engine.

    Returns:
        BibTeX-formatted string of all matching publications.
    """
    return engine.export_bibtex(researcher=researcher, year=year)


@router.get("/json")
def export_json(
    researcher: str | None = Query(None, description="Filter by researcher"),
    year: int | None = Query(None, description="Filter by year"),
    engine: LabPubs = Depends(get_engine),
) -> list[dict[str, Any]]:
    """Export publications as JSON.

    Args:
        researcher: Optional researcher name filter.
        year: Optional year filter.
        engine: Injected LabPubs engine.

    Returns:
        List of publication records as JSON.
    """
    return engine.export_json(researcher=researcher, year=year)


@router.get("/csl-json")
def export_csl_json(
    researcher: str | None = Query(None, description="Filter by researcher"),
    year: int | None = Query(None, description="Filter by year"),
    engine: LabPubs = Depends(get_engine),
) -> list[dict[str, Any]]:
    """Export publications as CSL-JSON (for citation managers).

    Args:
        researcher: Optional researcher name filter.
        year: Optional year filter.
        engine: Injected LabPubs engine.

    Returns:
        List of CSL-JSON records.
    """
    return engine.export_csl_json(researcher=researcher, year=year)
