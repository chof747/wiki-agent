from __future__ import annotations

import io
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


def test_runner_reads_openai_settings_from_app_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            "bot_name = \"marvin\"\n\n"
            "[postgres]\n"
            "dsn = \"postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent\"\n\n"
            "[wikigo]\n"
            "base_url = \"http://127.0.0.1:4010\"\n"
            "username = \"marvin\"\n"
            "password = \"marvin-pass\"\n\n"
            "[runner]\n"
            "command = [\"wiki-agent-runner\"]\n\n"
            "[runner.openai]\n"
            "api_key = \"config-openai-key\"\n"
            "model = \"gpt-4.1-mini\"\n"
            "max_input_bytes = 12345\n"
            "max_output_bytes = 23456\n"
            "timeout_seconds = 12.5\n\n"
            "[service]\n"
            "log_level = \"INFO\"\n"
        ),
        encoding="utf-8",
    )

    result, _state_path, _helper_log_path, openai_log_path = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={"final_page_content": "# Replacement page\n\nUpdated content.\n"},
        extra_env={"WIKI_AGENT_CONFIG_PATH": str(config_path)},
    )

    assert result.returncode == 0, result.stderr
    openai_calls = _read_jsonl(openai_log_path)
    assert len(openai_calls) == 1
    assert openai_calls[0]["model"] == "gpt-4.1-mini"
    assert openai_calls[0]["timeout"] == 12.5


def test_runner_main_loads_repo_dotenv_before_reading_settings(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        (
            "OPENAI_API_KEY=dotenv-openai-key\n"
            "WIKI_AGENT_RUNNER_OPENAI_MODEL=gpt-4.1-nano\n"
            "WIKI_AGENT_RUNNER_MAX_INPUT_BYTES=111\n"
            "WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES=222\n"
            "WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS=7.5\n"
        ),
        encoding="utf-8",
    )
    settings_seen: dict[str, object] = {}

    monkeypatch.setattr(runner.environment, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("WIKI_AGENT_RUNNER_OPENAI_MODEL", raising=False)
    monkeypatch.delenv("WIKI_AGENT_RUNNER_MAX_INPUT_BYTES", raising=False)
    monkeypatch.delenv("WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES", raising=False)
    monkeypatch.delenv("WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS", raising=False)
    def fake_generate_runner_decision(_prompt: str, settings: runner.RunnerSettings) -> runner.RunnerDecision:
        settings_seen["settings"] = settings
        return runner.RunnerDecision(action="update", final_page_content="# Replacement page\n")

    monkeypatch.setattr(runner, "_read_page", lambda _target_page: "# Current page\n")
    monkeypatch.setattr(runner, "_load_prompt_template", lambda: "{{PROMPT}}")
    monkeypatch.setattr(
        runner,
        "render_prompt",
        lambda **_kwargs: "rendered prompt",
    )
    monkeypatch.setattr(runner, "_generate_runner_decision", fake_generate_runner_decision)
    monkeypatch.setattr(runner, "_save_page", lambda _target_page, _content: None)
    monkeypatch.setattr(runner, "_delete_comment", lambda _comment_identity, _target_page: None)
    monkeypatch.setattr(runner, "_list_comments", lambda _target_page: [])
    monkeypatch.setattr(
        runner.sys,
        "stdin",
        io.StringIO(json.dumps(_envelope(original_comment_text="@marvin update", prompt="update"))),
    )
    monkeypatch.setattr(runner.sys, "stdout", io.StringIO())

    assert runner.main() == 0
    assert settings_seen["settings"] == runner.RunnerSettings(
        api_key="dotenv-openai-key",
        openai_model="gpt-4.1-nano",
        max_input_bytes=111,
        max_output_bytes=222,
        model_timeout_seconds=7.5,
    )


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
        "message": "model output must be a JSON object matching the runner decision schema",
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


def test_runner_returns_structured_failure_for_invalid_max_input_bytes_env(tmp_path: Path) -> None:
    result, state_path, helper_log_path, openai_log_path = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={"final_page_content": "# Replacement page\n"},
        extra_env={"WIKI_AGENT_RUNNER_MAX_INPUT_BYTES": "not-an-int"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "UPDATE_FAILED",
        "error_code": "RUNNER_CONFIG_INVALID",
        "message": "WIKI_AGENT_RUNNER_MAX_INPUT_BYTES must be a positive integer",
    }
    assert _read_jsonl(openai_log_path) == []
    assert _read_jsonl(helper_log_path) == []

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] is None


