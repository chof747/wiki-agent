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

from wiki_agent import environment
from wiki_agent.config import load_config
from wiki_agent.domain import STATUS_UPDATE_FAILED
from wiki_agent.runner_completion import RunnerCompletion
from wiki_agent.wikigo_adapter import WikiGoAdapterError, parse_helper_comments_output, parse_helper_page_output


DEFAULT_OPENAI_MODEL = "gpt-4o-2024-08-06"
DEFAULT_MAX_INPUT_BYTES = 32 * 1024
DEFAULT_MAX_OUTPUT_BYTES = 40 * 1024
DEFAULT_MODEL_TIMEOUT_SECONDS = 60.0
DEFAULT_REJECTION_QUOTE_MAX_BYTES = 500
PROMPT_TEMPLATE_RESOURCE = "page_update_prompt.md"
PROMPT_TEMPLATE_PACKAGE = "wiki_agent.prompts"
REQUIRED_PROMPT_TOKENS = (
    "{{TARGET_PAGE}}",
    "{{PROMPT}}",
    "{{ORIGINAL_COMMENT_TEXT}}",
    "{{CURRENT_PAGE_CONTENT}}",
)
REJECTION_REASON_CODES = {
    "UNCLEAR_REQUEST",
    "MULTI_TARGET_REQUEST",
    "CROSS_PAGE_REQUEST",
    "FORBIDDEN_ACTION",
    "UNSUPPORTED_ACTION",
    "MISSING_CONTEXT",
    "SAFETY_REFUSAL",
}


class RunnerContractError(ValueError):
    """Raised when the prompt envelope is malformed."""


class PromptTemplateError(ValueError):
    """Raised when the prompt template cannot be rendered safely."""


class HelperCommandError(RuntimeError):
    """Raised when a helper command fails or returns invalid data."""


class ModelOutputError(ValueError):
    """Raised when model output does not satisfy the runner contract."""


@dataclass(frozen=True)
class RunnerDecision:
    action: str
    final_page_content: str | None = None
    rejection_reason_code: str | None = None
    explanation: str | None = None


