from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_run_once_dry_run_emits_expected_contract() -> None:
    script = shutil.which("wiki-agent")
    assert script is not None

    config_path = _require_path_env("WIKI_AGENT_INTEGRATION_CONFIG")
    env = os.environ.copy()
    result = subprocess.run(
        [script, "run-once", "--dry-run", "--config", str(config_path)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0

    payload = json.loads(result.stdout)
    assert len(payload["comment_events"]) == 1

    event = payload["comment_events"][0]
    assert event["comment_identity"].strip()
    assert event["original_comment_text"] == "@marvin tighten the intro"
    assert event["prompt"] == "tighten the intro"
    assert event["target_page"] == "__tests__/scanner-dry-run/eligible"
    assert event["source_metadata"]["author"] == "admin"
    assert event["source_metadata"]["source_system"] == "wiki-go"

    events = [json.loads(line)["event"] for line in result.stderr.splitlines()]
    assert "service.run_once_started" in events
    assert "scanner.dry_run_completed" in events
    assert "worker.run_once_not_implemented" not in events


def _require_path_env(name: str) -> Path:
    value = os.environ.get(name)
    assert value, f"missing required environment variable: {name}"
    return Path(value)
