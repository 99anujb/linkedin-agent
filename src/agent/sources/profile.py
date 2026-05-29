"""Build source content from the profile for a given rotation decision."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from agent.profile_model import Profile
from agent.rotation import RotationDecision
from agent.sources.rss import Headline, pick_fresh_headline


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


def _trending_source(headline: Headline, profile: Profile) -> SourceContent:
    """Build a trending post around a fresh AI/data-science headline."""
    role_focus = ", ".join(profile.role_targets[:2]) or "data professionals"
    body = (
        f"Trending headline (treat as your starting point, not the whole post):\n"
        f"  Title: {headline.title}\n"
        f"  Source: {headline.source}\n"
        f"  Summary: {headline.summary[:600]}\n\n"
        f"Goal: open with a punchy hook that names what is new (or what matters), "
        f"explain why it matters in plain language for {role_focus} who follow "
        f"the data / AI space, and connect it to one concrete implication for "
        f"the reader's day-to-day. Do NOT just summarize the article. Add your "
        f"perspective. Do not paste the article link inline."
    )
    return SourceContent(
        title=headline.title[:120],
        body=body,
        keywords=["AI", "trending", "data science", "machine learning", headline.source],
        source_ref=f"trending:{headline.hash}",
    )


def _news_take_source(headline: Headline, profile: Profile) -> SourceContent:
    """Hot-take framing on a fresh headline."""
    body = (
        f"News headline to react to:\n"
        f"  Title: {headline.title}\n"
        f"  Source: {headline.source}\n"
        f"  Summary: {headline.summary[:600]}\n\n"
        f"Goal: pick a clear stance (agree / disagree / unexpected angle), give "
        f"2-3 reasons grounded in data / analytics / ML practice, and invite "
        f"counterpoints from the reader. Stay respectful, never inflammatory. "
        f"Do not paste the article link inline."
    )
    return SourceContent(
        title=f"Hot take: {headline.title[:100]}",
        body=body,
        keywords=["AI news", "industry take", "data science", headline.source],
        source_ref=f"news_take:{headline.hash}",
    )


def _tutorial_source(profile: Profile, sub_key: str | None) -> SourceContent:
    """Pick a skill category and frame as a short hands-on tutorial."""
    cat = sub_key if sub_key and sub_key in profile.skills else next(iter(profile.skills.keys()))
    items = profile.skills[cat]
    body = (
        f"Skill category: {cat}. Items I have hands-on experience with: "
        f"{', '.join(items)}.\n\n"
        f"Goal: pick ONE concrete technique or tool from this list and teach it "
        f"in a short 'do this, not that' format. Include one tiny example "
        f"(SQL/Python/idea) the reader can copy. Keep it scannable on mobile."
    )
    return SourceContent(
        title=f"Tutorial: {cat.replace('_', ' ').title()}",
        body=body,
        keywords=[cat, *items[:5], "tutorial", "how-to"],
        source_ref=f"tutorial:{cat}",
    )


def _roadmap_source(profile: Profile, sub_key: str | None) -> SourceContent:
    """Roadmap post targeted at one of the user's role targets."""
    role = (
        sub_key
        if sub_key in (profile.role_targets or [])
        else (profile.role_targets[0] if profile.role_targets else "Data Scientist")
    )
    skill_keys = list(profile.skills.keys())
    body = (
        f"Audience: someone trying to break into {role} in the US.\n"
        f"Anchor skills I can speak to (use sparingly, only what fits the roadmap): "
        f"{', '.join(skill_keys)}.\n\n"
        f"Goal: produce a tight 30/60/90 day roadmap OR a 4-step framework that "
        f"a beginner can follow. Each step short, concrete, and free or near-free "
        f"to start. End with a CTA inviting the reader to share their own path."
    )
    return SourceContent(
        title=f"Roadmap: how to break into {role}",
        body=body,
        keywords=[role, "roadmap", "career growth", "learning path", "data science"],
        source_ref=f"roadmap:{role.lower().replace(' ', '_')}",
    )


def build_source(
    decision: RotationDecision,
    profile: Profile,
    *,
    conn: sqlite3.Connection | None = None,
) -> SourceContent:
    if decision.post_type == "project":
        return _project_source(profile, decision.sub_key)
    if decision.post_type == "concept":
        return _concept_source(profile, decision.sub_key)
    if decision.post_type == "career":
        return _career_source(profile, decision.sub_key)
    if decision.post_type == "tutorial":
        return _tutorial_source(profile, decision.sub_key)
    if decision.post_type == "roadmap":
        return _roadmap_source(profile, decision.sub_key)
    if decision.post_type in ("trending", "news_take"):
        if conn is None:
            raise ValueError(
                f"{decision.post_type} source needs a DB connection for headline dedup"
            )
        headline = pick_fresh_headline(conn)
        if headline is None:
            # No fresh headline available — fall back to a concept source so
            # the day still produces a post.
            return _concept_source(profile, sub_key=None)
        if decision.post_type == "trending":
            return _trending_source(headline, profile)
        return _news_take_source(headline, profile)
    raise ValueError(f"Unsupported post type: {decision.post_type}")
