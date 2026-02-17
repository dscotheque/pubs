"""Shared FastAPI dependencies for the pubs API."""

from __future__ import annotations

import functools
from pathlib import Path

from labpubs.core import LabPubs


@functools.lru_cache(maxsize=1)
def get_engine() -> LabPubs:
    """Return a cached LabPubs engine instance.

    Returns:
        Configured LabPubs engine backed by the repo's SQLite database.

    Raises:
        FileNotFoundError: If labpubs.yaml is missing.
    """
    config_path = Path("labpubs.yaml")
    return LabPubs(str(config_path))
