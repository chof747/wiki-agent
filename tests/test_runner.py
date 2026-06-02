from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from wiki_agent import runner


def test_runner_executes_openai_backed_successful_page_update_flow(tmp_path: Path) -> None:
    result, state_path, helper_log_path, openai_log_path = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={"final_page_content": "# Replacement page\n\nUpdated content.\n"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "SUCCESS"}

    helper_calls = _read_jsonl(helper_log_path)
    assert [call["command"] for call in helper_calls] == [
        "page.get",
        "page.save",
        "page.get",
        "comments.delete",
        "comments.list",
    ]
    assert helper_calls[1]["content"] == "# Replacement page\n\nUpdated content.\n"

    openai_calls = _read_jsonl(openai_log_path)
    assert len(openai_calls) == 1
    assert openai_calls[0]["model"] == runner.DEFAULT_OPENAI_MODEL
    rendered_prompt = openai_calls[0]["input"][1]["content"]
    assert "Target page: /pages/example" in rendered_prompt
    assert "Stripped prompt:\n# Rewrite the page\n\nMake it shorter.\n" in rendered_prompt
    assert "Original source comment:\n@marvin # Rewrite the page\n\nMake it shorter.\n" in rendered_prompt
    assert "Current page content:\n# Current page\n" in rendered_prompt

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] == "# Replacement page\n\nUpdated content.\n"
    assert state["deleted_comment_ids"] == ["comment-1"]


def test_runner_returns_update_failed_when_model_output_is_invalid(tmp_path: Path) -> None:
    result, state_path, helper_log_path, _ = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={
            "final_page_content": "# Replacement page\n",
            "extra_field": "not allowed",
        },
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "UPDATE_FAILED",
        "error_code": "MODEL_OUTPUT_INVALID",
        "message": "model output must contain exactly one string field: final_page_content",
    }

    helper_calls = _read_jsonl(helper_log_path)
    assert [call["command"] for call in helper_calls] == ["page.get"]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] is None
    assert state["deleted_comment_ids"] == []


def test_runner_returns_update_failed_when_model_output_does_not_change_page(tmp_path: Path) -> None:
    result, state_path, helper_log_path, _ = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={"final_page_content": "# Current page\n"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "UPDATE_FAILED",
        "error_code": "NO_CONTENT_CHANGE",
        "message": "model output did not change the current page content",
    }

    helper_calls = _read_jsonl(helper_log_path)
    assert [call["command"] for call in helper_calls] == ["page.get"]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] is None
    assert state["deleted_comment_ids"] == []


def test_runner_enforces_input_size_limit_before_model_call(tmp_path: Path) -> None:
    result, state_path, helper_log_path, openai_log_path = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={"final_page_content": "# Replacement page\n"},
        extra_env={"WIKI_AGENT_RUNNER_MAX_INPUT_BYTES": "32"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "UPDATE_FAILED",
        "error_code": "INPUT_TOO_LARGE",
        "message": "rendered model input exceeded byte limit",
    }
    assert _read_jsonl(openai_log_path) == []
    assert [call["command"] for call in _read_jsonl(helper_log_path)] == ["page.get"]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] is None


def test_runner_enforces_output_size_limit_before_save(tmp_path: Path) -> None:
    result, state_path, helper_log_path, openai_log_path = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={"final_page_content": "x" * 64},
        extra_env={"WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES": "32"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "UPDATE_FAILED",
        "error_code": "OUTPUT_TOO_LARGE",
        "message": "model output exceeded byte limit",
    }
    assert len(_read_jsonl(openai_log_path)) == 1
    assert [call["command"] for call in _read_jsonl(helper_log_path)] == ["page.get"]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] is None


def test_runner_returns_update_failed_when_model_call_raises(tmp_path: Path) -> None:
    result, state_path, helper_log_path, openai_log_path = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={"raise_error": "simulated model failure"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "UPDATE_FAILED",
        "error_code": "MODEL_CALL_FAILED",
        "message": "simulated model failure",
    }
    assert len(_read_jsonl(openai_log_path)) == 1
    assert [call["command"] for call in _read_jsonl(helper_log_path)] == ["page.get"]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] is None


