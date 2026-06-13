from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_PATH = "__tests__/scanner-dry-run/eligible"
DEFAULT_INTEGRATION_CONFIG_PATH = (
    REPO_ROOT / ".runtime" / "integration-harness" / "wiki-agent.integration.toml"
)


@pytest.mark.integration
def test_wikigo_helper_uses_supported_1_8_9_contract(tmp_path: Path) -> None:
    config_path = _require_path_env("WIKI_AGENT_INTEGRATION_CONFIG")
    runtime_root = config_path.parent
    admin_config_path = runtime_root / "wikigo-admin-config.json"
    bot_config_path = runtime_root / "wikigo-bot-config.json"

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/private/tmp/uv-cache")

    updated_markdown = "# Eligible Fixture\n\nUpdated by helper contract test.\n"
    comment_text = "Contract test comment"
    content_path = tmp_path / "comment.md"
    content_path.write_text(comment_text, encoding="utf-8")
    page_path = tmp_path / "page.md"
    page_path.write_text(updated_markdown, encoding="utf-8")

    try:
        _reset_harness(env=env)

        _run_helper(["wikigo-page", "save", PAGE_PATH, str(page_path)], runtime_config=bot_config_path, env=env)
        page_payload = json.loads(
            _run_helper(["wikigo-page", "get", PAGE_PATH], runtime_config=bot_config_path, env=env)
        )
        assert page_payload["markdown"] == updated_markdown

        _run_helper(
            ["wikigo-comments", "create", PAGE_PATH, str(content_path)],
            runtime_config=admin_config_path,
            env=env,
        )

        comments = json.loads(
            _run_helper(["wikigo-comments", "list", PAGE_PATH], runtime_config=admin_config_path, env=env)
        )
        created_comment = next(comment for comment in comments if comment["text"] == comment_text)
        comment_id = str(created_comment["id"])

        _run_helper(
            ["wikigo-comments", "delete", comment_id, PAGE_PATH],
            runtime_config=admin_config_path,
            env=env,
        )
        remaining = json.loads(
            _run_helper(["wikigo-comments", "list", PAGE_PATH], runtime_config=admin_config_path, env=env)
        )
        assert all(comment["id"] != comment_id for comment in remaining)
    finally:
        _reset_harness(env=env)


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
    value = os.environ.get(name)
    if value:
        return Path(value)
    assert DEFAULT_INTEGRATION_CONFIG_PATH.exists(), f"missing required environment variable: {name}"
    return DEFAULT_INTEGRATION_CONFIG_PATH
