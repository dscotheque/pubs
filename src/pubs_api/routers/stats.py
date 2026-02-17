"""Router for summary statistics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from labpubs.core import LabPubs

from pubs_api.dependencies import get_engine

router = APIRouter(tags=["stats"])


@router.get("/stats")
def get_stats(engine: LabPubs = Depends(get_engine)) -> dict[str, Any]:
    """Return summary statistics for the lab's publication database.

    Args:
        engine: Injected LabPubs engine.

    Returns:
        Dictionary with counts of researchers, total works,
        funders, and verification stats.
    """
    researchers = engine.get_researchers()
    works = engine.get_works()
    funders = engine.get_funders()
    verification = engine.get_verification_stats()

    return {
        "total_researchers": len(researchers),
        "total_works": len(works),
        "total_funders": len(funders),
        "verification": verification,
    }
