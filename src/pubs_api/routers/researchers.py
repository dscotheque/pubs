"""Router for researcher endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from labpubs.core import LabPubs

from pubs_api.dependencies import get_engine

router = APIRouter(prefix="/researchers", tags=["researchers"])


@router.get("")
def list_researchers(
    engine: LabPubs = Depends(get_engine),
) -> list[dict[str, Any]]:
    """List all tracked lab members with their identifiers.

    Returns:
        List of researcher records with name, ORCID, OpenAlex ID,
        and Semantic Scholar ID.
    """
    researchers = engine.get_researchers()
    return [r.model_dump(exclude_none=True) for r in researchers]
