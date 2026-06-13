from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import worktree


def test_create_copies_local_state_and_bootstraps_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "wiki-agent"
    repo_root.mkdir()
    (repo_root / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
    (repo_root / ".runtime").mkdir()
    (repo_root / ".runtime" / "state.json").write_text("{}\n", encoding="utf-8")
    (repo_root / ".vscode").mkdir()
    (repo_root / ".vscode" / "settings.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(worktree, "resolve_repo_root", lambda: repo_root)

    observed: list[tuple[list[str], Path, str | None]] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        argv = list(args[0])
        cwd = Path(kwargs.get("cwd", repo_root))
        uv_cache_dir = None if kwargs.get("env") is None else kwargs["env"].get("UV_CACHE_DIR")
        observed.append((argv, cwd, uv_cache_dir))

        if argv == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(argv, 0, stdout="main\n", stderr="")
        if argv == ["git", "fetch", "origin", "main"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(argv, 0, stdout="abc123\n", stderr="")
        if argv == ["git", "rev-parse", "refs/remotes/origin/main"]:
            return subprocess.CompletedProcess(argv, 0, stdout="abc123\n", stderr="")
        if argv[:4] == ["gh", "issue", "view", "71"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        "number": 71,
                        "state": "OPEN",
                        "title": "Add issue-scoped worktree workflow tooling and local enforcement",
                        "labels": [{"name": "enhancement"}, {"name": "ready-for-agent"}],
                    }
                ),
                stderr="",
            )
        if argv[:4] == ["git", "worktree", "add", "-b"]:
            Path(argv[5]).mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["uv", "sync", "--locked", "--dev"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["uv", "run", "wiki-agent-integration", "reset"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["uv", "run", "wiki-agent-integration", "down"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(worktree.subprocess, "run", fake_run)

    result = worktree.create_worktree(71)

    assert result.branch == "feat/71-add-issue-scoped-worktree-workflow-tooling-and-local-enforcement"
    assert result.path == repo_root.parent / "wiki-agent-worktrees" / "wiki-agent-71"
    assert (result.path / ".env").read_text(encoding="utf-8") == "OPENAI_API_KEY=test\n"
    assert (result.path / ".runtime" / "state.json").read_text(encoding="utf-8") == "{}\n"
    assert (result.path / ".vscode" / "settings.json").read_text(encoding="utf-8") == "{}\n"
    assert observed[-3:] == [
        (["uv", "sync", "--locked", "--dev"], result.path, None),
        (["uv", "run", "wiki-agent-integration", "reset"], result.path, worktree.UV_CACHE_DIR),
        (["uv", "run", "wiki-agent-integration", "down"], result.path, worktree.UV_CACHE_DIR),
    ]


def test_create_requires_ready_for_agent_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "wiki-agent"
    repo_root.mkdir()

    monkeypatch.setattr(worktree, "resolve_repo_root", lambda: repo_root)

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        argv = list(args[0])
        if argv == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(argv, 0, stdout="main\n", stderr="")
        if argv == ["git", "fetch", "origin", "main"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(argv, 0, stdout="abc123\n", stderr="")
        if argv == ["git", "rev-parse", "refs/remotes/origin/main"]:
            return subprocess.CompletedProcess(argv, 0, stdout="abc123\n", stderr="")
        if argv[:4] == ["gh", "issue", "view", "71"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        "number": 71,
                        "state": "OPEN",
                        "title": "Needs triage first",
                        "labels": [{"name": "needs-triage"}],
                    }
                ),
                stderr="",
            )

        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(worktree.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match="ready-for-agent"):
        worktree.create_worktree(71)


def test_delete_requires_pr_and_removes_registered_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "wiki-agent"
    repo_root.mkdir()
    worktree_path = repo_root.parent / "wiki-agent-worktrees" / "wiki-agent-71"
    worktree_path.mkdir(parents=True)

    monkeypatch.setattr(worktree, "resolve_repo_root", lambda: repo_root)

    observed: list[tuple[list[str], Path]] = []

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        argv = list(args[0])
        cwd = Path(kwargs.get("cwd", repo_root))
        observed.append((argv, cwd))

        if argv == ["git", "worktree", "list", "--porcelain"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=(
                    f"worktree {repo_root}\n"
                    "HEAD abc123\n"
                    "branch refs/heads/main\n\n"
                    f"worktree {worktree_path}\n"
                    "HEAD def456\n"
                    "branch refs/heads/feat/71-add-issue-scoped-worktree-workflow-tooling-and-local-enforcement\n"
                ),
                stderr="",
            )
        if argv == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(argv, 0, stdout="feat/71-add-issue-scoped-worktree-workflow\n", stderr="")
        if argv == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv[:4] == ["gh", "pr", "list", "--head"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    [{"number": 91, "url": "https://github.com/chof747/wiki-agent/pull/91"}]
                ),
                stderr="",
            )
        if argv == ["uv", "run", "wiki-agent-integration", "down"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "worktree", "remove", str(worktree_path)]:
            shutil.rmtree(worktree_path)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(worktree.subprocess, "run", fake_run)

    result = worktree.delete_worktree(71)

    assert result.branch == "feat/71-add-issue-scoped-worktree-workflow-tooling-and-local-enforcement"
    assert result.path == worktree_path
    assert not worktree_path.exists()
    assert observed[-2:] == [
        (["uv", "run", "wiki-agent-integration", "down"], worktree_path),
        (["git", "worktree", "remove", str(worktree_path)], repo_root),
    ]
