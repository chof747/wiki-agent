from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ALLOWED_EXACT_PATHS = {
    "AGENTS.md",
    "CONTEXT.md",
    "config.example.toml",
}
ALLOWED_PREFIX = "docs/"
ZERO_SHA = "0" * 40


def is_docs_only_path(path: str) -> bool:
    normalized = path.strip()
    if not normalized:
        return False
    return normalized in ALLOWED_EXACT_PATHS or normalized.startswith(ALLOWED_PREFIX)


def classify_paths(paths: list[str]) -> bool:
    return bool(paths) and all(is_docs_only_path(path) for path in paths)


def classify_diff_lines(lines: list[str]) -> bool:
    if not lines:
        return False

    for line in lines:
        parts = line.split("\t")
        if len(parts) < 2:
            return False

        status = parts[0]
        if status.startswith(("R", "C")):
            if len(parts) != 3:
                return False
            if not classify_paths([parts[1], parts[2]]):
                return False
            continue

        if len(parts) != 2:
            return False
        if not is_docs_only_path(parts[1]):
            return False

    return True


def read_event_range(event_name: str, event: dict[str, object]) -> tuple[str, str] | None:
    if event_name == "pull_request":
        pull_request = event.get("pull_request")
        if not isinstance(pull_request, dict):
            return None
        base = _read_nested_sha(pull_request, "base")
        head = _read_nested_sha(pull_request, "head")
        return (base, head) if base and head else None

    if event_name == "push":
        before = event.get("before")
        after = event.get("after")
        if not isinstance(before, str) or not isinstance(after, str):
            return None
        if not before or not after or before == ZERO_SHA or after == ZERO_SHA:
            return None
        return before, after

    return None


def _read_nested_sha(container: dict[str, object], key: str) -> str | None:
    value = container.get(key)
    if not isinstance(value, dict):
        return None
    sha = value.get("sha")
    return sha if isinstance(sha, str) and sha else None


def run_diff(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-status", "--find-renames", base, head],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def classify_event(event_name: str, event_path: Path) -> bool:
    if event_name == "workflow_dispatch":
        return False

    event = json.loads(event_path.read_text(encoding="utf-8"))
    diff_range = read_event_range(event_name, event)
    if diff_range is None:
        return False

    base, head = diff_range
    return classify_diff_lines(run_diff(base, head))


def _write_result(docs_only: bool, github_output: Path | None) -> None:
    payload = {"docs_only": docs_only}
    print(json.dumps(payload))
    if github_output is not None:
        github_output.write_text(f"docs_only={'true' if docs_only else 'false'}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify_paths_parser = subparsers.add_parser("classify-paths")
    classify_paths_parser.add_argument("paths", nargs="+")

    from_event_parser = subparsers.add_parser("from-github-event")
    from_event_parser.add_argument("event_name")
    from_event_parser.add_argument("event_path", type=Path)
    from_event_parser.add_argument("--github-output", type=Path)

    args = parser.parse_args(argv)

    if args.command == "classify-paths":
        _write_result(classify_paths(args.paths), None)
        return 0

    try:
        docs_only = classify_event(args.event_name, args.event_path)
    except (json.JSONDecodeError, OSError, subprocess.CalledProcessError):
        docs_only = False

    _write_result(docs_only, args.github_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