@dataclass(frozen=True)
class RunnerSettings:
    api_key: str
    openai_model: str
    max_input_bytes: int
    max_output_bytes: int
    model_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "RunnerSettings":
        config = _load_app_config_from_env()
        config_openai = config.runner_openai if config is not None else None
        return cls(
            api_key=_read_non_empty_string_env(
                "OPENAI_API_KEY",
                config_openai.api_key if config_openai is not None else None,
            ),
            openai_model=_read_non_empty_string_env(
                "WIKI_AGENT_RUNNER_OPENAI_MODEL",
                config_openai.model if config_openai is not None else DEFAULT_OPENAI_MODEL,
            ),
            max_input_bytes=_read_positive_int_env(
                "WIKI_AGENT_RUNNER_MAX_INPUT_BYTES",
                config_openai.max_input_bytes if config_openai is not None else DEFAULT_MAX_INPUT_BYTES,
            ),
            max_output_bytes=_read_positive_int_env(
                "WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES",
                config_openai.max_output_bytes if config_openai is not None else DEFAULT_MAX_OUTPUT_BYTES,
            ),
            model_timeout_seconds=_read_positive_float_env(
                "WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS",
                config_openai.timeout_seconds if config_openai is not None else DEFAULT_MODEL_TIMEOUT_SECONDS,
            ),
        )


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

        expected_keys = {"prompt", "original_comment_text", "target_page", "comment_identity"}
        unexpected_keys = sorted(set(payload) - expected_keys)
        if unexpected_keys:
            raise RunnerContractError(
                "prompt envelope contains unexpected field(s): " + ", ".join(unexpected_keys)
            )

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
    environment.load_repo_environment()
    completion = RunnerCompletion(
        read_page=_read_page,
        save_page=_save_page,
        create_comment=_create_comment,
        list_comments=_list_comments,
        delete_comment=_delete_comment,
    )

    try:
        envelope = RunnerEnvelope.from_stdin()
    except RunnerContractError as exc:
        _emit_response(STATUS_UPDATE_FAILED, "PROMPT_ENVELOPE_INVALID", str(exc))
        return 0

    try:
        settings = RunnerSettings.from_env()
    except RunnerContractError as exc:
        _emit_response(STATUS_UPDATE_FAILED, "RUNNER_CONFIG_INVALID", str(exc))
        return 0

    try:
        current_page_content = _read_page(envelope.target_page)
    except HelperCommandError as exc:
        _emit_response(STATUS_UPDATE_FAILED, "PAGE_READ_FAILED", str(exc))
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
        _emit_response(STATUS_UPDATE_FAILED, "PROMPT_TEMPLATE_INVALID", str(exc))
        return 0

    if _utf8_len(rendered_prompt) > settings.max_input_bytes:
        _emit_response(STATUS_UPDATE_FAILED, "INPUT_TOO_LARGE", "rendered model input exceeded byte limit")
        return 0

    try:
        decision = _generate_runner_decision(rendered_prompt, settings)
    except ModelOutputError as exc:
        _emit_response(STATUS_UPDATE_FAILED, "MODEL_OUTPUT_INVALID", str(exc))
        return 0
    except Exception as exc:
        _emit_response(STATUS_UPDATE_FAILED, "MODEL_CALL_FAILED", _bounded_message(exc))
        return 0

    if decision.action == "update":
        final_page_content = decision.final_page_content
        assert final_page_content is not None

        if _utf8_len(final_page_content) > settings.max_output_bytes:
            _emit_response(STATUS_UPDATE_FAILED, "OUTPUT_TOO_LARGE", "model output exceeded byte limit")
            return 0

        if final_page_content == current_page_content:
            _emit_response(STATUS_UPDATE_FAILED, "NO_CONTENT_CHANGE", "model output did not change the current page content")
            return 0

        result = completion.complete_update(
            target_page=envelope.target_page,
            comment_identity=envelope.comment_identity,
            final_page_content=final_page_content,
        )
    else:
        replacement_comment = _build_rejection_comment(
            comment_identity=envelope.comment_identity,
            original_comment_text=envelope.original_comment_text,
            rejection_reason_code=decision.rejection_reason_code or "",
            explanation=decision.explanation or "",
        )
        result = completion.complete_rejection(
            target_page=envelope.target_page,
            comment_identity=envelope.comment_identity,
            replacement_comment=replacement_comment,
        )

    _emit_response(result.status, result.error_code, result.message)
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


