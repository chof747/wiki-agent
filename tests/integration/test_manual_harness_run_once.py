from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import psycopg


REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_PATH = "__tests__/scanner-dry-run/eligible"
COMMENT_TEXT = "@marvin # Eligible Fixture\n\nUpdated by manual harness test.\n"
UPDATED_MARKDOWN = "# Eligible Fixture\n\nUpdated by manual harness test."
REJECTION_COMMENT_TEXT = "@marvin update /other-page too"
REJECTION_REASON_CODE = "CROSS_PAGE_REQUEST"
REJECTION_EXPLANATION = "This agent can only update the page where the comment was posted."


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
    fake_runner_path = _write_fake_runner(tmp_path / "fake-runner")

    try:
        _delete_all_comments(PAGE_PATH, runtime_config=admin_config_path, env=env)
        _post_comment(PAGE_PATH, COMMENT_TEXT, runtime_config=admin_config_path, env=env, tmp_path=tmp_path)

        run_env = _helper_env(runtime_config=bot_config_path, env=env)
        run_env["WIKI_AGENT_RUNNER_COMMAND_JSON"] = json.dumps([str(fake_runner_path)])
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


@pytest.mark.integration
def test_run_once_creates_visible_rejection_comment_and_finalizes_job(tmp_path: Path) -> None:
    script = shutil.which("wiki-agent")
    assert script is not None

    config_path = _require_path_env("WIKI_AGENT_INTEGRATION_CONFIG")
    runtime_root = config_path.parent
    admin_config_path = runtime_root / "wikigo-admin-config.json"
    bot_config_path = runtime_root / "wikigo-bot-config.json"

    env = os.environ.copy()
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/private/tmp/uv-cache")
    _write_fake_openai_package(
        tmp_path / "openai",
        {
            "action": "reject",
            "final_page_content": None,
            "rejection_reason_code": REJECTION_REASON_CODE,
            "explanation": REJECTION_EXPLANATION,
        },
    )

    try:
        _delete_all_comments(PAGE_PATH, runtime_config=admin_config_path, env=env)
        source_comment = _post_comment(
            PAGE_PATH,
            REJECTION_COMMENT_TEXT,
            runtime_config=admin_config_path,
            env=env,
            tmp_path=tmp_path,
        )
        source_comment_id = str(source_comment["id"])

        run_env = _helper_env(runtime_config=bot_config_path, env=env)
        run_env["OPENAI_API_KEY"] = "test-openai-key"
        run_env["PYTHONPATH"] = f"{tmp_path}{os.pathsep}{run_env.get('PYTHONPATH', '')}"
        result = subprocess.run(
            [script, "run-once", "--config", str(config_path)],
            cwd=REPO_ROOT,
            env=run_env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        stderr_events = [json.loads(line) for line in result.stderr.splitlines()]
        assert "worker.runner_failed" not in [event["event"] for event in stderr_events]
        finalized_event = next(event for event in stderr_events if event["event"] == "worker.job_finalized")
        assert finalized_event["status"] == "REJECTED_WITH_COMMENT"

        comments = json.loads(
            _run_helper(["wikigo-comments", "list", PAGE_PATH], runtime_config=admin_config_path, env=env)
        )
        assert len(comments) == 1
        assert all(str(comment["id"]) != source_comment_id for comment in comments)
        assert comments[0]["author"] == "marvin"
        assert comments[0]["text"].strip() == _expected_rejection_comment(source_comment_id).strip()
        assert isinstance(comments[0].get("created_at"), str)

        with psycopg.connect(_require_env("WIKI_AGENT_INTEGRATION_RUNTIME_DSN")) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status FROM comment_jobs WHERE comment_identity = %s",
                    (source_comment_id,),
                )
                row = cursor.fetchone()

        assert row == ("REJECTED_WITH_COMMENT",)
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
) -> dict[str, object]:
    payload_path = tmp_path / "comment-payload.json"
    payload_path.write_text(json.dumps({"content": comment_text}), encoding="utf-8")
    _run_helper(
        ["wikigo-api", "POST", f"/api/comments/add/{page_path}", str(payload_path), "application/json"],
        runtime_config=runtime_config,
        env=env,
    )
    comments = json.loads(
        _run_helper(["wikigo-comments", "list", page_path], runtime_config=runtime_config, env=env)
    )
    return next(comment for comment in comments if comment.get("text") == comment_text.rstrip("\n"))


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