def test_runner_returns_structured_failure_for_invalid_max_output_bytes_env(tmp_path: Path) -> None:
    result, state_path, helper_log_path, openai_log_path = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={"final_page_content": "# Replacement page\n"},
        extra_env={"WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES": "0"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "UPDATE_FAILED",
        "error_code": "RUNNER_CONFIG_INVALID",
        "message": "WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES must be a positive integer",
    }
    assert _read_jsonl(openai_log_path) == []
    assert _read_jsonl(helper_log_path) == []

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] is None


def test_runner_returns_structured_failure_for_invalid_model_timeout_env(tmp_path: Path) -> None:
    result, state_path, helper_log_path, openai_log_path = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={"final_page_content": "# Replacement page\n"},
        extra_env={"WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS": "-1"},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "UPDATE_FAILED",
        "error_code": "RUNNER_CONFIG_INVALID",
        "message": "WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS must be a positive number",
    }
    assert _read_jsonl(openai_log_path) == []
    assert _read_jsonl(helper_log_path) == []

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] is None


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


def test_runner_executes_visible_rejection_flow_for_cross_page_request(tmp_path: Path) -> None:
    result, state_path, helper_log_path, openai_log_path = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={
            "action": "reject",
            "final_page_content": None,
            "rejection_reason_code": "CROSS_PAGE_REQUEST",
            "explanation": "This agent can only update the page where the comment was posted.",
        },
        original_comment_text="@marvin update /other-page too",
        prompt="update /other-page too",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "REJECTED_WITH_COMMENT"}

    helper_calls = _read_jsonl(helper_log_path)
    assert [call["command"] for call in helper_calls] == [
        "page.get",
        "comments.create",
        "comments.list",
        "comments.delete",
        "comments.list",
    ]

    replacement_comment = helper_calls[1]["content"]
    assert replacement_comment == (
        '<!-- wiki-agent:rejection source_comment_id="comment-1" '
        'reason_code="CROSS_PAGE_REQUEST" -->\n\n'
        "Marvin could not process this request.\n\n"
        "> @marvin update /other-page too\n\n"
        "Reason (`CROSS_PAGE_REQUEST`): This agent can only update the page where the comment was posted.\n"
    )

    openai_calls = _read_jsonl(openai_log_path)
    assert len(openai_calls) == 1

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] is None
    assert state["deleted_comment_ids"] == ["comment-1"]
    assert state["comments"] == [
        {
            "id": "comment-created-1",
            "text": replacement_comment,
        }
    ]


def test_runner_truncates_long_original_comment_in_rejection_comment(tmp_path: Path) -> None:
    original_comment_text = "@marvin " + ("very long request " * 40).strip()
    result, _, helper_log_path, _ = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={
            "action": "reject",
            "final_page_content": None,
            "rejection_reason_code": "UNSUPPORTED_ACTION",
            "explanation": "This runner does not support that kind of request.",
        },
        original_comment_text=original_comment_text,
        prompt=original_comment_text.removeprefix("@marvin ").strip(),
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "REJECTED_WITH_COMMENT"}

    helper_calls = _read_jsonl(helper_log_path)
    replacement_comment = helper_calls[1]["content"]
    assert "> [original comment truncated for length]\n" in replacement_comment
    assert original_comment_text not in replacement_comment


def test_runner_returns_update_failed_when_replacement_comment_confirmation_fails(
    tmp_path: Path,
) -> None:
    result, _, helper_log_path, _ = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={
            "action": "reject",
            "final_page_content": None,
            "rejection_reason_code": "UNCLEAR_REQUEST",
            "explanation": "The request was not specific enough to execute safely.",
        },
        suppress_created_comment=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "UPDATE_FAILED",
        "error_code": "REPLACEMENT_CONFIRMATION_FAILED",
        "message": "replacement comment was not present during confirmation",
    }
    assert [call["command"] for call in _read_jsonl(helper_log_path)] == [
        "page.get",
        "comments.create",
        "comments.list",
    ]


def test_runner_returns_delete_failed_after_confirmed_rejection_when_delete_confirmation_fails(
    tmp_path: Path,
) -> None:
    result, state_path, helper_log_path, _ = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={
            "action": "reject",
            "final_page_content": None,
            "rejection_reason_code": "FORBIDDEN_ACTION",
            "explanation": "This request asks for an action the agent must not perform.",
        },
        keep_comment_after_delete=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "DELETE_FAILED",
        "error_code": "DELETE_CONFIRMATION_FAILED",
        "message": "source comment still present after delete confirmation",
    }
    assert [call["command"] for call in _read_jsonl(helper_log_path)] == [
        "page.get",
        "comments.create",
        "comments.list",
        "comments.delete",
        "comments.list",
    ]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["deleted_comment_ids"] == ["comment-1"]


