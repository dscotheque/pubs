"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from pubs_api.app import create_app
from pubs_api.dependencies import get_engine


@pytest.fixture()
def mock_engine() -> MagicMock:
    """Create a mock LabPubs engine."""
    return MagicMock()


@pytest.fixture()
def client(mock_engine: MagicMock) -> TestClient:
    """Create a test client with mocked engine dependency."""
    application = create_app()
    application.dependency_overrides[get_engine] = lambda: mock_engine
    return TestClient(application)
