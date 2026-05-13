# LinkedIn Auto-Post Agent — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Phase 1 MVP that, once a day at 08:00 ET on GitHub Actions, generates a LinkedIn post draft from Anuj's profile (rotating across project / concept / tip) and emails the formatted draft to Anuj for him to manually copy-paste to LinkedIn at 11:00 ET.

**Architecture:** Python 3.11 package run by a GitHub Actions cron. Source-of-truth for content is `master_profile.json` (kept local; loaded into GH Actions via a base64 Secret). State lives in `db/state.sqlite` committed back to the repo by the workflow. Claude (Anthropic SDK) writes the caption + hashtags; Unsplash provides the image. Gmail SMTP (via `smtplib`) sends the draft email. No Buffer, no Cloudflare Worker, no approval click handler in this phase — Anuj reviews the email and posts manually.

**Tech Stack:**
- Python 3.11
- `anthropic` SDK (Claude Sonnet 4.6 for captions, Haiku 4.5 for hashtags)
- `httpx` for Unsplash
- `tenacity` for retries
- `pydantic` for profile/config validation
- `python-dotenv` for local dev
- Stdlib: `sqlite3`, `smtplib`, `email.message`, `argparse`, `uuid`, `datetime`, `pathlib`, `json`, `logging`
- `pytest`, `respx`, `pytest-mock`, `freezegun` for testing
- `ruff` (lint + format), `mypy` (types)
- GitHub Actions for cron

**Scope boundaries (Phase 1 only):**
- 3 post types: `project`, `concept`, `tip`. Other 4 types deferred to Phase 3.
- 3-day rotation Mon/Tue/Wed/Thu/Fri/Sat/Sun → project/concept/tip/project/concept/tip/project (cycle).
- Profile-only sources. No arXiv / HN / Reddit / GitHub / Trends in Phase 1.
- Email delivery only. No Buffer API call. No approval link. No Cloudflare Worker. The email contains the full caption + hashtags + image URL, ready for manual copy-paste.
- No DST handling beyond a single UTC cron (close enough; revisit Phase 2).

---

## File Structure

Files created in this plan (all paths relative to repo root):

```
linkedin-agent/
├── pyproject.toml                       # ruff, mypy, pytest config; package metadata
├── requirements.txt                     # pinned runtime deps
├── requirements-dev.txt                 # test/lint deps
├── .env.example                         # template for local dev
├── README.md                            # setup + run instructions (this phase only)
├── Makefile                             # convenience: install, test, lint, dry-run
├── master_profile.example.json          # already exists; left untouched
├── master_profile.json                  # already exists; gitignored
├── db/
│   └── state.sqlite                     # created by first run; committed by workflow
├── src/agent/
│   ├── __init__.py                      # package marker, version
│   ├── __main__.py                      # `python -m agent` entrypoint dispatcher
│   ├── config.py                        # env loading + frozen Settings model
│   ├── logging_setup.py                 # stdlib logging config
│   ├── profile_model.py                 # pydantic model of master_profile.json
│   ├── rotation.py                      # 3-day rotation + sub-key selection
│   ├── draft.py                         # entrypoint: gather → generate → save → email
│   ├── sources/
│   │   ├── __init__.py
│   │   └── profile.py                   # build source dict from profile + post_type
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── prompts.py                   # prompt templates (pure strings)
│   │   ├── caption.py                   # Claude → caption text
│   │   ├── hashtags.py                  # Claude (Haiku) → hashtag list
│   │   └── image.py                     # Unsplash search → (url, credit)
│   ├── delivery/
│   │   ├── __init__.py
│   │   └── email.py                     # Gmail SMTP send draft
│   └── db/
│       ├── __init__.py
│       ├── schema.sql                   # CREATE TABLE statements
│       └── store.py                     # CRUD wrappers (no ORM)
├── tests/
│   ├── __init__.py
│   ├── conftest.py                      # shared fixtures (tmp DB, sample profile)
│   ├── fixtures/
│   │   ├── master_profile.sample.json   # sanitized profile for tests
│   │   ├── claude_caption.txt           # captured Claude caption sample
│   │   ├── claude_hashtags.json         # captured Claude hashtag sample
│   │   └── unsplash_search.json         # captured Unsplash response
│   └── unit/
│       ├── test_config.py
│       ├── test_profile_model.py
│       ├── test_rotation.py
│       ├── test_sources_profile.py
│       ├── test_generators_prompts.py
│       ├── test_generators_caption.py
│       ├── test_generators_hashtags.py
│       ├── test_generators_image.py
│       ├── test_delivery_email.py
│       ├── test_db_store.py
│       └── test_draft_pipeline.py
└── .github/workflows/
    ├── test.yml                         # lint + types + unit tests on push
    └── draft.yml                        # cron 12:00 UTC daily
```

Each `src/agent/*` module has one responsibility and is unit-testable with mocks at the HTTP boundary. `draft.py` is the only module that coordinates across layers.

---

