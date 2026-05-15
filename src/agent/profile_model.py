"""Pydantic model of master_profile.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    constraints: dict[str, Any]
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