def test_runner_confirms_replacement_comment_when_listed_text_is_stripped(tmp_path: Path) -> None:
    result, state_path, helper_log_path, _ = _run_runner(
        tmp_path,
        page_markdown="# Current page\n",
        openai_output={
            "action": "reject",
            "final_page_content": None,
            "rejection_reason_code": "UNCLEAR_REQUEST",
            "explanation": "The request was not specific enough to execute safely.",
        },
        strip_created_comment_text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "REJECTED_WITH_COMMENT"}
    assert [call["command"] for call in _read_jsonl(helper_log_path)] == [
        "page.get",
        "comments.create",
        "comments.list",
        "comments.delete",
        "comments.list",
    ]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["deleted_comment_ids"] == ["comment-1"]


@pytest.mark.parametrize(
    "rejection_reason_code",
    sorted(runner.REJECTION_REASON_CODES),
)
def test_validate_model_payload_accepts_all_rejection_reason_codes(rejection_reason_code: str) -> None:
    decision = runner._validate_model_payload(
        {
            "action": "reject",
            "final_page_content": None,
            "rejection_reason_code": rejection_reason_code,
            "explanation": "Human-readable explanation.",
        }
    )

    assert decision == runner.RunnerDecision(
        action="reject",
        rejection_reason_code=rejection_reason_code,
        explanation="Human-readable explanation.",
    )


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
    suppress_created_comment: bool = False,
    strip_created_comment_text: bool = False,
    original_comment_text: str = "@marvin # Rewrite the page\n\nMake it shorter.\n",
    prompt: str = "# Rewrite the page\n\nMake it shorter.\n",
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
                "comments": [{"id": "comment-1", "text": original_comment_text}],
                "keep_comment_after_delete": keep_comment_after_delete,
                "suppress_created_comment": suppress_created_comment,
                "strip_created_comment_text": strip_created_comment_text,
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
    for name in (
        "OPENAI_API_KEY",
        "WIKI_AGENT_CONFIG_PATH",
        "WIKI_AGENT_RUNNER_OPENAI_MODEL",
        "WIKI_AGENT_RUNNER_MAX_INPUT_BYTES",
        "WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES",
        "WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS",
    ):
        env.pop(name, None)
    if not (extra_env and "WIKI_AGENT_CONFIG_PATH" in extra_env):
        env["OPENAI_API_KEY"] = "test-openai-key"
        env["WIKI_AGENT_RUNNER_OPENAI_MODEL"] = runner.DEFAULT_OPENAI_MODEL
        env["WIKI_AGENT_RUNNER_MAX_INPUT_BYTES"] = str(runner.DEFAULT_MAX_INPUT_BYTES)
        env["WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES"] = str(runner.DEFAULT_MAX_OUTPUT_BYTES)
        env["WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS"] = str(
            runner.DEFAULT_MODEL_TIMEOUT_SECONDS
        )
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [script],
        input=json.dumps(_envelope(original_comment_text=original_comment_text, prompt=prompt)),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return result, state_path, helper_log_path, openai_log_path


def _envelope(*, original_comment_text: str, prompt: str) -> dict[str, object]:
    return {
        "prompt": prompt,
        "original_comment_text": original_comment_text,
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
            "    def __init__(self, *, api_key=None, timeout=None):\n"
            "        self.api_key = api_key\n"
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
            "        payload = OUTPUT_PAYLOAD\n"
            "        if isinstance(payload, dict) and 'action' not in payload and set(payload.keys()) == {'final_page_content'}:\n"
            "            payload = {\n"
            "                'action': 'update',\n"
            "                'final_page_content': payload['final_page_content'],\n"
            "                'rejection_reason_code': None,\n"
            "                'explanation': None,\n"
            "            }\n"
            "        return types.SimpleNamespace(status='completed', output_text=json.dumps(payload))\n"
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
            "if command == 'create':\n"
            "    page = sys.argv[2]\n"
            "    content = pathlib.Path(sys.argv[3]).read_text(encoding='utf-8')\n"
            "    line = json.dumps({'command': 'comments.create', 'page': page, 'content': content}) + '\\n'\n"
            "    existing = log_path.read_text(encoding='utf-8') if log_path.exists() else ''\n"
            "    log_path.write_text(existing + line, encoding='utf-8')\n"
            "    comments = state.setdefault('comments', [])\n"
            "    if not state.get('suppress_created_comment'):\n"
            "        stored_text = content.strip() if state.get('strip_created_comment_text') else content\n"
            "        comments.append({'id': f'comment-created-{len(comments)}', 'text': stored_text})\n"
            "    state_path.write_text(json.dumps(state), encoding='utf-8')\n"
            "    comment_id = comments[-1]['id'] if comments else 'comment-created-0'\n"
            "    sys.stdout.write(json.dumps({'id': comment_id}))\n"
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