## Task 1: Repository scaffolding & tooling

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.env.example`
- Create: `Makefile`
- Create: `README.md`
- Create: `src/agent/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1.1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "linkedin-agent"
version = "0.1.0"
description = "LinkedIn auto-post agent — Phase 1 MVP"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
exclude = ["tests/fixtures/"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --strict-markers"
```

- [ ] **Step 1.2: Create `requirements.txt`**

```
anthropic==0.40.0
httpx==0.27.2
tenacity==9.0.0
pydantic==2.9.2
python-dotenv==1.0.1
```

- [ ] **Step 1.3: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest==8.3.3
pytest-mock==3.14.0
respx==0.21.1
freezegun==1.5.1
ruff==0.7.4
mypy==1.13.0
types-requests==2.32.0.20241016
```

- [ ] **Step 1.4: Create `.env.example`**

```
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Unsplash (https://unsplash.com/developers)
UNSPLASH_ACCESS_KEY=

# Gmail SMTP (use a Gmail app password, NOT your main password)
GMAIL_USERNAME=99anujbansal@gmail.com
GMAIL_APP_PASSWORD=
GMAIL_RECIPIENT=99anujbansal@gmail.com

# Profile file path (local dev). In GH Actions, profile is decoded from secret.
PROFILE_PATH=./master_profile.json

# DB
DB_PATH=./db/state.sqlite

# Logging
LOG_LEVEL=INFO
```

- [ ] **Step 1.5: Create `Makefile`**

```makefile
.PHONY: install test lint type dry-run

install:
	pip install -r requirements-dev.txt

test:
	pytest

lint:
	ruff check src tests
	ruff format --check src tests

type:
	mypy src

dry-run:
	python -m agent draft --dry-run
```

- [ ] **Step 1.6: Create `README.md` (minimal Phase 1 instructions)**

```markdown
# LinkedIn Auto-Post Agent — Phase 1

Daily LinkedIn draft emailed to you for manual posting. See
`docs/superpowers/specs/2026-05-13-linkedin-auto-post-agent-design.md`
for the full design.

## Setup (local dev)

```
make install
cp .env.example .env
# fill in ANTHROPIC_API_KEY, UNSPLASH_ACCESS_KEY, GMAIL_APP_PASSWORD
python -m agent draft --dry-run
```

## Setup (GitHub Actions)

1. Create a private repo and push this code.
2. Add these Repository Secrets:
   - `ANTHROPIC_API_KEY`
   - `UNSPLASH_ACCESS_KEY`
   - `GMAIL_USERNAME`
   - `GMAIL_APP_PASSWORD`
   - `GMAIL_RECIPIENT`
   - `PROFILE_B64` — base64 of `master_profile.json`
     (`base64 -i master_profile.json | pbcopy`)
3. Cron runs daily at 12:00 UTC (≈ 08:00 ET). You receive an email
   draft and post it manually at 11:00 ET.

## CLI

```
python -m agent draft --dry-run         # generate, print, no email or commit
python -m agent draft --post-type=tip   # force a post type
python -m agent draft --force           # ignore "already drafted today"
python -m agent db list-pending         # show pending drafts
```
```

- [ ] **Step 1.7: Create empty package markers**

`src/agent/__init__.py`:

```python
"""LinkedIn auto-post agent."""

__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

- [ ] **Step 1.8: Verify install works**

```bash
make install
```

Expected: pip installs all deps without errors.

- [ ] **Step 1.9: Commit**

```bash
git add pyproject.toml requirements.txt requirements-dev.txt .env.example Makefile README.md src/agent/__init__.py tests/__init__.py
git commit -m "feat(scaffold): project layout, deps, and dev tooling"
```

---

## Task 2: Config module

**Files:**
- Create: `src/agent/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 2.1: Write the failing test**

`tests/unit/test_config.py`:

```python
import os
from pathlib import Path

import pytest

from agent.config import Settings, load_settings


def _full_env() -> dict[str, str]:
    return {
        "ANTHROPIC_API_KEY": "sk-test",
        "UNSPLASH_ACCESS_KEY": "u-test",
        "GMAIL_USERNAME": "a@b.com",
        "GMAIL_APP_PASSWORD": "app-pwd",
        "GMAIL_RECIPIENT": "a@b.com",
        "PROFILE_PATH": "./master_profile.json",
        "DB_PATH": "./db/state.sqlite",
        "LOG_LEVEL": "INFO",
    }


def test_load_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _full_env().items():
        monkeypatch.setenv(k, v)
    s = load_settings()
    assert isinstance(s, Settings)
    assert s.anthropic_api_key == "sk-test"
    assert s.gmail_recipient == "a@b.com"
    assert s.profile_path == Path("./master_profile.json")
    assert s.db_path == Path("./db/state.sqlite")
    assert s.log_level == "INFO"


def test_missing_required_var_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _full_env()
    env.pop("ANTHROPIC_API_KEY")
    for k in list(os.environ):
        if k.startswith(("ANTHROPIC_", "UNSPLASH_", "GMAIL_", "PROFILE_", "DB_", "LOG_")):
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        load_settings()


def test_log_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _full_env()
    env.pop("LOG_LEVEL")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    s = load_settings()
    assert s.log_level == "INFO"
```

- [ ] **Step 2.2: Run test to verify failure**

```bash
pytest tests/unit/test_config.py -v
```

Expected: ImportError / ModuleNotFoundError on `agent.config`.

- [ ] **Step 2.3: Implement `src/agent/config.py`**

```python
"""Environment-based configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Immutable application settings loaded from environment."""

    model_config = {"frozen": True}

    anthropic_api_key: str = Field(min_length=1)
    unsplash_access_key: str = Field(min_length=1)
    gmail_username: str = Field(min_length=1)
    gmail_app_password: str = Field(min_length=1)
    gmail_recipient: str = Field(min_length=1)
    profile_path: Path
    db_path: Path
    log_level: str = "INFO"


_REQUIRED = (
    "ANTHROPIC_API_KEY",
    "UNSPLASH_ACCESS_KEY",
    "GMAIL_USERNAME",
    "GMAIL_APP_PASSWORD",
    "GMAIL_RECIPIENT",
    "PROFILE_PATH",
    "DB_PATH",
)


def load_settings() -> Settings:
    """Load settings from environment (and .env if present)."""
    load_dotenv(override=False)
    missing = [v for v in _REQUIRED if not os.environ.get(v)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    return Settings(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        unsplash_access_key=os.environ["UNSPLASH_ACCESS_KEY"],
        gmail_username=os.environ["GMAIL_USERNAME"],
        gmail_app_password=os.environ["GMAIL_APP_PASSWORD"],
        gmail_recipient=os.environ["GMAIL_RECIPIENT"],
        profile_path=Path(os.environ["PROFILE_PATH"]),
        db_path=Path(os.environ["DB_PATH"]),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
```

- [ ] **Step 2.4: Run tests to verify pass**

```bash
pytest tests/unit/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 2.5: Commit**

```bash
git add src/agent/config.py tests/unit/test_config.py
git commit -m "feat(config): env-based Settings loader with validation"
```

---

## Task 3: Logging setup

**Files:**
- Create: `src/agent/logging_setup.py`

- [ ] **Step 3.1: Implement logging setup**

```python
"""Stdlib logging configuration."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with a single stderr handler.

    Idempotent: calling twice doesn't add duplicate handlers.
    """
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
```

- [ ] **Step 3.2: Sanity check via REPL**

```bash
python -c "from agent.logging_setup import setup_logging; setup_logging(); import logging; logging.info('ok')"
```

Expected: one line like `... INFO root: ok` on stderr.

- [ ] **Step 3.3: Commit**

```bash
git add src/agent/logging_setup.py
git commit -m "feat(logging): stdlib logging setup helper"
```

---

## Task 4: Profile model

**Files:**
- Create: `src/agent/profile_model.py`
- Create: `tests/fixtures/master_profile.sample.json`
- Create: `tests/conftest.py`
- Test: `tests/unit/test_profile_model.py`

- [ ] **Step 4.1: Create test fixture profile**

`tests/fixtures/master_profile.sample.json` — copy of `master_profile.example.json` from the repo root (sanitized version). Keep the same shape but fake values:

```json
{
  "contact": {
    "name": "Test User",
    "tagline": "Open to work",
    "phone": "(000) 000-0000",
    "phone_tel": "+10000000000",
    "email": "test@example.com",
    "linkedin_label": "LinkedIn",
    "linkedin_url": "https://www.linkedin.com/in/test/",
    "github_label": "GitHub",
    "github_url": "https://github.com/test",
    "portfolio_label": "Portfolio",
    "portfolio_url": "https://example.com"
  },
  "role_targets": ["Data Analyst", "Data Scientist"],
  "constraints": {
    "work_authorization": "OPT",
    "needs_sponsorship_now": false,
    "needs_sponsorship_future": true,
    "visa_status": "OPT",
    "opt_valid_through_years": 3,
    "eligible_countries": ["United States"],
    "eligible_locations": ["Remote-US"],
    "open_to_relocation": true,
    "current_location": "Boston, MA",
    "preferred_locations": ["Anywhere"],
    "earliest_start": "Immediately",
    "experience_years": 4,
    "highest_degree_in_progress": "MS Data Science",
    "deal_breakers": []
  },
  "summaries": {
    "business_analyst": "Test summary.",
    "data_analyst": "Test summary.",
    "data_scientist": "Test summary."
  },
  "skills": {
    "programming": ["Python", "SQL"],
    "machine_learning": ["XGBoost"],
    "deep_learning": ["PyTorch"],
    "interpretability": ["SHAP"],
    "visualization_bi": ["Tableau"],
    "databases_cloud": ["MySQL"],
    "deployment_engineering": ["FastAPI"],
    "analytics_techniques": ["A/B Testing"],
    "business_strategy": ["GTM Strategy"],
    "financial_planning": ["Forecasting"],
    "tools_workflow": ["Jupyter"]
  },
  "experience": [
    {
      "id": "co_a",
      "company": "Co A",
      "location": "Boston",
      "title": "Analyst",
      "start": "Jan 2022",
      "end": "Dec 2023",
      "bullets": {
        "business_analyst": ["Drove $1M outcome."],
        "data_analyst": ["Built dashboards reducing latency 50%."],
        "data_scientist": ["Built models with 90% accuracy."]
      }
    }
  ],
  "projects": [
    {
      "id": "p1",
      "title": "Project One",
      "subtitle": "Demo",
      "tech": ["Python", "PyTorch"],
      "github": "https://github.com/test/p1",
      "domain": ["ml"],
      "metrics": {"accuracy": "95%"},
      "framings": {
        "data_scientist": "Built a deep learning thing with 95% accuracy.",
        "data_analyst": "Built a model.",
        "business_analyst": "Built something."
      }
    },
    {
      "id": "p2",
      "title": "Project Two",
      "subtitle": null,
      "tech": ["SQL"],
      "github": "https://github.com/test/p2",
      "domain": ["analytics"],
      "metrics": {},
      "framings": {
        "data_scientist": "Did SQL analysis.",
        "data_analyst": "Did SQL analysis.",
        "business_analyst": "Did SQL analysis."
      }
    }
  ],
  "education": [
    {
      "school": "Test U",
      "degree": "MS Data Science",
      "gpa": "3.6",
      "start": "Sep 2024",
      "end": "May 2026",
      "coursework": ["ML", "DL"]
    }
  ],
  "achievements": ["Won a competition."]
}
```

- [ ] **Step 4.2: Create conftest with shared fixtures**

`tests/conftest.py`:

```python
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
```

- [ ] **Step 4.3: Write the failing test**

`tests/unit/test_profile_model.py`:

```python
from pathlib import Path

import pytest

from agent.profile_model import Profile, load_profile


def test_load_profile_parses_sample(sample_profile_path: Path) -> None:
    profile = load_profile(sample_profile_path)
    assert isinstance(profile, Profile)
    assert profile.contact.name == "Test User"
    assert "Data Analyst" in profile.role_targets
    assert len(profile.projects) == 2
    assert profile.projects[0].framings["data_scientist"].startswith("Built")


def test_load_profile_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path / "missing.json")


def test_load_profile_malformed_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ValueError):
        load_profile(bad)
