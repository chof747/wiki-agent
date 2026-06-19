from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from textwrap import dedent

import pytest

from wiki_agent.comment_jobs import CommentJob
from wiki_agent.runner_client import RunnerClient, RunnerCommand, RunnerInvocationError


def test_runner_client_sends_prompt_envelope_and_parses_stdout(tmp_path: Path) -> None:
    capture_path = tmp_path / "stdin.json"
    runner = _write_runner(
        tmp_path / "runner_success.py",
        f"""
        import json
        import pathlib
        import sys

        payload = json.load(sys.stdin)
        pathlib.Path({str(capture_path)!r}).write_text(json.dumps(payload, sort_keys=True))
        sys.stderr.write("diagnostic line\\n")
        sys.stdout.write(json.dumps({{"status": "SUCCESS", "updated": True}}))
        """,
    )

    client = RunnerClient(RunnerCommand(argv=(str(runner),)))
    response = client.invoke(_job())

    assert response.status == "SUCCESS"
    assert response.payload["updated"] is True
    assert response.stderr == "diagnostic line\n"

    payload = json.loads(capture_path.read_text())
    assert payload == {
        "comment_identity": "comment-1",
        "original_comment_text": "@marvin tighten intro",
        "prompt": "tighten intro",
        "target_page": "/pages/example",
    }


def test_runner_client_maps_non_zero_exit_to_failure(tmp_path: Path) -> None:
    runner = _write_runner(
        tmp_path / "runner_non_zero.py",
        """
        import sys

        sys.stderr.write("boom\\n")
        raise SystemExit(7)
        """,
    )

    client = RunnerClient(RunnerCommand(argv=(str(runner),)))

    with pytest.raises(RunnerInvocationError, match="runner exited with 7: boom"):
        client.invoke(_job())


def test_runner_client_rejects_invalid_json_stdout(tmp_path: Path) -> None:
    runner = _write_runner(
        tmp_path / "runner_invalid_json.py",
        """
        import sys

        sys.stdout.write("{not json}")
        """,
    )

    client = RunnerClient(RunnerCommand(argv=(str(runner),)))

    with pytest.raises(RunnerInvocationError, match="invalid JSON"):
        client.invoke(_job())


def test_runner_client_rejects_missing_finalized_response(tmp_path: Path) -> None:
    runner = _write_runner(
        tmp_path / "runner_empty_stdout.py",
        """
        pass
        """,
    )

    client = RunnerClient(RunnerCommand(argv=(str(runner),)))

    with pytest.raises(RunnerInvocationError, match="did not emit a finalized response"):
        client.invoke(_job())


def test_runner_client_rejects_invalid_status_code(tmp_path: Path) -> None:
    runner = _write_runner(
        tmp_path / "runner_invalid_status.py",
        """
        import json
        import sys

        sys.stdout.write(json.dumps({"status": "NOT_A_REAL_STATUS"}))
        """,
    )

    client = RunnerClient(RunnerCommand(argv=(str(runner),)))

    with pytest.raises(RunnerInvocationError, match="invalid status"):
        client.invoke(_job())


def test_runner_client_maps_timeout_to_failure(tmp_path: Path) -> None:
    runner = _write_runner(
        tmp_path / "runner_timeout.py",
        """
        import time

        time.sleep(0.2)
        """,
    )

    client = RunnerClient(
        RunnerCommand(argv=(str(runner),)),
        timeout=timedelta(milliseconds=50),
    )

    with pytest.raises(RunnerInvocationError, match="timed out"):
        client.invoke(_job())


def _job() -> CommentJob:
    scanned_at = datetime(2026, 5, 24, 20, 0, tzinfo=UTC)
    return CommentJob(
        id=1,
        source_system="wiki-go",
        comment_identity="comment-1",
        target_page="/pages/example",
        original_comment_text="@marvin tighten intro",
        prompt="tighten intro",
        source_metadata={"source_system": "wiki-go", "author": "alice"},
        status="processing",
        receipt_count=1,
        first_scanned_at=scanned_at,
        last_scanned_at=scanned_at,
        claimed_at=scanned_at,
        completed_at=None,
        error_detail=None,
    )


def _write_runner(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + dedent(body).lstrip())
    path.chmod(0o755)
    return path
