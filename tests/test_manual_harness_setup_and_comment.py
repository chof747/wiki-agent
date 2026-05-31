from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "manual_harness_setup_and_comment.sh"


def test_manual_harness_setup_passes_harness_dsns_to_reset(tmp_path: Path) -> None:
    capture_path = tmp_path / "reset-env.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    _write_executable(
        fake_bin / "uv",
        f"""#!/bin/sh
set -eu

if [ "$1" = "run" ] && [ "$2" = "wiki-agent-integration" ] && [ "$3" = "reset" ]; then
  printf '%s\n%s\n' "${{WIKI_AGENT_INTEGRATION_ADMIN_DSN:-}}" "${{WIKI_AGENT_INTEGRATION_RUNTIME_DSN:-}}" > "{capture_path}"
  exit 0
fi

if [ "$1" = "run" ] && [ "$2" = "python" ]; then
  shift 2
  exec python3 "$@"
fi

exit 0
""",
    )

    runtime_bin = REPO_ROOT / ".runtime" / "integration-harness" / "bin"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    _write_executable(runtime_bin / "wikigo-api", "#!/bin/sh\nexit 0\n")
    _write_executable(runtime_bin / "wikigo-comments", "#!/bin/sh\nprintf '[]\\n'\n")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["MANUAL_HARNESS_POSTGRES_DSN"] = "postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent"
    env["RESET_COMMENT_JOBS"] = "0"

    subprocess.run(
        [str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    admin_dsn, runtime_dsn = capture_path.read_text(encoding="utf-8").splitlines()
    assert admin_dsn == env["MANUAL_HARNESS_POSTGRES_DSN"]
    assert runtime_dsn == env["MANUAL_HARNESS_POSTGRES_DSN"]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
