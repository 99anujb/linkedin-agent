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


def _career_source(profile: Profile, sub_key: str | None) -> SourceContent:
    """Build source content from achievements + education + degree pivot."""
    if not profile.achievements:
        # Fallback: use education only.
        edu = profile.education[0] if profile.education else None
        title = f"{edu.degree} @ {edu.school}" if edu else "My career journey"
        body = (
            f"Pursuing {edu.degree} ({edu.start} - {edu.end}, GPA {edu.gpa}). "
            f"Coursework: {', '.join(edu.coursework)}."
            if edu
            else "Sharing a moment from my career journey."
        )
        return SourceContent(
            title=title,
            body=body,
            keywords=["career", "data science", "graduate school"],
            source_ref="career:education",
        )

    # Pick achievement by sub_key (format "achv_<idx>"), else first.
    idx = 0
    if sub_key and sub_key.startswith("achv_"):
        try:
            idx = int(sub_key.split("_", 1)[1])
        except ValueError:
            idx = 0
    idx = idx % len(profile.achievements)
    achievement = profile.achievements[idx]

    # Append supporting context: current degree + the Mech-Eng → DS pivot.
    edu_lines: list[str] = []
    for edu in profile.education:
        edu_lines.append(f"{edu.degree} at {edu.school} ({edu.start} - {edu.end})")
    edu_context = " | ".join(edu_lines) if edu_lines else ""

    body = (
        f"Achievement to highlight: {achievement}\n\n"
        f"Supporting context (use only if relevant): {edu_context}\n\n"
        f"Pivot story (use only if it adds depth): I trained as a Mechanical Engineer "
        f"(B.Tech) and pivoted into data science via the MS program at UMass Dartmouth."
    )
    return SourceContent(
        title="Career milestone",
        body=body,
        keywords=["career", "data science", "graduate school", "career pivot"],
        source_ref=f"career:{sub_key or f'achv_{idx}'}",
    )


def build_source(decision: RotationDecision, profile: Profile) -> SourceContent:
    if decision.post_type == "project":
        return _project_source(profile, decision.sub_key)
    if decision.post_type == "concept":
        return _concept_source(profile, decision.sub_key)
    if decision.post_type == "career":
        return _career_source(profile, decision.sub_key)
    raise ValueError(f"Unsupported post type: {decision.post_type}")
