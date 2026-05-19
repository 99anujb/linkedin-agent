from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.delivery.git_publish import commit_and_push


def test_commit_and_push_is_noop_when_ci_unset(monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    with patch("agent.delivery.git_publish.subprocess.run") as run:
        commit_and_push([Path("db/images/x.png")], message="m")
    run.assert_not_called()


def test_commit_and_push_runs_git_commands_when_ci_set(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    paths = [Path("db/images/a.png"), Path("db/images/b.png")]
    with patch("agent.delivery.git_publish.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        commit_and_push(paths, message="add cards")
    calls = [c.args[0] for c in run.call_args_list]
    assert calls[0] == [
        "git",
        "config",
        "user.name",
        "linkedin-agent",
    ]
    assert calls[1] == [
        "git",
        "config",
        "user.email",
        "noreply@anthropic.com",
    ]
    assert calls[2] == ["git", "add", "db/images/a.png", "db/images/b.png"]
    assert calls[3] == ["git", "commit", "-m", "add cards"]
    assert calls[4] == ["git", "push", "origin", "HEAD"]


def test_commit_and_push_swallows_nothing_to_commit(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    with patch("agent.delivery.git_publish.subprocess.run") as run:
        outputs = iter(
            [
                MagicMock(returncode=0),  # config name
                MagicMock(returncode=0),  # config email
                MagicMock(returncode=0),  # add
                MagicMock(returncode=1, stdout="nothing to commit", stderr=""),
            ]
        )
        run.side_effect = lambda *a, **kw: next(outputs)
        commit_and_push([Path("db/images/a.png")], message="m")
    # push is skipped when commit yielded nothing
    last_call = run.call_args_list[-1].args[0]
    assert last_call[1] == "commit"
