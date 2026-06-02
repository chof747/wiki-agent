from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest


def test_run_once_dry_run_emits_normalized_comment_events(tmp_path: Path) -> None:
    script = shutil.which("wiki-agent")
    assert script is not None

    helper_path = tmp_path / "wikigo-comments-scan"
    helper_path.write_text(
        """#!/bin/sh
cat <<'EOF'
[
  {
    "comment_id": "comment-1",
    "page_path": "/pages/alpha",
    "body": "@marvin tighten this page",
    "author": "alice",
    "comment_url": "https://example.test/comments/1"
  },
  {
    "comment_id": "comment-2",
    "page_path": "/pages/beta",
    "body": "@marvin this should be skipped",
    "author": "marvin"
  },
  {
    "comment_id": "comment-3",
    "page_path": "/pages/gamma",
    "body": "@marvin wiki-agent:rejection already handled",
    "author": "bob"
  },
  {
    "comment_id": "comment-4",
    "page_path": "/pages/delta",
    "body": "hello @marvin",
    "author": "carol"
  },
  {
    "comment_id": "comment-5",
    "page_path": "/pages/epsilon",
    "body": "@marvin\\nsecond line request",
    "author": "dave",
    "page_id": "page-5"
  }
]
EOF
""",
        encoding="utf-8",
    )
    helper_path.chmod(0o755)

    config_path = Path(__file__).parent / "fixtures" / "config.toml"
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [script, "run-once", "--dry-run", "--config", str(config_path)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0

    payload = json.loads(result.stdout)
    assert payload == {
        "comment_events": [
            {
                "comment_identity": "comment-1",
                "original_comment_text": "@marvin tighten this page",
                "prompt": "tighten this page",
                "source_metadata": {
                    "author": "alice",
                    "comment_url": "https://example.test/comments/1",
                    "source_system": "wiki-go",
                },
                "target_page": "/pages/alpha",
            },
            {
                "comment_identity": "comment-5",
                "original_comment_text": "@marvin\nsecond line request",
                "prompt": "second line request",
                "source_metadata": {
                    "author": "dave",
                    "page_id": "page-5",
                    "source_system": "wiki-go",
                },
                "target_page": "/pages/epsilon",
            },
        ]
    }

    events = [json.loads(line)["event"] for line in result.stderr.splitlines()]
    assert "service.run_once_started" in events
    assert "scanner.dry_run_completed" in events
    assert "worker.run_once_not_implemented" not in events


def test_run_once_smoke(tmp_path: Path) -> None:
    script = shutil.which("wiki-agent")
    assert script is not None

    config_path = Path(__file__).parent / "fixtures" / "config.toml"
    postgres_dsn = os.environ.get("WIKI_AGENT_TEST_POSTGRES_DSN")
    if not postgres_dsn:
        pytest.skip("set WIKI_AGENT_TEST_POSTGRES_DSN to run non-dry-run CLI smoke coverage")

    helper_dir = Path(__file__).parent.parent / ".runtime" / "integration-harness" / "bin"
    helper_path = helper_dir / "wikigo-comments-scan"
    if shutil.which("wikigo-comments-scan") is None and not helper_path.exists():
        pytest.skip(
            "wikigo-comments-scan is not available; run the integration harness or add the helper to PATH"
        )

    if helper_path.exists():
        reset = subprocess.run(
            ["uv", "run", "wiki-agent-integration", "reset"],
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
        if reset.returncode != 0:
            pytest.skip(f"integration harness reset failed: {reset.stderr or reset.stdout}")

    with psycopg.connect(postgres_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("TRUNCATE TABLE comment_jobs RESTART IDENTITY")
        connection.commit()

    env = os.environ.copy()
    env["WIKI_AGENT_POSTGRES_DSN"] = postgres_dsn
    fake_runner_dir = tmp_path / "runner-bin"
    fake_runner_dir.mkdir()
    capture_path = fake_runner_dir / "runner-stdin.json"
    runner_path = fake_runner_dir / "codex-runner"
    runner_path.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

payload = json.load(sys.stdin)
pathlib.Path(sys.argv[2]).write_text(json.dumps(payload, sort_keys=True))
sys.stderr.write("runner diagnostic\\n")
sys.stdout.write(json.dumps({"status": "SUCCESS"}))
""",
        encoding="utf-8",
    )
    runner_path.chmod(0o755)
    env["WIKI_AGENT_RUNNER_COMMAND_JSON"] = json.dumps(
        [str(runner_path), "--capture", str(capture_path)]
    )
    if helper_path.exists():
        env["PATH"] = f"{fake_runner_dir}{os.pathsep}{helper_dir}{os.pathsep}{env['PATH']}"
    else:
        env["PATH"] = f"{fake_runner_dir}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [script, "run-once", "--config", str(config_path)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, f"{result.stderr}"
    events = [json.loads(line)["event"] for line in result.stderr.splitlines()]
    assert "worker.job_claimed" in events
    assert "worker.job_finalized" in events
    assert "service.run_once_finished" in events
    assert "worker.runner_failed" not in events

    payload = json.loads(capture_path.read_text(encoding="utf-8"))
    assert payload["prompt"]
    assert payload["original_comment_text"].startswith("@marvin")
    assert payload["comment_identity"]
    assert payload["target_page"]
    assert payload["source_metadata"]["source_system"] == "wiki-go"
    assert payload["constraints"] == {
        "single_target_scope": {
            "mode": "attached_target_page_only",
            "target_page": payload["target_page"],
        }
    }