```

- [ ] **Step 4.4: Run test to verify failure**

```bash
pytest tests/unit/test_profile_model.py -v
```

Expected: ImportError on `agent.profile_model`.

- [ ] **Step 4.5: Implement `src/agent/profile_model.py`**

```python
"""Pydantic model of master_profile.json."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class Contact(BaseModel):
    name: str
    tagline: str = ""
    phone: str = ""
    phone_tel: str = ""
    email: str
    linkedin_label: str = "LinkedIn"
    linkedin_url: str = ""
    github_label: str = "GitHub"
    github_url: str = ""
    portfolio_label: str = "Portfolio"
    portfolio_url: str = ""


class ExperienceItem(BaseModel):
    id: str
    company: str
    location: str = ""
    title: str
    start: str
    end: str
    bullets: dict[str, list[str]]


class ProjectItem(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    tech: list[str] = []
    github: str = ""
    domain: list[str] = []
    metrics: dict[str, str | float | int] = {}
    framings: dict[str, str]


class EducationItem(BaseModel):
    school: str
    degree: str
    gpa: str | None = None
    start: str
    end: str
    coursework: list[str] = []


class Profile(BaseModel):
    contact: Contact
    role_targets: list[str]
    constraints: dict
    summaries: dict[str, str]
    skills: dict[str, list[str]]
    experience: list[ExperienceItem]
    projects: list[ProjectItem]
    education: list[EducationItem]
    achievements: list[str] = []


def load_profile(path: Path) -> Profile:
    """Load and validate the profile JSON at `path`."""
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed profile JSON: {e}") from e
    return Profile.model_validate(data)
```

- [ ] **Step 4.6: Run tests to verify pass**

```bash
pytest tests/unit/test_profile_model.py -v
```

Expected: 3 passed.

- [ ] **Step 4.7: Commit**

```bash
git add src/agent/profile_model.py tests/conftest.py tests/fixtures/master_profile.sample.json tests/unit/test_profile_model.py
git commit -m "feat(profile): pydantic model + loader for master profile JSON"
```

---

## Task 5: SQLite store

**Files:**
- Create: `src/agent/db/__init__.py`
- Create: `src/agent/db/schema.sql`
- Create: `src/agent/db/store.py`
- Test: `tests/unit/test_db_store.py`

- [ ] **Step 5.1: Create empty package marker**

`src/agent/db/__init__.py`: empty.

- [ ] **Step 5.2: Create schema**

`src/agent/db/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS drafts (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    post_type       TEXT NOT NULL,
    source_ref      TEXT,
    caption         TEXT NOT NULL,
    hashtags        TEXT NOT NULL,
    image_url       TEXT,
    image_credit    TEXT,
    status          TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    approved_at     TEXT,
    posted_at       TEXT,
    buffer_post_id  TEXT,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS rotation_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_day        TEXT,
    project_index   INTEGER DEFAULT 0,
    skill_index     INTEGER DEFAULT 0,
    exp_index       INTEGER DEFAULT 0
);

INSERT OR IGNORE INTO rotation_state (id, last_day, project_index, skill_index, exp_index)
    VALUES (1, NULL, 0, 0, 0);

CREATE TABLE IF NOT EXISTS post_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id        TEXT REFERENCES drafts(id),
    post_type       TEXT,
    source_ref      TEXT,
    posted_at       TEXT,
    linkedin_url    TEXT
);
```

- [ ] **Step 5.3: Write the failing test**

`tests/unit/test_db_store.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from freezegun import freeze_time

from agent.db.store import (
    Draft,
    RotationState,
    expire_stale_drafts,
    get_draft,
    get_rotation_state,
    init_db,
    insert_draft,
    list_pending,
    update_draft_status,
    update_rotation_state,
)


def test_init_db_creates_tables(tmp_db_path: Path) -> None:
    conn = init_db(tmp_db_path)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    names = {row[0] for row in cur.fetchall()}
    assert {"drafts", "rotation_state", "post_history"}.issubset(names)
    # rotation_state seeded
    row = conn.execute("SELECT id, project_index FROM rotation_state").fetchone()
    assert row == (1, 0)
    conn.close()


def test_insert_and_get_draft(tmp_db: sqlite3.Connection) -> None:
    with freeze_time("2026-05-13T12:00:00Z"):
        draft = Draft(
            id="d1",
            post_type="project",
            source_ref="project:p1",
            caption="hi",
            hashtags="#a #b",
            image_url="http://img",
            image_credit="cred",
        )
        insert_draft(tmp_db, draft)

    got = get_draft(tmp_db, "d1")
    assert got is not None
    assert got.id == "d1"
    assert got.caption == "hi"
    assert got.status == "pending"
    assert got.created_at == "2026-05-13T12:00:00+00:00"
    assert got.expires_at == "2026-05-14T12:00:00+00:00"


def test_update_draft_status(tmp_db: sqlite3.Connection) -> None:
    insert_draft(
        tmp_db,
        Draft(
            id="d2",
            post_type="tip",
            source_ref=None,
            caption="x",
            hashtags="#x",
            image_url=None,
            image_credit=None,
        ),
    )
    update_draft_status(tmp_db, "d2", "rejected")
    got = get_draft(tmp_db, "d2")
    assert got is not None
    assert got.status == "rejected"


def test_list_pending_excludes_others(tmp_db: sqlite3.Connection) -> None:
    insert_draft(tmp_db, Draft(id="a", post_type="tip", caption="a", hashtags=""))
    insert_draft(tmp_db, Draft(id="b", post_type="tip", caption="b", hashtags=""))
    update_draft_status(tmp_db, "b", "rejected")
    pending = list_pending(tmp_db)
    assert [d.id for d in pending] == ["a"]


def test_expire_stale_drafts(tmp_db: sqlite3.Connection) -> None:
    with freeze_time("2026-05-13T12:00:00Z"):
        insert_draft(tmp_db, Draft(id="old", post_type="tip", caption="x", hashtags=""))
    with freeze_time("2026-05-14T13:00:00Z"):
        count = expire_stale_drafts(tmp_db)
    assert count == 1
    got = get_draft(tmp_db, "old")
    assert got is not None
    assert got.status == "expired"


def test_rotation_state_get_update(tmp_db: sqlite3.Connection) -> None:
    state = get_rotation_state(tmp_db)
    assert isinstance(state, RotationState)
    assert state.project_index == 0
    assert state.last_day is None

    update_rotation_state(tmp_db, last_day="2026-05-13", project_index=1)
    new_state = get_rotation_state(tmp_db)
    assert new_state.last_day == "2026-05-13"
    assert new_state.project_index == 1
    # unchanged fields preserved
    assert new_state.skill_index == 0
```

- [ ] **Step 5.4: Run test to verify failure**

```bash
pytest tests/unit/test_db_store.py -v
```

Expected: ImportError on `agent.db.store`.

- [ ] **Step 5.5: Implement `src/agent/db/store.py`**

```python
"""SQLite CRUD wrappers for drafts, rotation state, and history."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

DRAFT_TTL = timedelta(hours=24)


@dataclass
class Draft:
    id: str
    post_type: str
    caption: str
    hashtags: str
    source_ref: str | None = None
    image_url: str | None = None
    image_credit: str | None = None
    status: str = "pending"
    created_at: str = ""
    expires_at: str = ""
    approved_at: str | None = None
    posted_at: str | None = None
    buffer_post_id: str | None = None
    error: str | None = None


