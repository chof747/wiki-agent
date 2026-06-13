from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "manual_harness_setup_and_comment.sh"


def test_manual_harness_setup_passes_harness_dsns_to_reset(tmp_path: Path) -> None:
    capture_path = tmp_path / "seed-comment-argv.json"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    _write_executable(
        fake_bin / "uv",
        f"""#!/bin/sh
set -eu

if [ "$1" = "run" ] && [ "$2" = "wiki-agent-integration" ] && [ "$3" = "seed-comment" ]; then
  python3 -c 'import json, pathlib, sys; pathlib.Path("{capture_path}").write_text(json.dumps(sys.argv[1:]))' "$@"
  exit 0
fi

exit 0
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["PAGE_PATH"] = "team/roadmap"
    env["COMMENT_TEXT"] = "@marvin investigate this"
    env["RESET_COMMENT_JOBS"] = "0"

    subprocess.run(
        [str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(capture_path.read_text(encoding="utf-8")) == [
        "run",
        "wiki-agent-integration",
        "seed-comment",
        "--page",
        "team/roadmap",
        "--text",
        "@marvin investigate this",
        "--no-reset-comment-jobs",
    ]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
