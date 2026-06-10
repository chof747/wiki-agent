from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "manual_harness_run_once.sh"


def test_manual_harness_run_once_forces_bot_runtime_config(tmp_path: Path) -> None:
    capture_path = tmp_path / "run-once-env.json"
    up_capture_path = tmp_path / "harness-up.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    _write_executable(
        fake_bin / "uv",
        f"""#!/bin/sh
set -eu

if [ "$1" = "run" ] && [ "$2" = "wiki-agent-integration" ] && [ "$3" = "up" ]; then
  printf 'up\n' > "{up_capture_path}"
  exit 0
fi

if [ "$1" = "run" ] && [ "$2" = "wiki-agent" ] && [ "$3" = "run-once" ]; then
  python3 -c 'import json, os, pathlib; pathlib.Path("{capture_path}").write_text(json.dumps({{"config_path": os.environ.get("WIKI_AGENT_CONFIG_PATH"), "openai_api_key": os.environ.get("OPENAI_API_KEY"), "wikigo_runtime_config": os.environ.get("WIKIGO_RUNTIME_CONFIG")}}))'
  exit 0
fi

exit 0
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["WIKIGO_RUNTIME_CONFIG"] = "/tmp/should-not-be-used-admin-config.json"

    subprocess.run(
        [str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert up_capture_path.read_text(encoding="utf-8") == "up\n"
    payload = json.loads(capture_path.read_text(encoding="utf-8"))
    assert payload["config_path"] == str(
        REPO_ROOT / ".runtime" / "integration-harness" / "wiki-agent.integration.toml"
    )
    assert payload["wikigo_runtime_config"] is None


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