def _expected_rejection_comment(source_comment_id: str) -> str:
    return (
        f'<!-- wiki-agent:rejection source_comment_id="{source_comment_id}" '
        f'reason_code="{REJECTION_REASON_CODE}" -->\n\n'
        "Marvin could not process this request.\n\n"
        f"> {REJECTION_COMMENT_TEXT}\n\n"
        f"Reason (`{REJECTION_REASON_CODE}`): {REJECTION_EXPLANATION}\n"
    )


def _write_fake_openai_package(path: Path, output_payload: dict[str, object]) -> None:
    path.mkdir()
    (path / "__init__.py").write_text(
        (
            "import json\n"
            "import types\n"
            "\n"
            f"OUTPUT_PAYLOAD = {output_payload!r}\n"
            "\n"
            "class OpenAI:\n"
            "    def __init__(self, *, api_key=None, timeout=None):\n"
            "        self.api_key = api_key\n"
            "        self.timeout = timeout\n"
            "        self.responses = _Responses()\n"
            "\n"
            "class _Responses:\n"
            "    def create(self, **kwargs):\n"
            "        del kwargs\n"
            "        return types.SimpleNamespace(status='completed', output_text=json.dumps(OUTPUT_PAYLOAD))\n"
        ),
        encoding="utf-8",
    )


def _write_fake_runner(path: Path) -> Path:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import pathlib\n"
            "import subprocess\n"
            "import sys\n"
            "import tempfile\n"
            "\n"
            "envelope = json.load(sys.stdin)\n"
            "target_page = envelope['target_page']\n"
            "comment_identity = envelope['comment_identity']\n"
            "updated_markdown = '# Eligible Fixture\\n\\nUpdated by manual harness test.\\n'\n"
            "subprocess.run(['wikigo-page', 'get', target_page], check=True, capture_output=True, text=True)\n"
            "with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.md', delete=False) as handle:\n"
            "    handle.write(updated_markdown)\n"
            "    temp_path = pathlib.Path(handle.name)\n"
            "try:\n"
            "    subprocess.run(['wikigo-page', 'save', target_page, str(temp_path)], check=True, capture_output=True, text=True)\n"
            "finally:\n"
            "    temp_path.unlink(missing_ok=True)\n"
            "confirmed = subprocess.run(['wikigo-page', 'get', target_page], check=True, capture_output=True, text=True)\n"
            "if json.loads(confirmed.stdout)['markdown'] != updated_markdown:\n"
            "    sys.stdout.write(json.dumps({'status': 'UPDATE_FAILED', 'error_code': 'UPDATE_CONFIRMATION_FAILED', 'message': 'saved page content did not match confirmation fetch'}))\n"
            "    sys.stdout.write('\\n')\n"
            "    raise SystemExit(0)\n"
            "subprocess.run(['wikigo-comments', 'delete', comment_identity, target_page], check=True, capture_output=True, text=True)\n"
            "remaining = subprocess.run(['wikigo-comments', 'list', target_page], check=True, capture_output=True, text=True)\n"
            "if any(comment.get('id') == comment_identity for comment in json.loads(remaining.stdout)):\n"
            "    sys.stdout.write(json.dumps({'status': 'DELETE_FAILED', 'error_code': 'DELETE_CONFIRMATION_FAILED', 'message': 'source comment still present after delete confirmation'}))\n"
            "    sys.stdout.write('\\n')\n"
            "    raise SystemExit(0)\n"
            "sys.stdout.write(json.dumps({'status': 'SUCCESS'}))\n"
            "sys.stdout.write('\\n')\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path