def test_runner_returns_delete_failed_after_confirmed_update_when_comment_delete_confirmation_fails(
    tmp_path: Path,
) -> None:
    result, state_path, helper_log_path, _ = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={"final_page_content": "# Replacement page\n"},
        keep_comment_after_delete=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "DELETE_FAILED",
        "error_code": "DELETE_CONFIRMATION_FAILED",
        "message": "source comment still present after delete confirmation",
    }

    helper_calls = _read_jsonl(helper_log_path)
    assert [call["command"] for call in helper_calls] == [
        "page.get",
        "page.save",
        "page.get",
        "comments.delete",
        "comments.list",
    ]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] == "# Replacement page\n"
    assert state["deleted_comment_ids"] == ["comment-1"]


def test_render_prompt_includes_all_runtime_inputs() -> None:
    template = (
        "Target={{TARGET_PAGE}}\n"
        "Prompt={{PROMPT}}\n"
        "Comment={{ORIGINAL_COMMENT_TEXT}}\n"
        "Content={{CURRENT_PAGE_CONTENT}}\n"
    )

    rendered = runner.render_prompt(
        template=template,
        prompt="# Rewrite the page",
        original_comment_text="@marvin # Rewrite the page",
        target_page="/pages/example",
        current_page_content="# Current page\n",
    )

    assert rendered == (
        "Target=/pages/example\n"
        "Prompt=# Rewrite the page\n"
        "Comment=@marvin # Rewrite the page\n"
        "Content=# Current page\n\n"
    )


def test_render_prompt_rejects_missing_required_placeholder() -> None:
    with pytest.raises(runner.PromptTemplateError, match="missing required placeholder"):
        runner.render_prompt(
            template="Target={{TARGET_PAGE}}\nPrompt={{PROMPT}}\n",
            prompt="# Rewrite the page",
            original_comment_text="@marvin # Rewrite the page",
            target_page="/pages/example",
            current_page_content="# Current page\n",
        )


def _run_runner(
    tmp_path: Path,
    *,
    page_markdown: str,
    openai_output: dict[str, object],
    extra_env: dict[str, str] | None = None,
    keep_comment_after_delete: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    script = shutil.which("wiki-agent-runner")
    assert script is not None

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "page_markdown": page_markdown,
                "saved_markdown": None,
                "deleted_comment_ids": [],
                "comments": [{"id": "comment-1", "text": "@marvin # Rewrite the page\n\nMake it shorter.\n"}],
                "keep_comment_after_delete": keep_comment_after_delete,
            }
        ),
        encoding="utf-8",
    )
    helper_log_path = tmp_path / "helper-log.jsonl"
    openai_log_path = tmp_path / "openai-log.jsonl"
    openai_package_root = tmp_path / "openai"
    _write_fake_openai_package(openai_package_root, openai_log_path, openai_output)
    _write_wikigo_page_helper(tmp_path / "wikigo-page", state_path, helper_log_path)
    _write_wikigo_comments_helper(tmp_path / "wikigo-comments", state_path, helper_log_path)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    env["PYTHONPATH"] = f"{tmp_path}{os.pathsep}{env.get('PYTHONPATH', '')}"
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [script],
        input=json.dumps(_envelope()),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return result, state_path, helper_log_path, openai_log_path


def _envelope() -> dict[str, object]:
    return {
        "prompt": "# Rewrite the page\n\nMake it shorter.\n",
        "original_comment_text": "@marvin # Rewrite the page\n\nMake it shorter.\n",
        "target_page": "/pages/example",
        "comment_identity": "comment-1",
        "source_metadata": {"source_system": "wiki-go", "author": "alice"},
        "constraints": {
            "single_target_scope": {
                "target_page": "/pages/example",
                "mode": "attached_target_page_only",
            }
        },
    }


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_fake_openai_package(path: Path, log_path: Path, output_payload: dict[str, object]) -> None:
    path.mkdir()
    (path / "__init__.py").write_text(
        (
            "import json\n"
            "import pathlib\n"
            "import types\n"
            "\n"
            f"LOG_PATH = pathlib.Path({str(log_path)!r})\n"
            f"OUTPUT_PAYLOAD = {output_payload!r}\n"
            "\n"
            "class OpenAI:\n"
            "    def __init__(self, *, timeout=None):\n"
            "        self.timeout = timeout\n"
            "        self.responses = _Responses(timeout)\n"
            "\n"
            "class _Responses:\n"
            "    def __init__(self, timeout):\n"
            "        self.timeout = timeout\n"
            "\n"
            "    def create(self, **kwargs):\n"
            "        entry = {'timeout': self.timeout, **kwargs}\n"
            "        if LOG_PATH.exists():\n"
            "            lines = LOG_PATH.read_text(encoding='utf-8')\n"
            "        else:\n"
            "            lines = ''\n"
            "        LOG_PATH.write_text(lines + json.dumps(entry) + '\\n', encoding='utf-8')\n"
            "        if isinstance(OUTPUT_PAYLOAD, dict) and 'raise_error' in OUTPUT_PAYLOAD:\n"
            "            raise RuntimeError(OUTPUT_PAYLOAD['raise_error'])\n"
            "        return types.SimpleNamespace(status='completed', output_text=json.dumps(OUTPUT_PAYLOAD))\n"
        ),
        encoding="utf-8",
    )


