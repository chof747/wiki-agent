from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


DEFAULT_OPENAI_MODEL = "gpt-4o-2024-08-06"
DEFAULT_MAX_INPUT_BYTES = 32 * 1024
DEFAULT_MAX_OUTPUT_BYTES = 40 * 1024
DEFAULT_MODEL_TIMEOUT_SECONDS = 60.0
PROMPT_TEMPLATE_RESOURCE = "page_update_prompt.md"
PROMPT_TEMPLATE_PACKAGE = "wiki_agent.prompts"
REQUIRED_PROMPT_TOKENS = (
    "{{TARGET_PAGE}}",
    "{{PROMPT}}",
    "{{ORIGINAL_COMMENT_TEXT}}",
    "{{CURRENT_PAGE_CONTENT}}",
)


class RunnerContractError(ValueError):
    """Raised when the prompt envelope is malformed."""


class PromptTemplateError(ValueError):
    """Raised when the prompt template cannot be rendered safely."""


class HelperCommandError(RuntimeError):
    """Raised when a helper command fails or returns invalid data."""


class ModelOutputError(ValueError):
    """Raised when model output does not satisfy the runner contract."""


@dataclass(frozen=True)
class RunnerEnvelope:
    prompt: str
    original_comment_text: str
    target_page: str
    comment_identity: str

    @classmethod
    def from_stdin(cls) -> "RunnerEnvelope":
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            raise RunnerContractError("stdin must contain one JSON prompt envelope") from exc

        if not isinstance(payload, dict):
            raise RunnerContractError("prompt envelope must be a JSON object")

        prompt = _require_string(payload, "prompt")
        original_comment_text = _require_string(payload, "original_comment_text")
        target_page = _require_string(payload, "target_page")
        comment_identity = _require_string(payload, "comment_identity")

        return cls(
            prompt=prompt,
            original_comment_text=original_comment_text,
            target_page=target_page,
            comment_identity=comment_identity,
        )


def main(argv: list[str] | None = None) -> int:
    del argv

    try:
        envelope = RunnerEnvelope.from_stdin()
    except RunnerContractError as exc:
        _emit_response("UPDATE_FAILED", "PROMPT_ENVELOPE_INVALID", str(exc))
        return 0

    try:
        current_page_content = _read_page(envelope.target_page)
    except HelperCommandError as exc:
        _emit_response("UPDATE_FAILED", "PAGE_READ_FAILED", str(exc))
        return 0

    try:
        rendered_prompt = render_prompt(
            template=_load_prompt_template(),
            prompt=envelope.prompt,
            original_comment_text=envelope.original_comment_text,
            target_page=envelope.target_page,
            current_page_content=current_page_content,
        )
    except PromptTemplateError as exc:
        _emit_response("UPDATE_FAILED", "PROMPT_TEMPLATE_INVALID", str(exc))
        return 0

    if _utf8_len(rendered_prompt) > _max_input_bytes():
        _emit_response("UPDATE_FAILED", "INPUT_TOO_LARGE", "rendered model input exceeded byte limit")
        return 0

    try:
        final_page_content = _generate_final_page_content(rendered_prompt)
    except ModelOutputError as exc:
        _emit_response("UPDATE_FAILED", "MODEL_OUTPUT_INVALID", str(exc))
        return 0
    except Exception as exc:
        _emit_response("UPDATE_FAILED", "MODEL_CALL_FAILED", _bounded_message(exc))
        return 0

    if _utf8_len(final_page_content) > _max_output_bytes():
        _emit_response("UPDATE_FAILED", "OUTPUT_TOO_LARGE", "model output exceeded byte limit")
        return 0

    if final_page_content == current_page_content:
        _emit_response("UPDATE_FAILED", "NO_CONTENT_CHANGE", "model output did not change the current page content")
        return 0

    try:
        _save_page(envelope.target_page, final_page_content)
    except HelperCommandError as exc:
        _emit_response("UPDATE_FAILED", "PAGE_SAVE_FAILED", str(exc))
        return 0

    try:
        confirmed_markdown = _read_page(envelope.target_page)
    except HelperCommandError as exc:
        _emit_response("UPDATE_FAILED", "UPDATE_CONFIRMATION_FAILED", str(exc))
        return 0

    if confirmed_markdown != final_page_content:
        _emit_response(
            "UPDATE_FAILED",
            "UPDATE_CONFIRMATION_FAILED",
            "saved page content did not match confirmation fetch",
        )
        return 0

    try:
        _delete_comment(envelope.comment_identity, envelope.target_page)
    except HelperCommandError as exc:
        _emit_response("DELETE_FAILED", "COMMENT_DELETE_FAILED", str(exc))
        return 0

    try:
        remaining_comments = _list_comments(envelope.target_page)
    except HelperCommandError as exc:
        _emit_response("DELETE_FAILED", "DELETE_CONFIRMATION_FAILED", str(exc))
        return 0

    if any(comment.get("id") == envelope.comment_identity for comment in remaining_comments):
        _emit_response(
            "DELETE_FAILED",
            "DELETE_CONFIRMATION_FAILED",
            "source comment still present after delete confirmation",
        )
        return 0

    _emit_response("SUCCESS")
    return 0