@dataclass
class RotationState:
    last_day: str | None
    project_index: int
    skill_index: int
    exp_index: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def init_db(path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite DB at `path` and apply schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    schema = (resources.files("agent.db") / "schema.sql").read_text()
    conn.executescript(schema)
    conn.commit()
    return conn


def insert_draft(conn: sqlite3.Connection, draft: Draft) -> None:
    now = _utcnow()
    expires = now + DRAFT_TTL
    conn.execute(
        """
        INSERT INTO drafts (
            id, created_at, post_type, source_ref, caption, hashtags,
            image_url, image_credit, status, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft.id,
            _iso(now),
            draft.post_type,
            draft.source_ref,
            draft.caption,
            draft.hashtags,
            draft.image_url,
            draft.image_credit,
            draft.status,
            _iso(expires),
        ),
    )
    conn.commit()


def _row_to_draft(row: sqlite3.Row) -> Draft:
    return Draft(
        id=row["id"],
        created_at=row["created_at"],
        post_type=row["post_type"],
        source_ref=row["source_ref"],
        caption=row["caption"],
        hashtags=row["hashtags"],
        image_url=row["image_url"],
        image_credit=row["image_credit"],
        status=row["status"],
        expires_at=row["expires_at"],
        approved_at=row["approved_at"],
        posted_at=row["posted_at"],
        buffer_post_id=row["buffer_post_id"],
        error=row["error"],
    )


def get_draft(conn: sqlite3.Connection, draft_id: str) -> Draft | None:
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    return _row_to_draft(row) if row else None


def update_draft_status(
    conn: sqlite3.Connection,
    draft_id: str,
    status: str,
    *,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE drafts SET status = ?, error = COALESCE(?, error) WHERE id = ?",
        (status, error, draft_id),
    )
    conn.commit()


def list_pending(conn: sqlite3.Connection) -> list[Draft]:
    rows = conn.execute(
        "SELECT * FROM drafts WHERE status = 'pending' ORDER BY created_at"
    ).fetchall()
    return [_row_to_draft(r) for r in rows]


def expire_stale_drafts(conn: sqlite3.Connection) -> int:
    now = _iso(_utcnow())
    cur = conn.execute(
        "UPDATE drafts SET status = 'expired' WHERE status = 'pending' AND expires_at <= ?",
        (now,),
    )
    conn.commit()
    return cur.rowcount


def get_rotation_state(conn: sqlite3.Connection) -> RotationState:
    row = conn.execute(
        "SELECT last_day, project_index, skill_index, exp_index FROM rotation_state WHERE id = 1"
    ).fetchone()
    return RotationState(
        last_day=row["last_day"],
        project_index=row["project_index"],
        skill_index=row["skill_index"],
        exp_index=row["exp_index"],
    )


def update_rotation_state(
    conn: sqlite3.Connection,
    *,
    last_day: str | None = None,
    project_index: int | None = None,
    skill_index: int | None = None,
    exp_index: int | None = None,
) -> None:
    current = get_rotation_state(conn)
    conn.execute(
        """
        UPDATE rotation_state SET
            last_day = ?, project_index = ?, skill_index = ?, exp_index = ?
        WHERE id = 1
        """,
        (
            last_day if last_day is not None else current.last_day,
            project_index if project_index is not None else current.project_index,
            skill_index if skill_index is not None else current.skill_index,
            exp_index if exp_index is not None else current.exp_index,
        ),
    )
    conn.commit()
```

- [ ] **Step 5.6: Run tests to verify pass**

```bash
pytest tests/unit/test_db_store.py -v
```

Expected: 6 passed.

- [ ] **Step 5.7: Commit**

```bash
git add src/agent/db/
git add tests/unit/test_db_store.py
git commit -m "feat(db): SQLite schema and store for drafts + rotation state"
```

---

## Task 6: Rotation logic

**Files:**
- Create: `src/agent/rotation.py`
- Test: `tests/unit/test_rotation.py`

- [ ] **Step 6.1: Write the failing test**

`tests/unit/test_rotation.py`:

```python
from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from agent.db.store import (
    Draft,
    RotationState,
    get_rotation_state,
    insert_draft,
    update_draft_status,
    update_rotation_state,
)
from agent.profile_model import Profile, load_profile
from agent.rotation import (
    PHASE1_TYPES,
    advance_after_draft,
    already_drafted_today,
    pick_today,
)


@pytest.fixture
def profile(sample_profile_path) -> Profile:
    return load_profile(sample_profile_path)


def test_pick_today_cycles_through_types(tmp_db: sqlite3.Connection, profile: Profile) -> None:
    # Mon 2026-05-11 → project
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 11))
    assert decision is not None
    assert decision.post_type == "project"

    # Tue → concept
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 12))
    assert decision is not None
    assert decision.post_type == "concept"

    # Wed → tip
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 13))
    assert decision is not None
    assert decision.post_type == "tip"

    # Thu → project again (3-day cycle in phase 1)
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 14))
    assert decision is not None
    assert decision.post_type == "project"


def test_pick_today_returns_none_if_already_drafted(
    tmp_db: sqlite3.Connection, profile: Profile
) -> None:
    update_rotation_state(tmp_db, last_day="2026-05-13")
    assert pick_today(tmp_db, profile, today=date(2026, 5, 13)) is None


def test_pick_today_force_overrides_last_day(
    tmp_db: sqlite3.Connection, profile: Profile
) -> None:
    update_rotation_state(tmp_db, last_day="2026-05-13")
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 13), force=True)
    assert decision is not None


def test_pick_today_with_explicit_post_type(
    tmp_db: sqlite3.Connection, profile: Profile
) -> None:
    decision = pick_today(
        tmp_db, profile, today=date(2026, 5, 13), override_post_type="project"
    )
    assert decision is not None
    assert decision.post_type == "project"


def test_project_index_cycles(tmp_db: sqlite3.Connection, profile: Profile) -> None:
    # sample profile has 2 projects (p1, p2)
    d1 = pick_today(tmp_db, profile, today=date(2026, 5, 11))
    assert d1 is not None
    assert d1.sub_key == "p1"

    advance_after_draft(tmp_db, d1)
    update_rotation_state(tmp_db, last_day="2026-05-11")

    # Next project day → p2
    d2 = pick_today(tmp_db, profile, today=date(2026, 5, 14))
    assert d2 is not None
    assert d2.sub_key == "p2"

    advance_after_draft(tmp_db, d2)
    update_rotation_state(tmp_db, last_day="2026-05-14")

    # Wraps back to p1
    d3 = pick_today(tmp_db, profile, today=date(2026, 5, 17))
    assert d3 is not None
    assert d3.sub_key == "p1"


def test_already_drafted_today(tmp_db: sqlite3.Connection) -> None:
    assert already_drafted_today(tmp_db, today=date(2026, 5, 13)) is False
    update_rotation_state(tmp_db, last_day="2026-05-13")
    assert already_drafted_today(tmp_db, today=date(2026, 5, 13)) is True


def test_phase1_types_constant() -> None:
    assert PHASE1_TYPES == ("project", "concept", "tip")
```

- [ ] **Step 6.2: Run test to verify failure**

```bash
pytest tests/unit/test_rotation.py -v
```

Expected: ImportError on `agent.rotation`.

- [ ] **Step 6.3: Implement `src/agent/rotation.py`**

```python
"""Decide today's post type and sub-key from rotation state + calendar."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from agent.db.store import get_rotation_state, update_rotation_state
from agent.profile_model import Profile

PHASE1_TYPES: tuple[str, ...] = ("project", "concept", "tip")


@dataclass(frozen=True)
class RotationDecision:
    """What to post today and the rotating sub-selector inside that type."""

    post_type: str
    sub_key: str | None


def already_drafted_today(conn: sqlite3.Connection, today: date) -> bool:
    state = get_rotation_state(conn)
    return state.last_day == today.isoformat()


def _weekday_to_type(d: date) -> str:
    # Mon=0 → project, Tue=1 → concept, Wed=2 → tip, then cycle.
    return PHASE1_TYPES[d.weekday() % len(PHASE1_TYPES)]


def _skill_categories(profile: Profile) -> list[str]:
    return list(profile.skills.keys())


def _sub_key(post_type: str, profile: Profile, state) -> str | None:
    if post_type == "project":
        if not profile.projects:
            return None
        idx = state.project_index % len(profile.projects)
        return profile.projects[idx].id
    if post_type == "concept":
        cats = _skill_categories(profile)
        if not cats:
            return None
        idx = state.skill_index % len(cats)
        return cats[idx]
    if post_type == "tip":
        if not profile.experience:
            return None
        idx = state.exp_index % len(profile.experience)
        return profile.experience[idx].id
    return None


def pick_today(
    conn: sqlite3.Connection,
    profile: Profile,
    *,
    today: date,
    force: bool = False,
    override_post_type: str | None = None,
) -> RotationDecision | None:
    """Return today's draft decision, or None if already drafted (and not forced)."""
    if not force and already_drafted_today(conn, today):
        return None
    post_type = override_post_type or _weekday_to_type(today)
    if post_type not in PHASE1_TYPES:
        raise ValueError(f"Unsupported post_type for phase 1: {post_type}")
    state = get_rotation_state(conn)
    return RotationDecision(post_type=post_type, sub_key=_sub_key(post_type, profile, state))


def advance_after_draft(conn: sqlite3.Connection, decision: RotationDecision) -> None:
    state = get_rotation_state(conn)
    if decision.post_type == "project":
        update_rotation_state(conn, project_index=state.project_index + 1)
    elif decision.post_type == "concept":
        update_rotation_state(conn, skill_index=state.skill_index + 1)
    elif decision.post_type == "tip":
        update_rotation_state(conn, exp_index=state.exp_index + 1)
```

- [ ] **Step 6.4: Run tests to verify pass**

```bash
pytest tests/unit/test_rotation.py -v
```

Expected: 7 passed.

- [ ] **Step 6.5: Commit**

```bash
git add src/agent/rotation.py tests/unit/test_rotation.py
git commit -m "feat(rotation): weekday-based 3-type rotation with sub-key cycling"
```

---

## Task 7: Profile source

**Files:**
- Create: `src/agent/sources/__init__.py`
- Create: `src/agent/sources/profile.py`
- Test: `tests/unit/test_sources_profile.py`

- [ ] **Step 7.1: Create package marker**

`src/agent/sources/__init__.py`: empty.

- [ ] **Step 7.2: Write the failing test**

`tests/unit/test_sources_profile.py`:

```python
from __future__ import annotations

import pytest

from agent.profile_model import Profile, load_profile
from agent.rotation import RotationDecision
from agent.sources.profile import SourceContent, build_source


@pytest.fixture
def profile(sample_profile_path) -> Profile:
    return load_profile(sample_profile_path)


def test_project_source(profile: Profile) -> None:
    src = build_source(RotationDecision("project", "p1"), profile)
    assert isinstance(src, SourceContent)
    assert src.title == "Project One"
    assert "95%" in src.body or "95" in src.body
    assert "PyTorch" in src.keywords
    assert src.source_ref == "project:p1"


def test_project_missing_id_falls_back_to_first(profile: Profile) -> None:
    src = build_source(RotationDecision("project", "nope"), profile)
    assert src.source_ref == "project:p1"


def test_concept_source(profile: Profile) -> None:
    # sub_key is a skills category key
    src = build_source(RotationDecision("concept", "machine_learning"), profile)
    assert "XGBoost" in src.body
    assert src.source_ref == "concept:machine_learning"
    assert "machine_learning" in src.keywords or "XGBoost" in src.keywords


def test_tip_source(profile: Profile) -> None:
    src = build_source(RotationDecision("tip", "co_a"), profile)
    assert "Co A" in src.body
    assert src.source_ref == "tip:co_a"


def test_unknown_type_raises(profile: Profile) -> None:
    with pytest.raises(ValueError):
        build_source(RotationDecision("commentary", None), profile)
```

- [ ] **Step 7.3: Run test to verify failure**

```bash
pytest tests/unit/test_sources_profile.py -v
```

Expected: ImportError on `agent.sources.profile`.

- [ ] **Step 7.4: Implement `src/agent/sources/profile.py`**

```python
"""Build source content from the profile for a given rotation decision."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.profile_model import Profile
from agent.rotation import RotationDecision


@dataclass(frozen=True)
class SourceContent:
    """Raw material handed to the caption generator."""

    title: str
    body: str
    keywords: list[str]
    source_ref: str
    metrics: dict[str, str | float | int] = field(default_factory=dict)


def _project_source(profile: Profile, sub_key: str | None) -> SourceContent:
    project = next((p for p in profile.projects if p.id == sub_key), profile.projects[0])
    framing = project.framings.get("data_scientist") or next(iter(project.framings.values()))
    metrics_text = ", ".join(f"{k}={v}" for k, v in project.metrics.items())
    body = framing + (f"\nMetrics: {metrics_text}" if metrics_text else "")
    keywords = [project.title, *project.tech, *project.domain]
    return SourceContent(
        title=project.title,
        body=body,
        keywords=keywords,
        source_ref=f"project:{project.id}",
        metrics=project.metrics,
    )


def _concept_source(profile: Profile, sub_key: str | None) -> SourceContent:
    cat = sub_key if sub_key and sub_key in profile.skills else next(iter(profile.skills.keys()))
    items = profile.skills[cat]
    body = (
        f"Skill category: {cat}. Items I use day-to-day: " + ", ".join(items) + ". "
        "Pick the most interesting one and explain it crisply for a working data professional."
    )
    return SourceContent(
        title=cat.replace("_", " ").title(),
        body=body,
        keywords=[cat, *items[:5]],
        source_ref=f"concept:{cat}",
    )


def _tip_source(profile: Profile, sub_key: str | None) -> SourceContent:
    exp = next((e for e in profile.experience if e.id == sub_key), profile.experience[0])
    bullets = exp.bullets.get("data_analyst") or next(iter(exp.bullets.values()))
    body = f"Role: {exp.title} @ {exp.company} ({exp.start} – {exp.end}). " + " ".join(bullets)
    return SourceContent(
        title=f"{exp.title} @ {exp.company}",
        body=body,
        keywords=[exp.company, exp.title, "growth analytics", "EdTech"],
        source_ref=f"tip:{exp.id}",
    )


def build_source(decision: RotationDecision, profile: Profile) -> SourceContent:
    if decision.post_type == "project":
        return _project_source(profile, decision.sub_key)
    if decision.post_type == "concept":
        return _concept_source(profile, decision.sub_key)
    if decision.post_type == "tip":
        return _tip_source(profile, decision.sub_key)
    raise ValueError(f"Unsupported post type: {decision.post_type}")
```

- [ ] **Step 7.5: Run tests to verify pass**

```bash
pytest tests/unit/test_sources_profile.py -v
```

Expected: 5 passed.

- [ ] **Step 7.6: Commit**

```bash
git add src/agent/sources/ tests/unit/test_sources_profile.py
git commit -m "feat(sources): profile-driven source content for project/concept/tip"
```

---

## Task 8: Prompt templates

**Files:**
- Create: `src/agent/generators/__init__.py`
- Create: `src/agent/generators/prompts.py`
- Test: `tests/unit/test_generators_prompts.py`

- [ ] **Step 8.1: Create package marker**

`src/agent/generators/__init__.py`: empty.

- [ ] **Step 8.2: Write the failing test**

`tests/unit/test_generators_prompts.py`:

```python
from agent.generators.prompts import (
    VOICE_GUIDELINES,
    build_caption_messages,
    build_hashtag_messages,
)
from agent.sources.profile import SourceContent


def test_caption_messages_contain_voice_and_source() -> None:
    src = SourceContent(
        title="Project One",
        body="Built a deep learning thing with 95% accuracy.",
        keywords=["PyTorch", "ml"],
        source_ref="project:p1",
        metrics={"accuracy": "95%"},
    )
    msgs = build_caption_messages("project", src, role_targets=["Data Scientist"])
    assert len(msgs) >= 1
    user_text = "\n".join(m["content"] for m in msgs if m["role"] == "user")
    assert "Project One" in user_text
    assert "95%" in user_text
    assert "project" in user_text.lower()


def test_voice_guidelines_present() -> None:
    assert "metric" in VOICE_GUIDELINES.lower()
    assert "hashtag" not in VOICE_GUIDELINES.lower()  # captions don't carry hashtags inline


def test_hashtag_messages() -> None:
    msgs = build_hashtag_messages(
        post_type="project",
        caption="My new project on attention u-net achieved 97% recovery.",
        keywords=["Attention U-Net", "PyTorch"],
    )
    user_text = "\n".join(m["content"] for m in msgs if m["role"] == "user")
    assert "Attention U-Net" in user_text or "attention" in user_text.lower()
    assert "JSON" in user_text or "json" in user_text
```

- [ ] **Step 8.3: Run test to verify failure**

```bash
pytest tests/unit/test_generators_prompts.py -v
```

Expected: ImportError on `agent.generators.prompts`.

- [ ] **Step 8.4: Implement `src/agent/generators/prompts.py`**

```python
"""Prompt builders for caption + hashtag generation."""

from __future__ import annotations

from agent.sources.profile import SourceContent

VOICE_GUIDELINES = """\
Voice for Anuj Bansal's LinkedIn:
- First person, confident but not boastful.
- Metric-heavy: cite specific numbers when the source provides them ($ amounts,
  %, throughput, accuracy). Never invent metrics.
- Technical but accessible: explain the "what" briefly, then "why it matters".
- Target audience: hiring managers and peers in Business Analyst / Data Analyst
  / Data Scientist roles in the US.
- Tone: thoughtful, grounded in real work. Avoid hype words ("revolutionary",
  "10x", "blown away"). Avoid emoji walls. One or two emoji at most, only if
  natural.
- Structure: hook (1 line) → body (3–5 short paragraphs, blank lines between)
  → soft CTA (1 line, a question or invite).
- Length: 800–1300 characters total.
- Do NOT include hashtags inline; they are added separately.
- Do NOT include URLs in the caption body."""


_TYPE_INSTRUCTIONS = {
    "project": (
        "Write a project breakdown post. Lead with the outcome (a metric or "
        "decision the project enabled). Then walk briefly through what you "
        "built, one technical choice that mattered, and what you learned. "
        "End with a question that invites discussion."
    ),
    "concept": (
        "Write a concept explainer post. Pick ONE concept from the supplied "
        "skill category and explain it in plain language with a tiny concrete "
        "example. End by asking how others apply it."
    ),
    "tip": (
        "Write a tip/insight post. Share ONE concrete lesson from the supplied "
        "experience bullets. State the situation, the move, the outcome (with "
        "metric). End with a one-line takeaway and a question."
    ),
}


def build_caption_messages(
    post_type: str,
    source: SourceContent,
    role_targets: list[str],
) -> list[dict[str, str]]:
    """Return messages for Anthropic Messages API to generate the caption."""
    instructions = _TYPE_INSTRUCTIONS[post_type]
    metrics_block = ""
    if source.metrics:
        metrics_block = "\nMetrics from the source (use these exact numbers if you cite any):\n" + "\n".join(
            f"- {k}: {v}" for k, v in source.metrics.items()
        )
    user = (
        f"Post type: {post_type}\n"
        f"Source title: {source.title}\n"
        f"Source content:\n{source.body}\n"
        f"Role targets: {', '.join(role_targets)}\n"
        f"{metrics_block}\n\n"
        f"Instructions:\n{instructions}\n\n"
        "Return ONLY the caption text. No preamble, no quotes, no hashtags."
    )
    return [
        {"role": "user", "content": VOICE_GUIDELINES + "\n\n" + user},
    ]


def build_hashtag_messages(
    post_type: str,
    caption: str,
    keywords: list[str],
) -> list[dict[str, str]]:
    """Return messages to generate 5–8 hashtags as a JSON array of strings."""
    user = (
        "Pick 5 to 8 LinkedIn hashtags for the post below.\n"
        "Rules:\n"
        "- Mix evergreen tags (e.g. #DataScience, #MachineLearning) with niche tags "
        "specific to the content.\n"
        "- No spaces, no punctuation other than the leading #.\n"
        "- CamelCase multi-word tags (e.g. #AttentionUNet).\n"
        "- Avoid banned/spammy tags (#follow, #like, #viral).\n\n"
        f"Post type: {post_type}\n"
        f"Caption:\n{caption}\n\n"
        f"Keywords (use these to inspire niche tags): {', '.join(keywords)}\n\n"
        'Return ONLY a JSON array of strings, no prose. Example: ["#DataScience", "#SHAP"]'
    )
    return [{"role": "user", "content": user}]
```

- [ ] **Step 8.5: Run tests to verify pass**

```bash
pytest tests/unit/test_generators_prompts.py -v
```

Expected: 3 passed.

- [ ] **Step 8.6: Commit**

```bash
git add src/agent/generators/__init__.py src/agent/generators/prompts.py tests/unit/test_generators_prompts.py
git commit -m "feat(prompts): caption + hashtag prompt builders with voice guide"
```

---

## Task 9: Caption generator (Claude API call)

**Files:**
- Create: `src/agent/generators/caption.py`
- Create: `tests/fixtures/claude_caption.txt`
- Test: `tests/unit/test_generators_caption.py`

- [ ] **Step 9.1: Create sample caption fixture**

`tests/fixtures/claude_caption.txt`:

```
Built a two-stage Attention U-Net pipeline for AFM height-map reconstruction that hit 97.1% median recovery and 0.77 nm MAE — a 75 percentage-point jump over the baseline.

The interesting bit wasn't the architecture, it was the loss: a custom AFMLoss combining L1, standard-deviation, and range terms.

Plain MSE pushed the network to wash out the fine surface texture. Adding the Std + Range terms forced it to match both the magnitude AND the variability of the true height map, which is what materials researchers actually care about.

Lesson: when your metric and your loss diverge, the loss wins. Time spent designing the loss is rarely wasted.

What's the most surprising loss function you've ever shipped?
```

- [ ] **Step 9.2: Write the failing test**

`tests/unit/test_generators_caption.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from agent.generators.caption import generate_caption
from agent.sources.profile import SourceContent


class FakeAnthropicClient:
    """Mimics the Messages API surface we use."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []
        self.messages = self  # we use client.messages.create

    def create(self, **kwargs) -> object:
        self.calls.append(kwargs)

        class _Block:
            def __init__(self, t: str) -> None:
                self.type = "text"
                self.text = t

        class _Resp:
            def __init__(self, t: str) -> None:
                self.content = [_Block(t)]

        return _Resp(self._text)


def test_generate_caption_returns_text(tmp_path: Path) -> None:
    fixture = (Path(__file__).parent.parent / "fixtures" / "claude_caption.txt").read_text()
    client = FakeAnthropicClient(fixture)
    src = SourceContent(
        title="AFM Z-Height Map Reconstruction",
        body="Built a two-stage deep learning pipeline...",
        keywords=["PyTorch", "Attention U-Net"],
        source_ref="project:afm",
        metrics={"median_recovery": "97.1%", "mae_nm": 0.77},
    )
    out = generate_caption(
        client,
        post_type="project",
        source=src,
        role_targets=["Data Scientist"],
        model="claude-sonnet-4-6",
    )
    assert "97.1%" in out
    assert len(client.calls) == 1
    assert client.calls[0]["model"] == "claude-sonnet-4-6"
    # message contains our voice guidelines + source body
    user_msg = client.calls[0]["messages"][0]["content"]
    assert "AFM" in user_msg
```

- [ ] **Step 9.3: Run test to verify failure**

```bash
pytest tests/unit/test_generators_caption.py -v
```

Expected: ImportError.

- [ ] **Step 9.4: Implement `src/agent/generators/caption.py`**

```python
"""Generate a LinkedIn caption via Anthropic's Messages API."""

from __future__ import annotations

import logging
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from agent.generators.prompts import build_caption_messages
from agent.sources.profile import SourceContent

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

log = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    reraise=True,
)
def generate_caption(
    client: Any,
    *,
    post_type: str,
    source: SourceContent,
    role_targets: list[str],
    model: str = DEFAULT_MODEL,
) -> str:
    """Call Claude and return the caption text.

    `client` is an `anthropic.Anthropic` instance (or a duck-typed test double).
    """
    messages = build_caption_messages(post_type, source, role_targets)
    log.info("Generating caption (model=%s, post_type=%s)", model, post_type)
    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=messages,
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
    return text.strip()
```

- [ ] **Step 9.5: Run tests to verify pass**

```bash
pytest tests/unit/test_generators_caption.py -v
```

Expected: 1 passed.

- [ ] **Step 9.6: Commit**

```bash
git add src/agent/generators/caption.py tests/fixtures/claude_caption.txt tests/unit/test_generators_caption.py
git commit -m "feat(caption): Anthropic-backed caption generator with retry"
```

---

## Task 10: Hashtag generator

**Files:**
- Create: `src/agent/generators/hashtags.py`
- Create: `tests/fixtures/claude_hashtags.json`
- Test: `tests/unit/test_generators_hashtags.py`

- [ ] **Step 10.1: Create hashtag fixture**

`tests/fixtures/claude_hashtags.json`:

```json
["#DataScience", "#DeepLearning", "#PyTorch", "#AttentionUNet", "#SHAP", "#MLResearch"]
```

- [ ] **Step 10.2: Write the failing test**

`tests/unit/test_generators_hashtags.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.generators.hashtags import format_hashtags, generate_hashtags


class FakeClient:
    def __init__(self, raw: str) -> None:
        self._raw = raw
        self.messages = self
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class _Block:
            type = "text"

            def __init__(self, t: str) -> None:
                self.text = t

        class _Resp:
            def __init__(self, t: str) -> None:
                self.content = [_Block(t)]

        return _Resp(self._raw)


def test_generate_hashtags_parses_json() -> None:
    raw = (Path(__file__).parent.parent / "fixtures" / "claude_hashtags.json").read_text()
    client = FakeClient(raw)
    tags = generate_hashtags(
        client,
        post_type="project",
        caption="A caption about deep learning.",
        keywords=["PyTorch"],
        model="claude-haiku-4-5-20251001",
    )
    assert tags[0].startswith("#")
    assert 5 <= len(tags) <= 8
    assert "#DataScience" in tags
    assert client.calls[0]["model"] == "claude-haiku-4-5-20251001"


def test_generate_hashtags_strips_codefence() -> None:
    client = FakeClient('```json\n["#A", "#B", "#C", "#D", "#E"]\n```')
    tags = generate_hashtags(client, post_type="tip", caption="x", keywords=[])
    assert tags == ["#A", "#B", "#C", "#D", "#E"]


def test_generate_hashtags_raises_on_garbage() -> None:
    client = FakeClient("not json at all")
    with pytest.raises(ValueError):
        generate_hashtags(client, post_type="tip", caption="x", keywords=[])


def test_format_hashtags() -> None:
    assert format_hashtags(["#A", "#B", "#C"]) == "#A #B #C"
```

- [ ] **Step 10.3: Run test to verify failure**

```bash
pytest tests/unit/test_generators_hashtags.py -v
```

Expected: ImportError.

- [ ] **Step 10.4: Implement `src/agent/generators/hashtags.py`**

```python
"""Generate LinkedIn hashtags via Claude Haiku (cheap, fast)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from agent.generators.prompts import build_hashtag_messages

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 256

log = logging.getLogger(__name__)


def _strip_codefence(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    return m.group(1) if m else text


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=16), reraise=True)
def generate_hashtags(
    client: Any,
    *,
    post_type: str,
    caption: str,
    keywords: list[str],
    model: str = DEFAULT_MODEL,
) -> list[str]:
    """Return 5–8 hashtags. Raises ValueError if Claude's response is unparseable."""
    messages = build_hashtag_messages(post_type, caption, keywords)
    log.info("Generating hashtags (model=%s)", model)
    resp = client.messages.create(model=model, max_tokens=MAX_TOKENS, messages=messages)
    raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    payload = _strip_codefence(raw).strip()
    try:
        tags = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ValueError(f"Hashtags response not JSON: {raw!r}") from e
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError(f"Hashtags response not list[str]: {tags!r}")
    return [t if t.startswith("#") else f"#{t}" for t in tags]


def format_hashtags(tags: list[str]) -> str:
    """Join hashtags into the single-line string used in the post body."""
    return " ".join(tags)
```

- [ ] **Step 10.5: Run tests to verify pass**

```bash
pytest tests/unit/test_generators_hashtags.py -v
```

Expected: 4 passed.

- [ ] **Step 10.6: Commit**

```bash
git add src/agent/generators/hashtags.py tests/fixtures/claude_hashtags.json tests/unit/test_generators_hashtags.py
git commit -m "feat(hashtags): Haiku-backed hashtag generator returning 5-8 tags"
```

---

## Task 11: Unsplash image fetcher

**Files:**
- Create: `src/agent/generators/image.py`
- Create: `tests/fixtures/unsplash_search.json`
- Test: `tests/unit/test_generators_image.py`

- [ ] **Step 11.1: Create Unsplash response fixture**

`tests/fixtures/unsplash_search.json`:

```json
{
  "total": 1,
  "total_pages": 1,
  "results": [
    {
      "id": "abc123",
      "urls": {
        "raw": "https://images.unsplash.com/raw",
        "full": "https://images.unsplash.com/full",
        "regular": "https://images.unsplash.com/regular",
        "small": "https://images.unsplash.com/small"
      },
      "links": {"html": "https://unsplash.com/photos/abc123"},
      "user": {"name": "Jane Doe", "username": "janed"}
    }
  ]
}
```

- [ ] **Step 11.2: Write the failing test**

`tests/unit/test_generators_image.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from agent.generators.image import FALLBACK_IMAGE_URL, ImageResult, fetch_image


FIXTURE = Path(__file__).parent.parent / "fixtures" / "unsplash_search.json"


@respx.mock
def test_fetch_image_success() -> None:
    body = json.loads(FIXTURE.read_text())
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(200, json=body)
    )
    result = fetch_image(
        keywords=["data science", "ml"], access_key="test-key"
    )
    assert isinstance(result, ImageResult)
    assert result.url == "https://images.unsplash.com/regular"
    assert "Jane Doe" in result.credit
    assert "Unsplash" in result.credit


