from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from wiki_agent import environment


UV_CACHE_DIR = "/private/tmp/uv-cache"
LOCAL_STATE_NAMES = (".env", ".runtime", ".vscode")


@dataclass(frozen=True)
class WorktreeResult:
    branch: str
    path: Path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = resolve_repo_root()
    environment.load_repo_environment(repo_root=repo_root)

    if args.command == "create":
        result = create_worktree(args.issue_number, repo_root=repo_root)
        print(f"Created {result.branch} at {result.path}")
        return 0

    if args.command == "delete":
        result = delete_worktree(args.issue_number, repo_root=repo_root)
        print(f"Removed {result.path} and kept {result.branch}")
        return 0

    parser.error("unsupported command")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wiki-agent-worktree")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("issue_number", type=int)

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("issue_number", type=int)
    return parser


def create_worktree(issue_number: int, *, repo_root: Path | None = None) -> WorktreeResult:
    control_root = repo_root or resolve_repo_root()
    ensure_control_checkout_ready(control_root)
    issue = read_issue(issue_number, cwd=control_root)
    ensure_issue_ready(issue_number, issue)
    branch = canonical_branch_name(issue_number, issue)
    path = worktree_path_for_issue(control_root, issue_number)
    if path.exists():
        raise SystemExit(f"worktree already exists at {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    run_command(["git", "worktree", "add", "-b", branch, str(path), "HEAD"], cwd=control_root)
    copy_local_state(control_root, path)
    run_command(["uv", "sync", "--locked", "--dev"], cwd=path)
    run_command(
        ["uv", "run", "wiki-agent-integration", "reset"],
        cwd=path,
        env=uv_env(),
    )
    run_command(
        ["uv", "run", "wiki-agent-integration", "down"],
        cwd=path,
        env=uv_env(),
    )
    return WorktreeResult(branch=branch, path=path)


def delete_worktree(issue_number: int, *, repo_root: Path | None = None) -> WorktreeResult:
    control_root = repo_root or resolve_repo_root()
    path = worktree_path_for_issue(control_root, issue_number)
    branch = registered_worktree_branch(control_root, path)
    ensure_worktree_clean(path)
    ensure_pull_request_exists(branch, cwd=control_root)
    best_effort_harness_down(path)
    run_command(["git", "worktree", "remove", str(path)], cwd=control_root)
    return WorktreeResult(branch=branch, path=path)


def resolve_repo_root() -> Path:
    stdout = run_command(["git", "rev-parse", "--show-toplevel"], cwd=Path.cwd())
    return Path(stdout.strip())


def ensure_control_checkout_ready(repo_root: Path) -> None:
    status = run_command(["git", "status", "--short"], cwd=repo_root)
    if status.strip():
        raise SystemExit("control checkout must be clean before creating an issue worktree")

    branch = run_command(["git", "branch", "--show-current"], cwd=repo_root).strip()
    if branch != "main":
        raise SystemExit("control checkout must be on main")

    run_command(["git", "fetch", "origin", "main"], cwd=repo_root)
    head = run_command(["git", "rev-parse", "HEAD"], cwd=repo_root).strip()
    origin_main = run_command(["git", "rev-parse", "refs/remotes/origin/main"], cwd=repo_root).strip()
    if head != origin_main:
        raise SystemExit("control checkout main must be up to date with origin/main")


def read_issue(issue_number: int, *, cwd: Path) -> dict[str, object]:
    stdout = run_command(
        ["gh", "issue", "view", str(issue_number), "--json", "number,state,title,labels"],
        cwd=cwd,
    )
    return json.loads(stdout)


def ensure_issue_ready(issue_number: int, issue: dict[str, object]) -> None:
    if str(issue.get("state", "")).upper() != "OPEN":
        raise SystemExit(f"issue {issue_number} must be open")

    labels = {str(label.get("name", "")) for label in issue.get("labels", []) if isinstance(label, dict)}
    if "ready-for-agent" not in labels:
        raise SystemExit(f"issue {issue_number} must be labeled ready-for-agent")


def canonical_branch_name(issue_number: int, issue: dict[str, object]) -> str:
    labels = {str(label.get("name", "")) for label in issue.get("labels", []) if isinstance(label, dict)}
    prefix = "bug" if "bug" in labels else "feat"
    slug = slugify(str(issue.get("title", "issue")))
    return f"{prefix}/{issue_number}-{slug}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "issue"


def worktree_path_for_issue(repo_root: Path, issue_number: int) -> Path:
    return repo_root.parent / f"{repo_root.name}-worktrees" / f"{repo_root.name}-{issue_number}"


def copy_local_state(source_root: Path, destination_root: Path) -> None:
    for name in LOCAL_STATE_NAMES:
        source = source_root / name
        if not source.exists():
            continue

        destination = destination_root / name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def registered_worktree_branch(repo_root: Path, worktree_path: Path) -> str:
    entries = parse_worktree_list(run_command(["git", "worktree", "list", "--porcelain"], cwd=repo_root))
    branch = entries.get(worktree_path.resolve())
    if branch is None:
        raise SystemExit(f"no registered worktree found for issue path {worktree_path}")
    return branch


def parse_worktree_list(stdout: str) -> dict[Path, str]:
    entries: dict[Path, str] = {}
    current_path: Path | None = None
    for line in stdout.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree ")).resolve()
            continue
        if line.startswith("branch refs/heads/") and current_path is not None:
            entries[current_path] = line.removeprefix("branch refs/heads/")
    return entries


def ensure_worktree_clean(worktree_path: Path) -> None:
    status = run_command(["git", "status", "--short"], cwd=worktree_path)
    if status.strip():
        raise SystemExit(f"worktree {worktree_path} has meaningful dirty state")


def ensure_pull_request_exists(branch: str, *, cwd: Path) -> None:
    stdout = run_command(["gh", "pr", "list", "--head", branch, "--json", "number,url"], cwd=cwd)
    pull_requests = json.loads(stdout)
    if not pull_requests:
        raise SystemExit(f"no pull request exists for branch {branch}")


def best_effort_harness_down(worktree_path: Path) -> None:
    result = subprocess.run(
        ["uv", "run", "wiki-agent-integration", "down"],
        cwd=worktree_path,
        env=uv_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "unknown error"
        print(f"warning: harness shutdown failed: {detail}", file=sys.stderr)


def uv_env() -> dict[str, str]:
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = UV_CACHE_DIR
    return env


def run_command(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"command failed: {' '.join(argv)}"
        raise SystemExit(detail)
    return result.stdout
