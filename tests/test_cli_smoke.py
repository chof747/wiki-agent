from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def test_run_once_smoke() -> None:
    script = shutil.which("wiki-agent")
    assert script is not None

    config_path = Path(__file__).parent / "fixtures" / "config.toml"
    result = subprocess.run(
        [script, "run-once", "--config", str(config_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    events = [json.loads(line)["event"] for line in result.stderr.splitlines()]
    assert "worker.run_once_not_implemented" in events


def test_run_once_dry_run_smoke(tmp_path: Path) -> None:
    script = shutil.which("wiki-agent")
    assert script is not None

    helper_dir = tmp_path / "bin"
    helper_dir.mkdir()
    helper_path = helper_dir / "wikigo-comments-scan"
    helper_path.write_text(
        "#!/bin/sh\n"
        "cat <<'EOF'\n"
        '{"scanned_pages":1,"matched_comments":2,"matches":['
        '{"page":"team/roadmap","id":"100","text":"@marvin tighten intro","author":"alice"},'
        '{"page":"team/roadmap","id":"101","text":"@marvin wiki-agent: handled","author":"alice"}'
        "]}\n"
        "EOF\n",
        encoding="utf-8",
    )
    helper_path.chmod(0o755)

    config_path = Path(__file__).parent / "fixtures" / "config.toml"
    env = os.environ.copy()
    env["PATH"] = f"{helper_dir}:{env['PATH']}"
    result = subprocess.run(
        [script, "run-once", "--dry-run", "--config", str(config_path)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0
    assert "worker.run_once_not_implemented" not in result.stderr
    summary = json.loads(result.stdout)
    assert summary == {
        "mode": "scanner_dry_run",
        "bot_name": "marvin",
        "scanned_pages": 1,
        "matched_comments": 2,
        "eligible_comment_events": [
            {
                "source_system": "wikigo",
                "comment_identity": "100",
                "target_page": "team/roadmap",
                "author": "alice",
                "comment_body": "@marvin tighten intro",
                "prompt": "tighten intro",
            }
        ],
    }
