"""Stage, commit, and push artifact files from inside the agent."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path

log = logging.getLogger(__name__)


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def commit_and_push(paths: Iterable[Path], *, message: str) -> None:
    """Commit and push the given files. No-op when CI env var is unset."""
    if not os.environ.get("CI"):
        log.info("commit_and_push: CI unset, skipping (paths=%s)", list(paths))
        return
    path_strs = [str(p) for p in paths]
    _run(["git", "config", "user.name", "linkedin-agent"])
    _run(["git", "config", "user.email", "noreply@anthropic.com"])
    _run(["git", "add", *path_strs])
    commit_res = _run(["git", "commit", "-m", message])
    if commit_res.returncode != 0:
        if "nothing to commit" in (commit_res.stdout + commit_res.stderr).lower():
            log.info("commit_and_push: nothing to commit")
            return
        log.warning(
            "commit_and_push: commit failed (rc=%s): %s",
            commit_res.returncode,
            commit_res.stderr,
        )
        return
    push_res = _run(["git", "push", "origin", "HEAD"])
    if push_res.returncode != 0:
        log.warning("commit_and_push: push failed: %s", push_res.stderr)