@respx.mock
def test_fetch_image_no_results_falls_back() -> None:
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    result = fetch_image(keywords=["zzz"], access_key="test-key")
    assert result.url == FALLBACK_IMAGE_URL
    assert "fallback" in result.credit.lower()


@respx.mock
def test_fetch_image_http_error_falls_back() -> None:
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(500, json={"errors": ["oops"]})
    )
    result = fetch_image(keywords=["x"], access_key="test-key")
    assert result.url == FALLBACK_IMAGE_URL
```

- [ ] **Step 11.3: Run test to verify failure**

```bash
pytest tests/unit/test_generators_image.py -v
```

Expected: ImportError.

- [ ] **Step 11.4: Implement `src/agent/generators/image.py`**

```python
"""Pick an image from Unsplash search results, with a stock fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

FALLBACK_IMAGE_URL = (
    "https://images.unsplash.com/photo-1551288049-bebda4e38f71"
    "?w=1200&auto=format&fit=crop&q=80"
)
FALLBACK_CREDIT = "Photo: Unsplash (fallback stock)"
UNSPLASH_SEARCH = "https://api.unsplash.com/search/photos"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageResult:
    url: str
    credit: str


def _credit(user: dict, photo_link: str) -> str:
    name = user.get("name") or user.get("username") or "Unsplash photographer"
    return f"Photo by {name} on Unsplash ({photo_link})"


def fetch_image(*, keywords: list[str], access_key: str) -> ImageResult:
    """Search Unsplash; return first result or a fallback on error/empty."""
    query = " ".join(keywords[:3]) or "technology"
    try:
        resp = httpx.get(
            UNSPLASH_SEARCH,
            params={"query": query, "per_page": 5, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Unsplash fetch failed: %s — using fallback", e)
        return ImageResult(FALLBACK_IMAGE_URL, FALLBACK_CREDIT)

    results = data.get("results") or []
    if not results:
        log.info("Unsplash returned no results for %r — using fallback", query)
        return ImageResult(FALLBACK_IMAGE_URL, FALLBACK_CREDIT)
    first = results[0]
    url = first["urls"]["regular"]
    credit = _credit(first.get("user", {}), first.get("links", {}).get("html", ""))
    return ImageResult(url, credit)
```

- [ ] **Step 11.5: Run tests to verify pass**

```bash
pytest tests/unit/test_generators_image.py -v
```

Expected: 3 passed.

- [ ] **Step 11.6: Commit**

```bash
git add src/agent/generators/image.py tests/fixtures/unsplash_search.json tests/unit/test_generators_image.py
git commit -m "feat(image): Unsplash search with stock fallback on error/empty"
```

---

## Task 12: Email delivery

**Files:**
- Create: `src/agent/delivery/__init__.py`
- Create: `src/agent/delivery/email.py`
- Test: `tests/unit/test_delivery_email.py`

- [ ] **Step 12.1: Create package marker**

`src/agent/delivery/__init__.py`: empty.

- [ ] **Step 12.2: Write the failing test**

`tests/unit/test_delivery_email.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from agent.delivery.email import build_draft_email, send_email
from agent.db.store import Draft


def _sample_draft() -> Draft:
    return Draft(
        id="d-test",
        post_type="project",
        source_ref="project:afm",
        caption="Hook line.\n\nBody paragraph one.\n\nQuestion?",
        hashtags="#DataScience #DeepLearning #PyTorch",
        image_url="https://images.unsplash.com/x",
        image_credit="Photo by Jane on Unsplash",
        status="pending",
        created_at="2026-05-13T12:00:00+00:00",
        expires_at="2026-05-14T12:00:00+00:00",
    )


def test_build_draft_email_contains_caption_hashtags_image() -> None:
    msg = build_draft_email(
        draft=_sample_draft(),
        sender="a@b.com",
        recipient="a@b.com",
    )
    assert msg["Subject"].startswith("[LinkedIn Draft]")
    assert msg["From"] == "a@b.com"
    assert msg["To"] == "a@b.com"
    body_text = msg.get_body(preferencelist=("plain",)).get_content()
    body_html = msg.get_body(preferencelist=("html",)).get_content()
    assert "Hook line." in body_text
    assert "#DataScience" in body_text
    assert "Hook line." in body_html
    assert "https://images.unsplash.com/x" in body_html
    assert "Photo by Jane" in body_html


def test_send_email_uses_smtp_client() -> None:
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.__exit__.return_value = None
    msg = build_draft_email(_sample_draft(), sender="a@b.com", recipient="a@b.com")

    send_email(
        msg,
        host="smtp.gmail.com",
        port=465,
        username="a@b.com",
        password="pw",
        smtp_factory=lambda host, port: smtp,
    )

    smtp.login.assert_called_once_with("a@b.com", "pw")
    smtp.send_message.assert_called_once()
    sent_msg = smtp.send_message.call_args[0][0]
    assert sent_msg["Subject"].startswith("[LinkedIn Draft]")
```

- [ ] **Step 12.3: Run test to verify failure**

```bash
pytest tests/unit/test_delivery_email.py -v
```

Expected: ImportError.

- [ ] **Step 12.4: Implement `src/agent/delivery/email.py`**

```python
"""Build and send the draft preview email via Gmail SMTP."""

from __future__ import annotations

import logging
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

from agent.db.store import Draft

log = logging.getLogger(__name__)


def _subject(draft: Draft) -> str:
    first_line = draft.caption.splitlines()[0] if draft.caption else "(empty)"
    return f"[LinkedIn Draft] {first_line[:60]}"


def _plain_body(draft: Draft) -> str:
    return (
        f"Post type: {draft.post_type}\n"
        f"Source: {draft.source_ref}\n"
        f"Draft ID: {draft.id}\n"
        f"Expires: {draft.expires_at}\n"
        f"\n"
        f"--- CAPTION ---\n"
        f"{draft.caption}\n"
        f"\n"
        f"--- HASHTAGS ---\n"
        f"{draft.hashtags}\n"
        f"\n"
        f"--- IMAGE ---\n"
        f"{draft.image_url or '(none)'}\n"
        f"{draft.image_credit or ''}\n"
    )


def _html_body(draft: Draft) -> str:
    image_html = (
        f'<p><img src="{draft.image_url}" alt="suggested image" '
        f'style="max-width:520px;border:1px solid #ddd;border-radius:6px"/></p>'
        f'<p style="color:#666;font-size:12px">{draft.image_credit or ""}</p>'
        if draft.image_url
        else ""
    )
    caption_html = draft.caption.replace("\n\n", "</p><p>").replace("\n", "<br/>")
    return f"""\
