from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_PATH = "__tests__/scanner-dry-run/eligible"
COMMENT_TEXT = "@marvin # Eligible Fixture\n\nUpdated by manual harness test.\n"
UPDATED_MARKDOWN = "# Eligible Fixture\n\nUpdated by manual harness test."


@pytest.mark.integration
def test_run_once_updates_page_and_deletes_source_comment(tmp_path: Path) -> None:
    script = shutil.which("wiki-agent")
    assert script is not None

    config_path = _require_path_env("WIKI_AGENT_INTEGRATION_CONFIG")
    runtime_root = config_path.parent
    admin_config_path = runtime_root / "wikigo-admin-config.json"
    bot_config_path = runtime_root / "wikigo-bot-config.json"

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/private/tmp/uv-cache")

    try:
        _delete_all_comments(PAGE_PATH, runtime_config=admin_config_path, env=env)
        _post_comment(PAGE_PATH, COMMENT_TEXT, runtime_config=admin_config_path, env=env, tmp_path=tmp_path)

        run_env = _helper_env(runtime_config=bot_config_path, env=env)
        result = subprocess.run(
            [script, "run-once", "--config", str(config_path)],
            cwd=REPO_ROOT,
            env=run_env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        events = [json.loads(line)["event"] for line in result.stderr.splitlines()]
        assert "worker.job_claimed" in events
        assert "worker.job_finalized" in events
        assert "worker.runner_failed" not in events

        page = _run_helper(["wikigo-page", "get", PAGE_PATH], runtime_config=bot_config_path, env=env)
        assert json.loads(page)["markdown"].rstrip("\n") == UPDATED_MARKDOWN

        comments = json.loads(
            _run_helper(["wikigo-comments", "list", PAGE_PATH], runtime_config=admin_config_path, env=env)
        )
        assert comments == []
    finally:
        _reset_harness(env=env)


def _delete_all_comments(page_path: str, *, runtime_config: Path, env: dict[str, str]) -> None:
    comments = json.loads(_run_helper(["wikigo-comments", "list", page_path], runtime_config=runtime_config, env=env))
    for comment in comments:
        _run_helper(
            ["wikigo-comments", "delete", comment["id"], page_path],
            runtime_config=runtime_config,
            env=env,
        )


def _post_comment(
    page_path: str,
    comment_text: str,
    *,
    runtime_config: Path,
    env: dict[str, str],
    tmp_path: Path,
) -> None:
    payload_path = tmp_path / "comment-payload.json"
    payload_path.write_text(json.dumps({"content": comment_text}), encoding="utf-8")
    _run_helper(
        ["wikigo-api", "POST", f"/api/comments/add/{page_path}", str(payload_path), "application/json"],
        runtime_config=runtime_config,
        env=env,
    )


def _reset_harness(*, env: dict[str, str]) -> None:
    subprocess.run(
        ["uv", "run", "wiki-agent-integration", "reset"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _run_helper(argv: list[str], *, runtime_config: Path, env: dict[str, str]) -> str:
    helper_env = _helper_env(runtime_config=runtime_config, env=env)
    result = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        env=helper_env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _helper_env(*, runtime_config: Path, env: dict[str, str]) -> dict[str, str]:
    helper_env = env.copy()
    helper_env["PATH"] = f"{REPO_ROOT / '.runtime' / 'integration-harness' / 'bin'}{os.pathsep}{helper_env['PATH']}"
    helper_env["WIKIGO_RUNTIME_CONFIG"] = str(runtime_config)
    return helper_env


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    assert value, f"missing required environment variable: {name}"
    return value


def _require_path_env(name: str) -> Path:
    return Path(_require_env(name))
