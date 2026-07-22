from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from wiki_agent.contracts.prompt_envelope import PromptEnvelope, PromptEnvelopeError
from wiki_agent.domain import STATUS_UPDATE_FAILED
from wiki_agent.ops import environment
from wiki_agent.ops.config import load_runner_openai_config, load_runner_research_budget_config
from wiki_agent.runner.capabilities.orchestration import CapabilityContext, CapabilityOrchestrator, CapabilityResult
from wiki_agent.runner.capabilities.web_research import (
    WebResearchBudget,
    WebResearchBudgetConstraint,
    WebResearchOutput,
)
from wiki_agent.runner.completion import CompletionResult, ConfirmedPrimaryAction, RunnerCompletion
from wiki_agent.runner.model_transport import (
    ModelTransport,
    ModelTransportError,
    ModelTransportRequest,
    OpenAIResponsesTransport,
    parse_json_output,
)
from wiki_agent.runner.page_composition import PageComposer, PageCompositionInput
from wiki_agent.wikigo.adapter import (
    WikiGoAdapterError,
    parse_helper_comments_output,
    parse_helper_page_output,
)


DEFAULT_OPENAI_MODEL = "gpt-4o-2024-08-06"
DEFAULT_MAX_INPUT_BYTES = 32 * 1024
DEFAULT_MAX_OUTPUT_BYTES = 40 * 1024
DEFAULT_MODEL_TIMEOUT_SECONDS = 60.0
DEFAULT_REJECTION_QUOTE_MAX_BYTES = 500
HOSTED_WEB_SEARCH_TOOL = ({"type": "web_search"},)
HOSTED_WEB_SEARCH_INCLUDE = ("web_search_call.action.sources",)
REQUIRED_TOOL_CHOICE = "required"
DEFAULT_SYSTEM_INSTRUCTION = (
    "You update exactly one attached wiki page. "
    "Return only structured JSON matching the provided schema. "
    "If you use hosted web search, issue concise search queries tailored to the user's request and the target topic. "
    "Never submit the full prompt, full page content, or policy text as a search query."
)
WEB_RESEARCH_HINT_PATTERN = re.compile(
    r"\b(current|latest|news|top stor(?:y|ies)|today|recent|search|web research|with links?|reddit|forum|community|sources?|cit(?:e|ation)s?)\b|[a-z0-9-]+\.[a-z]{2,}",
    re.IGNORECASE,
)
FRESH_VERIFICATION_HINT_PATTERN = re.compile(
    r"\b(verify|verified|official sources?|authoritative sources?)\b",
    re.IGNORECASE,
)
CURRENT_STATE_TEMPORAL_HINT_PATTERN = re.compile(
    r"\b(as of|current|currently|latest|today|up to date|up-to-date)\b",
    re.IGNORECASE,
)
CURRENT_STATE_CLAIM_HINT_PATTERN = re.compile(
    r"\b(version|release|price|pricing|schedule|officeholder|office holder|office-holder|mayor|governor|president|prime minister|news|top stor(?:y|ies)|headline|headlines)\b",
    re.IGNORECASE,
)
HTTP_URL_PATTERN = re.compile(r"https?://\S+")
PROMPT_TEMPLATE_RESOURCE = "page_update_prompt.md"
PROMPT_TEMPLATE_PACKAGE = "wiki_agent.runner.prompts"
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


class PromptTemplateError(ValueError):
    """Raised when the prompt template cannot be rendered safely."""


class HelperCommandError(RuntimeError):
    """Raised when a helper command fails or returns invalid data."""


class ModelOutputError(ValueError):
    """Raised when model output does not satisfy the runner contract."""


@dataclass(frozen=True)
class UpdateDecision:
    final_page_content: str


@dataclass(frozen=True)
class RejectDecision:
    rejection_reason_code: str
    explanation: str


RunnerDecision = UpdateDecision | RejectDecision