<html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5">
  <h2 style="margin:0 0 4px 0">LinkedIn Draft — {draft.post_type}</h2>
  <p style="color:#888;margin:0 0 16px 0;font-size:13px">
    Source: {draft.source_ref or '—'} · Draft ID: {draft.id} · Expires: {draft.expires_at}
  </p>
  {image_html}
  <div style="background:#f7f7f9;padding:16px;border-radius:8px;margin:16px 0">
    <p>{caption_html}</p>
  </div>
  <p style="font-weight:600">Hashtags</p>
  <p style="color:#0a66c2">{draft.hashtags}</p>
  <hr/>
  <p style="color:#888;font-size:12px">
    Phase 1: copy-paste this into LinkedIn at 11:00 ET. Approval link comes in Phase 2.
  </p>
</body></html>
"""


def build_draft_email(*, draft: Draft, sender: str, recipient: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = _subject(draft)
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(_plain_body(draft))
    msg.add_alternative(_html_body(draft), subtype="html")
    return msg


SmtpFactory = Callable[[str, int], Any]


def _default_smtp_factory(host: str, port: int) -> smtplib.SMTP_SSL:
    return smtplib.SMTP_SSL(host, port, context=ssl.create_default_context())


def send_email(
    msg: EmailMessage,
    *,
    host: str = "smtp.gmail.com",
    port: int = 465,
    username: str,
    password: str,
    smtp_factory: SmtpFactory = _default_smtp_factory,
) -> None:
    log.info("Sending email to %s via %s:%s", msg["To"], host, port)
    with smtp_factory(host, port) as smtp:
        smtp.login(username, password)
        smtp.send_message(msg)
```

- [ ] **Step 12.5: Run tests to verify pass**

```bash
pytest tests/unit/test_delivery_email.py -v
```

Expected: 2 passed.

- [ ] **Step 12.6: Commit**

```bash
git add src/agent/delivery/__init__.py src/agent/delivery/email.py tests/unit/test_delivery_email.py
git commit -m "feat(email): build + send Gmail SMTP draft preview (plain + HTML)"
```

---

## Task 13: Draft entrypoint (pipeline)

**Files:**
- Create: `src/agent/draft.py`
- Test: `tests/unit/test_draft_pipeline.py`

- [ ] **Step 13.1: Write the failing test**

`tests/unit/test_draft_pipeline.py`:

```python
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from agent.config import Settings
from agent.db.store import (
    get_draft,
    get_rotation_state,
    init_db,
    list_pending,
)
from agent.draft import DraftResult, run_draft
from agent.generators.image import ImageResult


@pytest.fixture
def settings(tmp_path: Path, sample_profile_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="x",
        unsplash_access_key="x",
        gmail_username="a@b.com",
        gmail_app_password="x",
        gmail_recipient="a@b.com",
        profile_path=sample_profile_path,
        db_path=tmp_path / "state.sqlite",
        log_level="INFO",
    )


def _wire_fakes():
    anthropic = MagicMock()

    class _Block:
        type = "text"

    block = _Block()
    block.text = "Hook.\n\nBody.\n\nQ?"
    anthropic.messages.create.side_effect = [
        MagicMock(content=[block]),
        MagicMock(content=[type("B", (), {"type": "text", "text": '["#A","#B","#C","#D","#E"]'})()]),
    ]
    image_fn = MagicMock(return_value=ImageResult(url="http://img", credit="cred"))
    send_fn = MagicMock()
    return anthropic, image_fn, send_fn


@freeze_time("2026-05-13T12:00:00Z")
def test_run_draft_happy_path(settings: Settings) -> None:
    # init DB once so paths exist
    conn = init_db(settings.db_path)
    conn.close()

    anthropic, image_fn, send_fn = _wire_fakes()

    result = run_draft(
        settings,
        anthropic_client=anthropic,
        image_fn=image_fn,
        email_send_fn=send_fn,
        today=date(2026, 5, 13),  # Wed → tip
    )
    assert isinstance(result, DraftResult)
    assert result.status == "drafted"
    assert result.post_type == "tip"

    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (result.draft_id,)).fetchone()
    assert row is not None
    assert row["status"] == "pending"
    assert row["post_type"] == "tip"
    rs = get_rotation_state(conn)
    assert rs.last_day == "2026-05-13"
    assert rs.exp_index == 1
    conn.close()

    image_fn.assert_called_once()
    send_fn.assert_called_once()


@freeze_time("2026-05-13T12:00:00Z")
def test_run_draft_skips_when_already_drafted(settings: Settings) -> None:
    conn = init_db(settings.db_path)
    conn.execute("UPDATE rotation_state SET last_day = '2026-05-13' WHERE id = 1")
    conn.commit()
    conn.close()

    anthropic, image_fn, send_fn = _wire_fakes()
    result = run_draft(
        settings,
        anthropic_client=anthropic,
        image_fn=image_fn,
        email_send_fn=send_fn,
        today=date(2026, 5, 13),
    )
    assert result.status == "skipped"
    anthropic.messages.create.assert_not_called()
    send_fn.assert_not_called()


@freeze_time("2026-05-13T12:00:00Z")
def test_run_draft_dry_run_does_not_email_or_persist(settings: Settings) -> None:
    init_db(settings.db_path).close()
    anthropic, image_fn, send_fn = _wire_fakes()
    result = run_draft(
        settings,
        anthropic_client=anthropic,
        image_fn=image_fn,
        email_send_fn=send_fn,
        today=date(2026, 5, 13),
        dry_run=True,
    )
    assert result.status == "dry_run"
    send_fn.assert_not_called()
    conn = sqlite3.connect(settings.db_path)
    rows = conn.execute("SELECT COUNT(*) FROM drafts").fetchone()
    assert rows[0] == 0
    rs = get_rotation_state(conn)
    assert rs.last_day is None
    conn.close()
```

- [ ] **Step 13.2: Run test to verify failure**

```bash
pytest tests/unit/test_draft_pipeline.py -v
```

Expected: ImportError on `agent.draft`.

- [ ] **Step 13.3: Implement `src/agent/draft.py`**

```python
"""Draft pipeline entrypoint: pick → source → caption → hashtags → image → email."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from agent.config import Settings
from agent.db.store import (
    Draft,
    expire_stale_drafts,
    init_db,
    insert_draft,
    update_rotation_state,
)
from agent.delivery.email import build_draft_email, send_email
from agent.generators.caption import generate_caption
from agent.generators.hashtags import format_hashtags, generate_hashtags
from agent.generators.image import ImageResult, fetch_image
from agent.profile_model import load_profile
from agent.rotation import advance_after_draft, pick_today
from agent.sources.profile import build_source