def render_prompt(
    *,
    template: str,
    prompt: str,
    original_comment_text: str,
    target_page: str,
    current_page_content: str,
) -> str:
    missing = [token for token in REQUIRED_PROMPT_TOKENS if token not in template]
    if missing:
        missing_list = ", ".join(missing)
        raise PromptTemplateError(f"missing required placeholder(s): {missing_list}")

    replacements = {
        "{{TARGET_PAGE}}": target_page,
        "{{PROMPT}}": prompt,
        "{{ORIGINAL_COMMENT_TEXT}}": original_comment_text,
        "{{CURRENT_PAGE_CONTENT}}": current_page_content,
    }
    pattern = re.compile("|".join(re.escape(token) for token in REQUIRED_PROMPT_TOKENS))
    return pattern.sub(lambda match: replacements[match.group(0)], template)


def _generate_final_page_content(rendered_prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(timeout=_model_timeout_seconds())
    response = client.responses.create(
        model=os.getenv("WIKI_AGENT_RUNNER_OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        input=[
            {
                "role": "system",
                "content": (
                    "You update exactly one attached wiki page. "
                    "Return only structured JSON matching the provided schema."
                ),
            },
            {"role": "user", "content": rendered_prompt},
        ],
        text={"format": _response_format_schema()},
    )

    status = getattr(response, "status", None)
    if status not in {None, "completed"}:
        raise ModelOutputError("model response did not complete successfully")

    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str) or not output_text:
        raise ModelOutputError("model response did not include structured output text")

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise ModelOutputError("model output was not valid JSON") from exc

    return _validate_model_payload(payload)


def _response_format_schema() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "wiki_agent_page_update",
        "schema": {
            "type": "object",
            "properties": {
                "final_page_content": {"type": "string"},
            },
            "required": ["final_page_content"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _validate_model_payload(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ModelOutputError("model output must contain exactly one string field: final_page_content")

    if set(payload.keys()) != {"final_page_content"}:
        raise ModelOutputError("model output must contain exactly one string field: final_page_content")

    final_page_content = payload.get("final_page_content")
    if not isinstance(final_page_content, str):
        raise ModelOutputError("model output must contain exactly one string field: final_page_content")

    return final_page_content


def _load_prompt_template() -> str:
    return resources.files(PROMPT_TEMPLATE_PACKAGE).joinpath(PROMPT_TEMPLATE_RESOURCE).read_text(
        encoding="utf-8"
    )


def _read_page(target_page: str) -> str:
    result = _run_helper(["wikigo-page", "get", target_page])

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HelperCommandError("wikigo-page get emitted invalid JSON") from exc

    if not isinstance(payload, dict):
        raise HelperCommandError("wikigo-page get must return a JSON object")

    markdown = payload.get("markdown")
    if isinstance(markdown, str):
        return markdown

    content = payload.get("content")
    if isinstance(content, str):
        return content

    raise HelperCommandError("wikigo-page get response is missing markdown content")


def _save_page(target_page: str, markdown: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(markdown)
            temp_path = Path(handle.name)

        _run_helper(["wikigo-page", "save", target_page, str(temp_path)])
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _delete_comment(comment_identity: str, target_page: str) -> None:
    _run_helper(["wikigo-comments", "delete", comment_identity, target_page])


def _list_comments(target_page: str) -> list[dict[str, Any]]:
    result = _run_helper(["wikigo-comments", "list", target_page])

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HelperCommandError("wikigo-comments list emitted invalid JSON") from exc

    if not isinstance(payload, list):
        raise HelperCommandError("wikigo-comments list must return a JSON array")

    comments: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            comments.append(item)
    return comments


def _run_helper(argv: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "no helper diagnostics"
        raise HelperCommandError(f"{argv[0]} failed: {stderr}")
    return result


def _emit_response(status: str, error_code: str | None = None, message: str | None = None) -> None:
    payload: dict[str, str] = {"status": status}
    if error_code is not None:
        payload["error_code"] = error_code
    if message is not None:
        payload["message"] = message
        print(message, file=sys.stderr)
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RunnerContractError(f"prompt envelope field '{key}' must be a non-empty string")
    return value


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _max_input_bytes() -> int:
    return _read_positive_int_env("WIKI_AGENT_RUNNER_MAX_INPUT_BYTES", DEFAULT_MAX_INPUT_BYTES)


def _max_output_bytes() -> int:
    return _read_positive_int_env("WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES", DEFAULT_MAX_OUTPUT_BYTES)


def _model_timeout_seconds() -> float:
    return _read_positive_float_env(
        "WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS",
        DEFAULT_MODEL_TIMEOUT_SECONDS,
    )


def _read_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RunnerContractError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RunnerContractError(f"{name} must be a positive integer")
    return value


def _read_positive_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RunnerContractError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise RunnerContractError(f"{name} must be a positive number")
    return value


def _bounded_message(exc: Exception) -> str:
    return str(exc).strip()[:500] or exc.__class__.__name__


if __name__ == "__main__":
    raise SystemExit(main())