def _generate_runner_decision(rendered_prompt: str, settings: RunnerSettings) -> RunnerDecision:
    from openai import OpenAI

    client = OpenAI(api_key=settings.api_key, timeout=settings.model_timeout_seconds)
    response = client.responses.create(
        model=settings.openai_model,
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
        "name": "wiki_agent_runner_decision",
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["update", "reject"]},
                "final_page_content": {"type": ["string", "null"]},
                "rejection_reason_code": {"type": ["string", "null"]},
                "explanation": {"type": ["string", "null"]},
            },
            "required": ["action", "final_page_content", "rejection_reason_code", "explanation"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _validate_model_payload(payload: object) -> RunnerDecision:
    if not isinstance(payload, dict):
        raise ModelOutputError("model output must be a JSON object matching the runner decision schema")

    expected_keys = {"action", "final_page_content", "rejection_reason_code", "explanation"}
    if set(payload.keys()) != expected_keys:
        raise ModelOutputError("model output must be a JSON object matching the runner decision schema")

    action = payload.get("action")
    if action == "update":
        final_page_content = payload.get("final_page_content")
        if not isinstance(final_page_content, str):
            raise ModelOutputError("update action must include final_page_content")
        if payload.get("rejection_reason_code") is not None or payload.get("explanation") is not None:
            raise ModelOutputError("update action must not include rejection fields")
        return RunnerDecision(action="update", final_page_content=final_page_content)

    if action == "reject":
        rejection_reason_code = payload.get("rejection_reason_code")
        explanation = payload.get("explanation")
        if rejection_reason_code not in REJECTION_REASON_CODES:
            raise ModelOutputError("reject action must include a valid rejection_reason_code")
        if not isinstance(explanation, str) or not explanation.strip():
            raise ModelOutputError("reject action must include a non-empty explanation")
        if payload.get("final_page_content") is not None:
            raise ModelOutputError("reject action must not include final_page_content")
        return RunnerDecision(
            action="reject",
            rejection_reason_code=rejection_reason_code,
            explanation=explanation.strip(),
        )

    raise ModelOutputError("model output must set action to update or reject")


def _load_prompt_template() -> str:
    try:
        return resources.files(PROMPT_TEMPLATE_PACKAGE).joinpath(PROMPT_TEMPLATE_RESOURCE).read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        raise PromptTemplateError("failed to load prompt template resource") from exc


def _read_page(target_page: str) -> str:
    result = _run_helper(["wikigo-helper", "page", "get", target_page])

    try:
        return parse_helper_page_output(result.stdout)
    except WikiGoAdapterError as exc:
        raise HelperCommandError(str(exc)) from exc


def _save_page(target_page: str, markdown: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(markdown)
            temp_path = Path(handle.name)

        _run_helper(["wikigo-helper", "page", "save", target_page, str(temp_path)])
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _delete_comment(comment_identity: str, target_page: str) -> None:
    _run_helper(["wikigo-comments", "delete", comment_identity, target_page])


def _create_comment(target_page: str, content: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(content)
            temp_path = Path(handle.name)

        _run_helper(["wikigo-comments", "create", target_page, str(temp_path)])
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _list_comments(target_page: str) -> list[dict[str, Any]]:
    result = _run_helper(["wikigo-comments", "list", target_page])

    try:
        return parse_helper_comments_output(result.stdout)
    except WikiGoAdapterError as exc:
        raise HelperCommandError(str(exc)) from exc


def _build_rejection_comment(
    *,
    comment_identity: str,
    original_comment_text: str,
    rejection_reason_code: str,
    explanation: str,
) -> str:
    quoted_text, truncated = _truncate_rejection_quote(original_comment_text)
    quoted_lines = [f"> {line}" if line else ">" for line in quoted_text.splitlines()]
    if truncated:
        quoted_lines.append("> [original comment truncated for length]")

    return (
        f'<!-- wiki-agent:rejection source_comment_id="{comment_identity}" '
        f'reason_code="{rejection_reason_code}" -->\n\n'
        "Marvin could not process this request.\n\n"
        f"{'\n'.join(quoted_lines)}\n\n"
        f"Reason (`{rejection_reason_code}`): {explanation}\n"
    )


def _truncate_rejection_quote(original_comment_text: str) -> tuple[str, bool]:
    encoded = original_comment_text.encode("utf-8")
    if len(encoded) <= DEFAULT_REJECTION_QUOTE_MAX_BYTES:
        return original_comment_text, False

    truncated = encoded[:DEFAULT_REJECTION_QUOTE_MAX_BYTES].decode("utf-8", errors="ignore").rstrip()
    return truncated, True


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


def _read_non_empty_string_env(name: str, default: str | None) -> str:
    raw = os.getenv(name)
    if raw is None:
        if default is None:
            raise RunnerContractError(f"{name} must be a non-empty string")
        return default

    value = raw.strip()
    if not value:
        raise RunnerContractError(f"{name} must be a non-empty string")
    return value


def _load_app_config_from_env():
    config_path_value = os.getenv("WIKI_AGENT_CONFIG_PATH")
    if not config_path_value:
        return None
    return load_config(Path(config_path_value))


def _bounded_message(exc: Exception) -> str:
    return str(exc).strip()[:500] or exc.__class__.__name__


if __name__ == "__main__":
    raise SystemExit(main())