log = logging.getLogger(__name__)


ImageFn = Callable[..., ImageResult]
EmailSendFn = Callable[..., None]


@dataclass(frozen=True)
class DraftResult:
    status: str  # "drafted" | "skipped" | "dry_run" | "error"
    post_type: str | None = None
    draft_id: str | None = None
    message: str = ""


def _default_image_fn(keywords: list[str], access_key: str) -> ImageResult:
    return fetch_image(keywords=keywords, access_key=access_key)


def _default_email_send(
    msg, *, username: str, password: str
) -> None:
    send_email(msg, username=username, password=password)


def run_draft(
    settings: Settings,
    *,
    anthropic_client: Any,
    image_fn: ImageFn | None = None,
    email_send_fn: EmailSendFn | None = None,
    today: date | None = None,
    force: bool = False,
    override_post_type: str | None = None,
    dry_run: bool = False,
) -> DraftResult:
    today = today or date.today()
    image_fn = image_fn or (
        lambda keywords, **_: _default_image_fn(keywords, settings.unsplash_access_key)
    )
    email_send_fn = email_send_fn or (
        lambda msg, **_: _default_email_send(
            msg, username=settings.gmail_username, password=settings.gmail_app_password
        )
    )

    profile = load_profile(settings.profile_path)
    conn = init_db(settings.db_path)

    try:
        expire_stale_drafts(conn)
        decision = pick_today(
            conn,
            profile,
            today=today,
            force=force,
            override_post_type=override_post_type,
        )
        if decision is None:
            log.info("Already drafted today (%s); skipping.", today)
            return DraftResult(status="skipped", message=f"already drafted on {today}")

        source = build_source(decision, profile)
        caption = generate_caption(
            anthropic_client,
            post_type=decision.post_type,
            source=source,
            role_targets=profile.role_targets,
        )
        tags = generate_hashtags(
            anthropic_client,
            post_type=decision.post_type,
            caption=caption,
            keywords=source.keywords,
        )
        image = image_fn(keywords=source.keywords, access_key=settings.unsplash_access_key)

        draft = Draft(
            id=str(uuid.uuid4()),
            post_type=decision.post_type,
            source_ref=source.source_ref,
            caption=caption,
            hashtags=format_hashtags(tags),
            image_url=image.url,
            image_credit=image.credit,
        )

        if dry_run:
            log.info("DRY RUN — caption:\n%s\nhashtags: %s", caption, draft.hashtags)
            return DraftResult(
                status="dry_run", post_type=decision.post_type, draft_id=draft.id
            )

        insert_draft(conn, draft)
        advance_after_draft(conn, decision)
        update_rotation_state(conn, last_day=today.isoformat())

        msg = build_draft_email(
            draft=draft,
            sender=settings.gmail_username,
            recipient=settings.gmail_recipient,
        )
        email_send_fn(msg)

        return DraftResult(
            status="drafted", post_type=decision.post_type, draft_id=draft.id
        )
    finally:
        conn.close()
