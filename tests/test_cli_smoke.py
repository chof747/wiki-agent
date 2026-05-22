from __future__ import annotations

import json
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

