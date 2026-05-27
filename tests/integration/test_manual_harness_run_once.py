from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import psycopg
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_PATH = "__tests__/scanner-dry-run/eligible"
COMMENT_TEXT = "@marvin # Eligible Fixture\n\nUpdated by manual harness test.\n"
POSTGRES_DSN = "postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent"


@pytest.mark.integration
def test_manual_harness_flow_updates_page_and_deletes_source_comment() -> None:
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/private/tmp/uv-cache")

    subprocess.run(
        [str(REPO_ROOT / "scripts" / "manual_harness_setup_and_comment.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    subprocess.run(
        [str(REPO_ROOT / "scripts" / "manual_harness_run_once.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    with psycopg.connect(POSTGRES_DSN) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT status, error_detail FROM comment_jobs
WHERE target_page = %s
ORDER BY id DESC
LIMIT 1""",
            (PAGE_PATH,),
        )
        row = cursor.fetchone()

    assert row == ("SUCCESS", None)

    page = _run_helper(["wikigo-page", "get", PAGE_PATH], env=env)
    assert json.loads(page)["markdown"].rstrip("\n") == "# Eligible Fixture\n\nUpdated by manual harness test."

    comments = json.loads(_run_helper(["wikigo-comments", "list", PAGE_PATH], env=env))
    assert all(comment["text"] != COMMENT_TEXT.rstrip("\n") for comment in comments)


def _run_helper(argv: list[str], *, env: dict[str, str]) -> str:
    helper_env = env.copy()
    helper_env["PATH"] = f"{REPO_ROOT / '.runtime' / 'integration-harness' / 'bin'}{os.pathsep}{helper_env['PATH']}"
    result = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        env=helper_env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
