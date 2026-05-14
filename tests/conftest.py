"""Shared pytest fixtures."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_profile_path() -> Path:
    return FIXTURES / "master_profile.sample.json"


@pytest.fixture
def sample_profile_dict(sample_profile_path: Path) -> dict[str, Any]:
    return json.loads(sample_profile_path.read_text())


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "state.sqlite"


@pytest.fixture
def tmp_db(tmp_db_path: Path) -> sqlite3.Connection:
    from agent.db.store import init_db

    conn = init_db(tmp_db_path)
    yield conn
    conn.close()