@dataclass(frozen=True)
class RunnerSettings:
    api_key: str
    openai_model: str
    max_input_bytes: int
    max_output_bytes: int
    model_timeout_seconds: float
    max_search_actions: int
    max_opened_links: int

    @classmethod
    def from_env(cls) -> "RunnerSettings":
        config_openai = _load_runner_openai_config_from_env()
        config_research_budget = _load_runner_research_budget_config_from_env()
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
            max_search_actions=_read_positive_int_env(
                "WIKI_AGENT_RUNNER_MAX_SEARCH_ACTIONS",
                config_research_budget.max_search_actions if config_research_budget is not None else 3,
            ),
            max_opened_links=_read_positive_int_env(
                "WIKI_AGENT_RUNNER_MAX_OPENED_LINKS",
                config_research_budget.max_opened_links if config_research_budget is not None else 5,
            ),
        )


def main(argv: list[str] | None = None) -> int:
    del argv
    environment.load_repo_environment()
    capability_orchestrator = CapabilityOrchestrator()
    page_composer = PageComposer()
    completion = RunnerCompletion(
        read_page=_read_page,
        save_page=_save_page,
        create_comment=_create_comment,
        list_comments=_list_comments,
        delete_comment=_delete_comment,
    )

    try:
        envelope = PromptEnvelope.from_stdin(sys.stdin)
    except PromptEnvelopeError as exc:
        _emit_response(STATUS_UPDATE_FAILED, "PROMPT_ENVELOPE_INVALID", str(exc))
        return 0

    try:
        settings = RunnerSettings.from_env()
    except ValueError as exc:
        _emit_response(STATUS_UPDATE_FAILED, "RUNNER_CONFIG_INVALID", str(exc))
        return 0

    transport = OpenAIResponsesTransport(
        api_key=settings.api_key,
        timeout_seconds=settings.model_timeout_seconds,
    )

    try:
        current_page_content = _read_page(envelope.target_page)
    except HelperCommandError as exc:
        _emit_response(STATUS_UPDATE_FAILED, "PAGE_READ_FAILED", str(exc))
        return 0

    try:
        capability_result = capability_orchestrator.prepare(
            CapabilityContext(
                prompt=envelope.prompt,
                original_comment_text=envelope.original_comment_text,
                target_page=envelope.target_page,
                current_page_content=current_page_content,
            )
        )
        rendered_prompt = render_prompt(
            template=_load_prompt_template(),
            prompt=envelope.prompt,
            original_comment_text=envelope.original_comment_text,
            target_page=envelope.target_page,
            current_page_content=current_page_content,
            supplemental_sections=capability_result.prompt_sections,
        )
    except PromptTemplateError as exc:
        _emit_response(STATUS_UPDATE_FAILED, "PROMPT_TEMPLATE_INVALID", str(exc))
        return 0

    if _utf8_len(rendered_prompt) > settings.max_input_bytes:
        _emit_response(STATUS_UPDATE_FAILED, "INPUT_TOO_LARGE", "rendered model input exceeded byte limit")
        return 0

    web_research_required = _requires_web_research(
        prompt=envelope.prompt,
        original_comment_text=envelope.original_comment_text,
    )
    fresh_verification_required = _requires_fresh_verification(
        prompt=envelope.prompt,
        original_comment_text=envelope.original_comment_text,
    )
    invocation_as_of_date = _invocation_as_of_date()

    try:
        decision, transport_capability_result = _generate_runner_decision(
            rendered_prompt,
            settings,
            transport=transport,
            user_prompt=_transport_user_prompt(
                prompt=envelope.prompt,
                target_page=envelope.target_page,
            ),
            web_research_required=web_research_required,
        )
    except ModelOutputError as exc:
        _emit_response(STATUS_UPDATE_FAILED, "MODEL_OUTPUT_INVALID", str(exc))
        return 0
    except Exception as exc:
        _emit_response(STATUS_UPDATE_FAILED, "MODEL_CALL_FAILED", _bounded_message(exc))
        return 0

    if fresh_verification_required and not transport_capability_result.artifacts:
        decision = RejectDecision(
            rejection_reason_code="MISSING_CONTEXT",
            explanation=(
                "This request required fresh public web verification, but hosted web search did not surface "
                "a verifiable source during this invocation."
            ),
        )

    result = _complete_runner_decision(
        completion=completion,
        decision=decision,
        envelope=envelope,
        current_page_content=current_page_content,
        invocation_as_of_date=invocation_as_of_date,
        fresh_verification_obtained=fresh_verification_required and bool(transport_capability_result.artifacts),
        degraded_web_research=web_research_required and not transport_capability_result.artifacts,
        capability_result=CapabilityResult(
            prompt_sections=capability_result.prompt_sections,
            artifacts=capability_result.artifacts + transport_capability_result.artifacts,
        ),
        page_composer=page_composer,
        settings=settings,
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
    supplemental_sections: tuple[str, ...] = (),
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
    rendered = pattern.sub(lambda match: replacements[match.group(0)], template)
    if not supplemental_sections:
        return rendered

    return rendered + "\n\n" + "\n\n".join(supplemental_sections)


def _generate_runner_decision(
    rendered_prompt: str,
    settings: RunnerSettings,
    *,
    transport: ModelTransport,
    user_prompt: str,
    web_research_required: bool = False,
) -> tuple[RunnerDecision, CapabilityResult]:
    try:
        response = transport.generate(
            ModelTransportRequest(
                model=settings.openai_model,
                system_instruction=_system_instruction(settings, rendered_prompt=rendered_prompt),
                user_prompt=user_prompt,
                response_format=_response_format_schema(),
                tools=HOSTED_WEB_SEARCH_TOOL,
                tool_choice=REQUIRED_TOOL_CHOICE if web_research_required else None,
                include=HOSTED_WEB_SEARCH_INCLUDE,
                research_budget=WebResearchBudget(
                    max_search_actions=settings.max_search_actions,
                    max_opened_links=settings.max_opened_links,
                ),
            )
        )
        payload = parse_json_output(response.output_text)
    except ModelTransportError as exc:
        raise ModelOutputError(str(exc)) from exc

    artifacts: tuple[object, ...] = response.web_research_outputs
    budget_constrained = response.web_research_budget_usage.materially_constrained or (
        web_research_required
        and response.web_research_outputs
        and response.web_research_budget_usage.search_actions_used >= settings.max_search_actions
    )
    if budget_constrained and response.web_research_outputs:
        artifacts = artifacts + (WebResearchBudgetConstraint(message=_research_budget_constraint_message()),)

    return _validate_model_payload(payload), CapabilityResult(artifacts=artifacts)


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
        return UpdateDecision(final_page_content=final_page_content)

    if action == "reject":
        rejection_reason_code = payload.get("rejection_reason_code")
        explanation = payload.get("explanation")
        if rejection_reason_code not in REJECTION_REASON_CODES:
            raise ModelOutputError("reject action must include a valid rejection_reason_code")
        if not isinstance(explanation, str) or not explanation.strip():
            raise ModelOutputError("reject action must include a non-empty explanation")
        if payload.get("final_page_content") is not None:
            raise ModelOutputError("reject action must not include final_page_content")
        return RejectDecision(
            rejection_reason_code=rejection_reason_code,
            explanation=explanation.strip(),
        )

    raise ModelOutputError("model output must set action to update or reject")


def _complete_runner_decision(
    *,
    completion: RunnerCompletion,
    decision: RunnerDecision,
    envelope: PromptEnvelope,
    current_page_content: str,
    invocation_as_of_date: str,
    fresh_verification_obtained: bool,
    degraded_web_research: bool,
    capability_result: CapabilityResult,
    page_composer: PageComposer,
    settings: RunnerSettings,
) -> CompletionResult:
    primary_action = _execute_primary_action(
        completion=completion,
        decision=decision,
        envelope=envelope,
        current_page_content=current_page_content,
        invocation_as_of_date=invocation_as_of_date,
        fresh_verification_obtained=fresh_verification_obtained,
        degraded_web_research=degraded_web_research,
        capability_result=capability_result,
        page_composer=page_composer,
        settings=settings,
    )
    if isinstance(primary_action, CompletionResult):
        return primary_action

    return completion.complete_finalization(
        target_page=envelope.target_page,
        comment_identity=envelope.comment_identity,
        primary_action=primary_action,
    )


def _execute_primary_action(
    *,
    completion: RunnerCompletion,
    decision: RunnerDecision,
    envelope: PromptEnvelope,
    current_page_content: str,
    invocation_as_of_date: str,
    fresh_verification_obtained: bool,
    degraded_web_research: bool,
    capability_result: CapabilityResult,
    page_composer: PageComposer,
    settings: RunnerSettings,
) -> CompletionResult | ConfirmedPrimaryAction:
    if isinstance(decision, UpdateDecision):
        return _execute_update_primary_action(
            completion=completion,
            decision=decision,
            target_page=envelope.target_page,
            current_page_content=current_page_content,
            invocation_as_of_date=invocation_as_of_date,
            fresh_verification_obtained=fresh_verification_obtained,
            degraded_web_research=degraded_web_research,
            capability_result=capability_result,
            page_composer=page_composer,
            settings=settings,
        )

    return _execute_rejection_primary_action(
        completion=completion,
        decision=decision,
        comment_identity=envelope.comment_identity,
        original_comment_text=envelope.original_comment_text,
        target_page=envelope.target_page,
    )


def _execute_update_primary_action(
    *,
    completion: RunnerCompletion,
    decision: UpdateDecision,
    target_page: str,
    current_page_content: str,
    invocation_as_of_date: str,
    fresh_verification_obtained: bool,
    degraded_web_research: bool,
    capability_result: CapabilityResult,
    page_composer: PageComposer,
    settings: RunnerSettings,
) -> CompletionResult | ConfirmedPrimaryAction:
    final_page_content = page_composer.compose_update(
        PageCompositionInput(
            current_page_content=current_page_content,
            model_page_content=decision.final_page_content,
            capability_result=capability_result,
            invocation_as_of_date=invocation_as_of_date,
            fresh_verification_obtained=fresh_verification_obtained,
            degraded_web_research=degraded_web_research,
        )
    ).final_page_content

    invalid_body_link = _invalid_body_link(
        current_page_content=current_page_content,
        final_page_content=final_page_content,
        web_research_outputs=tuple(
            artifact for artifact in capability_result.artifacts if isinstance(artifact, WebResearchOutput)
        ),
    )
    if invalid_body_link is not None:
        return CompletionResult(
            STATUS_UPDATE_FAILED,
            "UNSURFACED_BODY_LINK",
            f"updated page included a link not supported by current page content or surfaced web research: {invalid_body_link}",
        )

    if _utf8_len(final_page_content) > settings.max_output_bytes:
        return CompletionResult(STATUS_UPDATE_FAILED, "OUTPUT_TOO_LARGE", "model output exceeded byte limit")

    if final_page_content == current_page_content:
        return CompletionResult(
            STATUS_UPDATE_FAILED,
            "NO_CONTENT_CHANGE",
            "model output did not change the current page content",
        )

    return completion.complete_update_primary_action(
        target_page=target_page,
        final_page_content=final_page_content,
    )


def _execute_rejection_primary_action(
    *,
    completion: RunnerCompletion,
    decision: RejectDecision,
    comment_identity: str,
    original_comment_text: str,
    target_page: str,
) -> CompletionResult | ConfirmedPrimaryAction:
    replacement_comment = _build_rejection_comment(
        comment_identity=comment_identity,
        original_comment_text=original_comment_text,
        rejection_reason_code=decision.rejection_reason_code,
        explanation=decision.explanation,
    )
    return completion.complete_rejection_primary_action(
        target_page=target_page,
        replacement_comment=replacement_comment,
    )


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

    quoted_block = "\n".join(quoted_lines)

    return (
        f'<!-- wiki-agent:rejection source_comment_id="{comment_identity}" '
        f'reason_code="{rejection_reason_code}" -->\n\n'
        "Marvin could not process this request.\n\n"
        f"{quoted_block}\n\n"
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


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _read_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _read_positive_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _read_non_empty_string_env(name: str, default: str | None) -> str:
    raw = os.getenv(name)
    if raw is None:
        if default is None:
            raise ValueError(f"{name} must be a non-empty string")
        return default

    value = raw.strip()
    if not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _load_runner_openai_config_from_env():
    config_path_value = os.getenv("WIKI_AGENT_CONFIG_PATH")
    if not config_path_value:
        return None
    return load_runner_openai_config(Path(config_path_value))


def _load_runner_research_budget_config_from_env():
    config_path_value = os.getenv("WIKI_AGENT_CONFIG_PATH")
    if not config_path_value:
        return None
    return load_runner_research_budget_config(Path(config_path_value))


def _bounded_message(exc: Exception) -> str:
    return str(exc).strip()[:500] or exc.__class__.__name__


def _requires_web_research(*, prompt: str, original_comment_text: str) -> bool:
    combined = f"{prompt}\n{original_comment_text}"
    return WEB_RESEARCH_HINT_PATTERN.search(combined) is not None


def _requires_fresh_verification(*, prompt: str, original_comment_text: str) -> bool:
    combined = f"{prompt}\n{original_comment_text}"
    if FRESH_VERIFICATION_HINT_PATTERN.search(combined) is not None:
        return True
    return (
        CURRENT_STATE_TEMPORAL_HINT_PATTERN.search(combined) is not None
        and CURRENT_STATE_CLAIM_HINT_PATTERN.search(combined) is not None
    )


def _invocation_as_of_date() -> str:
    return datetime.now(UTC).date().isoformat()


def _system_instruction(settings: RunnerSettings, *, rendered_prompt: str | None = None) -> str:
    instruction = (
        DEFAULT_SYSTEM_INSTRUCTION
        + " "
        + f"Use at most {settings.max_search_actions} hosted web search actions and at most "
        + f"{settings.max_opened_links} opened surfaced links during this invocation."
    )
    if rendered_prompt is None:
        return instruction

    return instruction + "\n\nFull page-update context:\n" + rendered_prompt


def _transport_user_prompt(*, prompt: str, target_page: str) -> str:
    return f"Target page: {target_page}\nUser request:\n{prompt}"


def _research_budget_constraint_message() -> str:
    return (
        "Web research hit the per-invocation budget. "
        "This update reflects only the evidence gathered before the limit was reached."
    )


def _invalid_body_link(
    *,
    current_page_content: str,
    final_page_content: str,
    web_research_outputs: tuple[WebResearchOutput, ...],
) -> str | None:
    if not web_research_outputs:
        return None

    current_urls = set(HTTP_URL_PATTERN.findall(_body_without_references(current_page_content)))
    surfaced_urls = {output.url for output in web_research_outputs}

    for url in HTTP_URL_PATTERN.findall(_body_without_references(final_page_content)):
        normalized = url.rstrip(")].,;")
        if normalized in current_urls or normalized in surfaced_urls:
            continue
        return normalized

    return None


def _body_without_references(markdown: str) -> str:
    marker = "\n## References\n"
    index = markdown.find(marker)
    if index == -1:
        return markdown
    return markdown[:index]


if __name__ == "__main__":
    raise SystemExit(main())
