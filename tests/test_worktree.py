from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools import worktree


def test_create_defaults_to_main_and_bootstraps_worktree(
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
    expected_path = repo_root.parent / "wiki-agent-worktrees" / "wiki-agent-71"

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = list(args[0])
        cwd = Path(kwargs.get("cwd", repo_root))
        uv_cache_dir = None if kwargs.get("env") is None else kwargs["env"].get("UV_CACHE_DIR")
        observed.append((argv, cwd, uv_cache_dir))

        if argv == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "fetch", "origin", "main"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
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
        if argv == [
            "git",
            "worktree",
            "add",
            "-b",
            "feat/71-add-issue-scoped-worktree-workflow-tooling-and-local-enforcement",
            str(expected_path),
            "origin/main",
        ]:
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
    assert result.path == expected_path
    assert (result.path / ".env").read_text(encoding="utf-8") == "OPENAI_API_KEY=test\n"
    assert (result.path / ".runtime" / "state.json").read_text(encoding="utf-8") == "{}\n"
    assert (result.path / ".vscode" / "settings.json").read_text(encoding="utf-8") == "{}\n"
    assert observed[:3] == [
        (["git", "status", "--short"], repo_root, None),
        (["git", "fetch", "origin", "main"], repo_root, None),
        (["gh", "issue", "view", "71", "--json", "number,state,title,labels"], repo_root, None),
    ]
    assert observed[-3:] == [
        (["uv", "sync", "--locked", "--dev"], result.path, None),
        (["uv", "run", "wiki-agent-integration", "reset"], result.path, worktree.UV_CACHE_DIR),
        (["uv", "run", "wiki-agent-integration", "down"], result.path, worktree.UV_CACHE_DIR),
    ]


def test_create_supports_explicit_release_base_from_clean_non_main_control_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "wiki-agent"
    repo_root.mkdir()

    monkeypatch.setattr(worktree, "resolve_repo_root", lambda: repo_root)

    observed: list[list[str]] = []
    expected_path = repo_root.parent / "wiki-agent-worktrees" / "wiki-agent-71"

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = list(args[0])
        observed.append(argv)

        if argv == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "fetch", "origin", "release/test-release"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
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
        if argv == [
            "git",
            "worktree",
            "add",
            "-b",
            "feat/71-add-issue-scoped-worktree-workflow-tooling-and-local-enforcement",
            str(expected_path),
            "origin/release/test-release",
        ]:
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

    result = worktree.create_worktree(71, repo_root=repo_root, base="release/test-release")

    assert result.path == expected_path
    assert observed[:3] == [
        ["git", "status", "--short"],
        ["git", "fetch", "origin", "release/test-release"],
        ["gh", "issue", "view", "71", "--json", "number,state,title,labels"],
    ]


@pytest.mark.parametrize("base", ["origin/release/test-release", "release/Test-Release", "feature/test"])
def test_create_rejects_invalid_base_names(base: str) -> None:
    with pytest.raises(SystemExit, match="base"):
        worktree.create_worktree(71, repo_root=Path("/tmp/repo"), base=base)


def test_create_fails_fast_when_remote_base_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "wiki-agent"
    repo_root.mkdir()

    monkeypatch.setattr(worktree, "resolve_repo_root", lambda: repo_root)

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = list(args[0])
        if argv == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "fetch", "origin", "release/missing-release"]:
            return subprocess.CompletedProcess(argv, 128, stdout="", stderr="fatal: couldn't find remote ref release/missing-release")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(worktree.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match=r"failed to fetch origin/release/missing-release"):
        worktree.create_worktree(71, repo_root=repo_root, base="release/missing-release")


def test_create_requires_clean_control_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "wiki-agent"
    repo_root.mkdir()

    monkeypatch.setattr(worktree, "resolve_repo_root", lambda: repo_root)

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = list(args[0])
        if argv == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(argv, 0, stdout=" M tools/worktree.py\n", stderr="")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(worktree.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match="control checkout must be clean"):
        worktree.create_worktree(71)


def test_create_requires_ready_for_agent_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "wiki-agent"
    repo_root.mkdir()

    monkeypatch.setattr(worktree, "resolve_repo_root", lambda: repo_root)

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = list(args[0])
        if argv == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "fetch", "origin", "main"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
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


def test_create_surfaces_existing_branch_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "wiki-agent"
    repo_root.mkdir()
    expected_path = repo_root.parent / "wiki-agent-worktrees" / "wiki-agent-71"

    monkeypatch.setattr(worktree, "resolve_repo_root", lambda: repo_root)

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = list(args[0])
        if argv == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "fetch", "origin", "main"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
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
        if argv == [
            "git",
            "worktree",
            "add",
            "-b",
            "feat/71-add-issue-scoped-worktree-workflow-tooling-and-local-enforcement",
            str(expected_path),
            "origin/main",
        ]:
            return subprocess.CompletedProcess(argv, 128, stdout="", stderr="fatal: a branch named 'feat/71-add-issue-scoped-worktree-workflow-tooling-and-local-enforcement' already exists")

        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(worktree.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match="already exists"):
        worktree.create_worktree(71)


def test_create_fails_when_worktree_path_already_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "wiki-agent"
    repo_root.mkdir()
    worktree_path = repo_root.parent / "wiki-agent-worktrees" / "wiki-agent-71"
    worktree_path.mkdir(parents=True)

    monkeypatch.setattr(worktree, "resolve_repo_root", lambda: repo_root)

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = list(args[0])
        if argv == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv == ["git", "fetch", "origin", "main"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
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
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(worktree.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match="worktree already exists"):
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
    expected_container_name = worktree.integration_harness_container_name(worktree_path)

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
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
        if argv == ["docker", "rm", "-f", expected_container_name]:
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
    assert observed[-3:] == [
        (["uv", "run", "wiki-agent-integration", "down"], worktree_path),
        (["docker", "rm", "-f", expected_container_name], worktree_path),
        (["git", "worktree", "remove", str(worktree_path)], repo_root),
    ]


def test_delete_ignores_missing_scoped_harness_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "wiki-agent"
    repo_root.mkdir()
    worktree_path = repo_root.parent / "wiki-agent-worktrees" / "wiki-agent-71"
    worktree_path.mkdir(parents=True)
    expected_container_name = worktree.integration_harness_container_name(worktree_path)

    monkeypatch.setattr(worktree, "resolve_repo_root", lambda: repo_root)

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = list(args[0])

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
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="harness unavailable")
        if argv == ["docker", "rm", "-f", expected_container_name]:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Error: No such container")
        if argv == ["git", "worktree", "remove", str(worktree_path)]:
            shutil.rmtree(worktree_path)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(worktree.subprocess, "run", fake_run)

    result = worktree.delete_worktree(71)

    assert result.path == worktree_path
    assert not worktree_path.exists()
