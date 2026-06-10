from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import time
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
    with psycopg.connect(postgres_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("TRUNCATE TABLE comment_jobs RESTART IDENTITY")
        connection.commit()

    env = os.environ.copy()
    env["WIKI_AGENT_POSTGRES_DSN"] = postgres_dsn
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
  }
]
EOF
""",
        encoding="utf-8",
    )
    helper_path.chmod(0o755)
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
    env["PATH"] = f"{fake_runner_dir}{os.pathsep}{tmp_path}{os.pathsep}{env['PATH']}"
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


def test_run_service_smoke_handles_sigterm(tmp_path: Path) -> None:
    script = shutil.which("wiki-agent")
    assert script is not None

    config_path = tmp_path / "config.toml"
    postgres_dsn = os.environ.get("WIKI_AGENT_TEST_POSTGRES_DSN")
    if not postgres_dsn:
        pytest.skip("set WIKI_AGENT_TEST_POSTGRES_DSN to run long-running CLI smoke coverage")

    with psycopg.connect(postgres_dsn) as connection, connection.cursor() as cursor:
        cursor.execute("TRUNCATE TABLE comment_jobs RESTART IDENTITY")
        connection.commit()

    config_path.write_text(
        "\n".join(
            [
                'bot_name = "marvin"',
                "",
                "[postgres]",
                f'dsn = "{postgres_dsn}"',
                "",
                "[wikigo]",
                'base_url = "http://127.0.0.1:4010"',
                'username = "marvin"',
                'password = "marvin-pass"',
                "",
                "[runner]",
                'command = ["wiki-agent-runner"]',
                "",
                "[runner.openai]",
                'api_key = "test-openai-key"',
                'model = "gpt-4o-2024-08-06"',
                "max_input_bytes = 32768",
                "max_output_bytes = 40960",
                "timeout_seconds = 60",
                "",
                "[service]",
                'log_level = "INFO"',
                "scan_interval = 1",
                "stale_processing_timeout = 5",
                "",
            ]
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    helper_path = tmp_path / "wikigo-comments-scan"
    helper_path.write_text(
        """#!/bin/sh
cat <<'EOF'
[
  {
    "comment_id": "comment-1",
    "page_path": "/pages/alpha",
    "body": "@marvin tighten this page",
    "author": "alice"
  }
]
EOF
""",
        encoding="utf-8",
    )
    helper_path.chmod(0o755)
    fake_runner_dir = tmp_path / "runner-bin"
    fake_runner_dir.mkdir()
    runner_path = fake_runner_dir / "wiki-agent-runner"
    runner_path.write_text(
        """#!/usr/bin/env python3
import json
import sys

json.load(sys.stdin)
sys.stderr.write("runner diagnostic\\n")
sys.stdout.write(json.dumps({"status": "SUCCESS"}))
""",
        encoding="utf-8",
    )
    runner_path.chmod(0o755)
    env["PATH"] = f"{fake_runner_dir}{os.pathsep}{tmp_path}{os.pathsep}{env['PATH']}"

    process = subprocess.Popen(
        [script, "run", "--config", str(config_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    try:
        deadline = time.time() + 10
        stderr_lines: list[str] = []
        while time.time() < deadline:
            line = process.stderr.readline()
            if line:
                stderr_lines.append(line)
                event = json.loads(line).get("event")
                if event == "worker.job_finalized":
                    break
            if process.poll() is not None:
                break

        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)

    assert process.returncode == 0
    assert stdout == ""
    events = [json.loads(line)["event"] for line in (stderr_lines + stderr.splitlines()) if line.strip()]
    assert "service.started" in events
    assert "worker.job_claimed" in events
    assert "worker.job_finalized" in events
    assert "service.shutdown_requested" in events
    assert "service.stopped" in events
