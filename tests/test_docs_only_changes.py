from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools import docs_only_changes


def test_classify_paths_accepts_exact_docs_only_allowlist() -> None:
    assert docs_only_changes.classify_paths(
        [
            "docs/design/integration-harness.md",
            "AGENTS.md",
            "CONTEXT.md",
            "config.example.toml",
        ]
    )


def test_classify_paths_rejects_non_doc_paths() -> None:
    assert not docs_only_changes.classify_paths(
        ["docs/design/integration-harness.md", "src/wiki_agent/runner.py"]
    )


def test_classify_diff_lines_accepts_docs_only_rename_within_allowlist() -> None:
    assert docs_only_changes.classify_diff_lines(
        ["R100\tdocs/old.md\tdocs/new.md", "M\tAGENTS.md"]
    )


def test_classify_diff_lines_rejects_rename_crossing_docs_boundary() -> None:
    assert not docs_only_changes.classify_diff_lines(
        ["R100\tdocs/old.md\tsrc/wiki_agent/runner.py"]
    )


def test_classify_diff_lines_rejects_empty_change_set() -> None:
    assert not docs_only_changes.classify_diff_lines([])


def test_read_event_range_for_pull_request() -> None:
    event = {"pull_request": {"base": {"sha": "base"}, "head": {"sha": "head"}}}

    assert docs_only_changes.read_event_range("pull_request", event) == ("base", "head")


def test_read_event_range_for_push() -> None:
    event = {"before": "base", "after": "head"}

    assert docs_only_changes.read_event_range("push", event) == ("base", "head")


def test_read_event_range_rejects_missing_sha_context() -> None:
    assert docs_only_changes.read_event_range("push", {"before": "", "after": "head"}) is None


def test_cli_classify_paths_reports_docs_only(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = docs_only_changes.main(
        ["classify-paths", "docs/design/integration-harness.md", "AGENTS.md"]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"docs_only": True}


def test_cli_from_github_event_reports_fail_closed_when_diff_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"base": {"sha": "base"}, "head": {"sha": "head"}}}),
        encoding="utf-8",
    )

    def fake_run_diff(base: str, head: str) -> list[str]:
        raise subprocess.CalledProcessError(1, ["git", "diff", base, head])

    monkeypatch.setattr(docs_only_changes, "run_diff", fake_run_diff)

    exit_code = docs_only_changes.main(
        ["from-github-event", "pull_request", str(event_path)]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"docs_only": False}
