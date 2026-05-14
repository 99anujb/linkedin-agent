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