```

- [ ] **Step 13.4: Run tests to verify pass**

```bash
pytest tests/unit/test_draft_pipeline.py -v
```

Expected: 3 passed.

- [ ] **Step 13.5: Commit**

```bash
git add src/agent/draft.py tests/unit/test_draft_pipeline.py
git commit -m "feat(draft): end-to-end draft pipeline (pick → claude → image → email)"
```

---

## Task 14: CLI entrypoint

**Files:**
- Create: `src/agent/__main__.py`

- [ ] **Step 14.1: Implement CLI**

```python
"""`python -m agent` dispatcher."""

from __future__ import annotations

import argparse
import sqlite3
import sys

from anthropic import Anthropic

from agent.config import load_settings
from agent.db.store import init_db, list_pending, update_draft_status
from agent.draft import run_draft
from agent.logging_setup import setup_logging


def _cmd_draft(args: argparse.Namespace) -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    client = Anthropic(api_key=settings.anthropic_api_key)
    result = run_draft(
        settings,
        anthropic_client=client,
        force=args.force,
        override_post_type=args.post_type,
        dry_run=args.dry_run,
    )
    print(f"status={result.status} post_type={result.post_type} draft_id={result.draft_id}")
    return 0 if result.status in ("drafted", "skipped", "dry_run") else 1


def _cmd_db_list_pending(_: argparse.Namespace) -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    conn = init_db(settings.db_path)
    try:
        for d in list_pending(conn):
            print(f"{d.id}\t{d.post_type}\t{d.source_ref}\t{d.expires_at}")
    finally:
        conn.close()
    return 0


def _cmd_db_expire(args: argparse.Namespace) -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    conn = init_db(settings.db_path)
    try:
        update_draft_status(conn, args.draft_id, "expired")
        print(f"marked {args.draft_id} expired")
    finally:
        conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    draft = sub.add_parser("draft", help="Generate today's draft.")
    draft.add_argument("--dry-run", action="store_true")
    draft.add_argument("--force", action="store_true")
    draft.add_argument("--post-type", choices=["project", "concept", "tip"])
    draft.set_defaults(func=_cmd_draft)

    db = sub.add_parser("db", help="Inspect the SQLite state.")
    db_sub = db.add_subparsers(dest="db_cmd", required=True)

    list_p = db_sub.add_parser("list-pending")
    list_p.set_defaults(func=_cmd_db_list_pending)

    expire_p = db_sub.add_parser("expire")
    expire_p.add_argument("draft_id")
    expire_p.set_defaults(func=_cmd_db_expire)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 14.2: Smoke-check CLI parser**

```bash
python -m agent --help
python -m agent draft --help
python -m agent db --help
```

Expected: usage strings; no tracebacks.

- [ ] **Step 14.3: Commit**

```bash
git add src/agent/__main__.py
git commit -m "feat(cli): python -m agent dispatcher for draft + db commands"
```

---

## Task 15: End-to-end dry run against real Anthropic + Unsplash

This is a **manual** validation step, not an automated test. The goal is to see real output before wiring up the cron.

- [ ] **Step 15.1: Populate `.env`**

```bash
cp .env.example .env
# Edit .env: fill ANTHROPIC_API_KEY, UNSPLASH_ACCESS_KEY, GMAIL_USERNAME, GMAIL_APP_PASSWORD
# (Gmail app password: myaccount.google.com → Security → 2-Step → App passwords)
```

- [ ] **Step 15.2: Dry-run for each post type**

```bash
python -m agent draft --dry-run --post-type=project --force
python -m agent draft --dry-run --post-type=concept --force
python -m agent draft --dry-run --post-type=tip --force
```

Expected: 3 distinct captions printed to logs, each 800–1300 chars, in Anuj's voice, citing real metrics from `master_profile.json`. If a caption sounds off, iterate on `VOICE_GUIDELINES` in `src/agent/generators/prompts.py` and rerun.

- [ ] **Step 15.3: One real run with email**

```bash
python -m agent draft --force --post-type=tip
```

Expected: the draft row lands in `db/state.sqlite` (verify with `python -m agent db list-pending`), and an email arrives at `GMAIL_RECIPIENT` with the formatted HTML body and an image preview.

- [ ] **Step 15.4: Commit (no code change; verifies state DB initialized)**

```bash
git add db/state.sqlite
git commit -m "chore(db): initialize state.sqlite after first run"
```

---

## Task 16: Lint + type CI workflow

**Files:**
- Create: `.github/workflows/test.yml`

- [ ] **Step 16.1: Implement workflow**

```yaml
name: test
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements-dev.txt
      - run: pip install -e .
      - run: ruff check src tests
      - run: ruff format --check src tests
      - run: mypy src
      - run: pytest
```

- [ ] **Step 16.2: Local sanity**

```bash
ruff check src tests
ruff format --check src tests
mypy src
pytest
```

Expected: all pass. Fix any ruff/mypy issues found.

- [ ] **Step 16.3: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: lint + type + test on push"
```

---

## Task 17: Daily cron workflow

**Files:**
- Create: `.github/workflows/draft.yml`

- [ ] **Step 17.1: Implement workflow**

```yaml
name: draft
on:
  schedule:
    - cron: "0 12 * * *"   # 12:00 UTC daily ≈ 08:00 ET (DST)
  workflow_dispatch:
jobs:
  draft:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - run: pip install -e .

      - name: Decode profile from secret
        env:
          PROFILE_B64: ${{ secrets.PROFILE_B64 }}
        run: |
          if [ -z "$PROFILE_B64" ]; then
            echo "PROFILE_B64 secret missing"; exit 1
          fi
          echo "$PROFILE_B64" | base64 -d > master_profile.json

      - name: Run draft
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          UNSPLASH_ACCESS_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}
          GMAIL_USERNAME: ${{ secrets.GMAIL_USERNAME }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          GMAIL_RECIPIENT: ${{ secrets.GMAIL_RECIPIENT }}
          PROFILE_PATH: ./master_profile.json
          DB_PATH: ./db/state.sqlite
          LOG_LEVEL: INFO
        run: python -m agent draft

      - name: Wipe decoded profile (defense in depth)
        if: always()
        run: rm -f master_profile.json

      - name: Commit updated state DB
        run: |
          git config user.name "linkedin-agent"
          git config user.email "noreply@anthropic.com"
          if git diff --quiet db/state.sqlite; then
            echo "no DB changes to commit"
          else
            git add db/state.sqlite
            git commit -m "chore(db): state after $(date -u +'%Y-%m-%dT%H:%MZ') draft"
            git push
          fi
```

- [ ] **Step 17.2: Verify workflow syntax**

```bash
# If `gh` is installed, lint the YAML by parsing it:
python -c "import yaml; yaml.safe_load(open('.github/workflows/draft.yml'))"
```

Expected: no exceptions.

- [ ] **Step 17.3: Commit**

```bash
git add .github/workflows/draft.yml
git commit -m "ci(cron): daily draft workflow at 12:00 UTC"
```

---

## Task 18: GitHub setup walkthrough (manual, doc the steps)

**Files:**
- Modify: `README.md` (append a "Deploy" section if not already there)

- [ ] **Step 18.1: Append deploy instructions to README**

Append the section below to `README.md`:

````markdown
## Deploy to GitHub Actions

1. Create a **private** GitHub repo (e.g. `linkedin-agent`). Push this code:

   ```
   git remote add origin git@github.com:<your-user>/linkedin-agent.git
   git push -u origin main
   ```

2. Generate a Gmail app password:
   `myaccount.google.com` → Security → 2-Step Verification → App passwords →
   create one for "Mail" → copy the 16-character password.

3. Get an Unsplash access key at `unsplash.com/developers` → New Application →
   copy the **Access Key** (not the Secret).

4. Base64-encode your real `master_profile.json` (do **not** commit it):

   ```
   base64 -i master_profile.json | tr -d '\n' | pbcopy
   ```

5. In the GitHub repo → Settings → Secrets and variables → Actions, add:
   - `ANTHROPIC_API_KEY`
   - `UNSPLASH_ACCESS_KEY`
   - `GMAIL_USERNAME` (e.g. `99anujbansal@gmail.com`)
   - `GMAIL_APP_PASSWORD` (the 16-character app password)
   - `GMAIL_RECIPIENT` (usually same as username)
   - `PROFILE_B64` (paste the base64 from step 4)

6. Trigger a manual run to verify everything wires up:
   Actions → "draft" → Run workflow → Run.

7. Watch the run; check your inbox for the draft email.

8. Once a manual run succeeds, the daily cron will fire automatically at
   12:00 UTC (≈ 08:00 ET).
````

- [ ] **Step 18.2: Commit**

```bash
git add README.md
git commit -m "docs(readme): GitHub Actions deploy walkthrough"
```

---

## Final verification pass

- [ ] **All unit tests pass:** `pytest` → all green.
- [ ] **Lint clean:** `ruff check src tests && ruff format --check src tests` → no findings.
- [ ] **Types clean:** `mypy src` → no errors.
- [ ] **Dry run produces a sensible caption in Anuj's voice for each of `project` / `concept` / `tip`** (manual eyeball).
- [ ] **One real run lands an email in the inbox** with image preview, caption, and hashtags.
- [ ] **Manual `workflow_dispatch` of `draft.yml` in GitHub Actions succeeds** end-to-end.
- [ ] **The committed `db/state.sqlite` reflects today's draft** after the run.
- [ ] **`master_profile.json` is NOT committed** (`git ls-files | grep master_profile.json` returns only the `.example.json`).

When all boxes are checked, Phase 1 is shipped. Phase 2 (Buffer + Cloudflare Worker approval) gets its own plan.