def _write_wikigo_page_helper(path: Path, state_path: Path, log_path: Path) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import pathlib\n"
            "import sys\n"
            f"state_path = pathlib.Path({str(state_path)!r})\n"
            f"log_path = pathlib.Path({str(log_path)!r})\n"
            "state = json.loads(state_path.read_text(encoding='utf-8'))\n"
            "command = sys.argv[1]\n"
            "if command == 'get':\n"
            "    page = sys.argv[2]\n"
            "    line = json.dumps({'command': 'page.get', 'page': page}) + '\\n'\n"
            "    existing = log_path.read_text(encoding='utf-8') if log_path.exists() else ''\n"
            "    log_path.write_text(existing + line, encoding='utf-8')\n"
            "    markdown = state.get('saved_markdown') or state.get('page_markdown') or ''\n"
            "    sys.stdout.write(json.dumps({'markdown': markdown}))\n"
            "    raise SystemExit(0)\n"
            "if command == 'save':\n"
            "    page = sys.argv[2]\n"
            "    content = pathlib.Path(sys.argv[3]).read_text(encoding='utf-8')\n"
            "    line = json.dumps({'command': 'page.save', 'page': page, 'content': content}) + '\\n'\n"
            "    existing = log_path.read_text(encoding='utf-8') if log_path.exists() else ''\n"
            "    log_path.write_text(existing + line, encoding='utf-8')\n"
            "    state['saved_markdown'] = content\n"
            "    state_path.write_text(json.dumps(state), encoding='utf-8')\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(f'unsupported wikigo-page command: {command}')\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_wikigo_comments_helper(path: Path, state_path: Path, log_path: Path) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import pathlib\n"
            "import sys\n"
            f"state_path = pathlib.Path({str(state_path)!r})\n"
            f"log_path = pathlib.Path({str(log_path)!r})\n"
            "state = json.loads(state_path.read_text(encoding='utf-8'))\n"
            "command = sys.argv[1]\n"
            "if command == 'delete':\n"
            "    comment_id = sys.argv[2]\n"
            "    page = sys.argv[3]\n"
            "    line = json.dumps({'command': 'comments.delete', 'comment_id': comment_id, 'page': page}) + '\\n'\n"
            "    existing = log_path.read_text(encoding='utf-8') if log_path.exists() else ''\n"
            "    log_path.write_text(existing + line, encoding='utf-8')\n"
            "    deleted = state.setdefault('deleted_comment_ids', [])\n"
            "    deleted.append(comment_id)\n"
            "    if not state.get('keep_comment_after_delete'):\n"
            "        state['comments'] = [item for item in state.get('comments', []) if item.get('id') != comment_id]\n"
            "    state_path.write_text(json.dumps(state), encoding='utf-8')\n"
            "    raise SystemExit(0)\n"
            "if command == 'list':\n"
            "    page = sys.argv[2]\n"
            "    line = json.dumps({'command': 'comments.list', 'page': page}) + '\\n'\n"
            "    existing = log_path.read_text(encoding='utf-8') if log_path.exists() else ''\n"
            "    log_path.write_text(existing + line, encoding='utf-8')\n"
            "    sys.stdout.write(json.dumps(state.get('comments', [])))\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(f'unsupported wikigo-comments command: {command}')\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
