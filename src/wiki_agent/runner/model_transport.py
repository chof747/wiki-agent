from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from wiki_agent.runner.capabilities.web_research import (
    WebResearchBudget,
    WebResearchBudgetUsage,
    WebResearchOutput,
)


class ModelTransportError(RuntimeError):
    """Raised when model transport fails before payload validation."""


@dataclass(frozen=True)
class ModelTransportRequest:
    model: str
    system_instruction: str
    user_prompt: str
    response_format: dict[str, Any]
    tools: tuple[dict[str, Any], ...] = ()
    tool_choice: object | None = None
    research_budget: WebResearchBudget | None = None


@dataclass(frozen=True)
class ModelTransportResponse:
    output_text: str
    web_research_outputs: tuple[WebResearchOutput, ...] = ()
    web_research_budget_usage: WebResearchBudgetUsage = WebResearchBudgetUsage()


class ModelTransport(Protocol):
    def generate(self, request: ModelTransportRequest) -> ModelTransportResponse: ...


def build_openai_client(*, api_key: str, timeout: float) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=timeout)


@dataclass
class OpenAIResponsesTransport:
    api_key: str
    timeout_seconds: float
    client_factory: Callable[..., Any] = build_openai_client

    def generate(self, request: ModelTransportRequest) -> ModelTransportResponse:
        client = self.client_factory(api_key=self.api_key, timeout=self.timeout_seconds)
        payload: dict[str, Any] = {
            "model": request.model,
            "input": [
                {"role": "system", "content": request.system_instruction},
                {"role": "user", "content": request.user_prompt},
            ],
            "text": {"format": request.response_format},
        }
        if request.tools:
            payload["tools"] = list(request.tools)
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice

        response = client.responses.create(
            **payload,
        )

        status = getattr(response, "status", None)
        if status not in {None, "completed"}:
            raise ModelTransportError("model response did not complete successfully")

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text:
            raise ModelTransportError("model response did not include structured output text")

        _emit_web_search_debug_log(response)

        web_research_outputs, web_research_budget_usage = _extract_web_research_outputs(
            response,
            request.research_budget,
        )
        _emit_web_research_budget_log(web_research_budget_usage, request.research_budget)
        return ModelTransportResponse(
            output_text=output_text,
            web_research_outputs=web_research_outputs,
            web_research_budget_usage=web_research_budget_usage,
        )


def _emit_web_search_debug_log(response: Any) -> None:
    output_items = getattr(response, "output", ()) or ()
    web_search_items = [item for item in output_items if getattr(item, "type", None) == "web_search_call"]
    if not web_search_items:
        return

    actions = _web_search_action_records(web_search_items)
    if actions:
        print(
            json.dumps(
                {
                    "event": "runner.web_search_actions",
                    "actions": actions,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )

    payload = {
        "event": "runner.web_search_output",
        "web_search_output": [_json_safe(item) for item in web_search_items],
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)


def _emit_web_research_budget_log(
    usage: WebResearchBudgetUsage,
    budget: WebResearchBudget | None,
) -> None:
    payload = {
        "event": "runner.web_research_budget_usage",
        "search_actions_used": usage.search_actions_used,
        "opened_links_used": usage.opened_links_used,
        "materially_constrained": usage.materially_constrained,
    }
    if budget is not None:
        payload["max_search_actions"] = budget.max_search_actions
        payload["max_opened_links"] = budget.max_opened_links
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)


def _json_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except TypeError:
            return value.model_dump()

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: _json_safe(item) for key, item in vars(value).items()}
    return value


def _web_search_action_records(web_search_items: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, item in enumerate(web_search_items, start=1):
        item_payload = _json_safe(item)
        if not isinstance(item_payload, dict):
            continue

        action = item_payload.get("action")
        if not isinstance(action, dict):
            continue

        action_type = action.get("type")
        record: dict[str, Any] = {"index": index}
        if isinstance(action_type, str):
            record["type"] = action_type

        query = action.get("query")
        if isinstance(query, str) and query:
            record["query"] = query

        url = action.get("url")
        if isinstance(url, str) and url:
            record["url"] = url

        title = action.get("title")
        if isinstance(title, str) and title:
            record["title"] = title

        records.append(record)

    return records


def _extract_web_research_outputs(
    response: Any,
    research_budget: WebResearchBudget | None,
) -> tuple[tuple[WebResearchOutput, ...], WebResearchBudgetUsage]:
    outputs: list[WebResearchOutput] = []
    seen_urls: set[str] = set()
    allowed_urls: set[str] = set()
    search_actions_used = 0
    opened_links_used = 0
    materially_constrained = False
    skipped_budgeted_action = False

    def append_output(url: str, title: str) -> None:
        if url in seen_urls:
            return
        seen_urls.add(url)
        allowed_urls.add(url)
        outputs.append(WebResearchOutput(title=title, url=url))

    for item in getattr(response, "output", ()) or ():
        item_type = getattr(item, "type", None)
        item_payload = _json_safe(item)

        if item_type == "web_search_call":
            action_type = _web_search_action_type(item_payload)
            if action_type == "search":
                if research_budget is not None and search_actions_used >= research_budget.max_search_actions:
                    materially_constrained = True
                    skipped_budgeted_action = True
                    continue
                search_actions_used += 1
            elif action_type == "open_page":
                if research_budget is not None and opened_links_used >= research_budget.max_opened_links:
                    materially_constrained = True
                    skipped_budgeted_action = True
                    continue
                opened_links_used += 1

            for url, title in _extract_url_records(item_payload):
                append_output(url, title)
            continue

        for annotation in _extract_annotations(item_payload):
            url = annotation.get("url")
            if not isinstance(url, str) or not url:
                continue
            if research_budget is not None and url not in allowed_urls and (
                skipped_budgeted_action or search_actions_used == 0
            ):
                materially_constrained = True
                continue
            title = annotation.get("title")
            append_output(url, title if isinstance(title, str) and title else url)

    return tuple(outputs), WebResearchBudgetUsage(
        search_actions_used=search_actions_used,
        opened_links_used=opened_links_used,
        materially_constrained=materially_constrained,
    )


def _web_search_action_type(item_payload: Any) -> str | None:
    if not isinstance(item_payload, dict):
        return None

    action = item_payload.get("action")
    if not isinstance(action, dict):
        return None

    action_type = action.get("type")
    return action_type if isinstance(action_type, str) else None


def _extract_url_records(value: Any) -> tuple[tuple[str, str], ...]:
    records: list[tuple[str, str]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            url = node.get("url")
            if isinstance(url, str) and url:
                title = node.get("title")
                records.append((url, title if isinstance(title, str) and title else url))
            for child in node.values():
                visit(child)
            return

        if isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return tuple(records)


def _extract_annotations(value: Any) -> tuple[dict[str, Any], ...]:
    annotations: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key == "annotations" and isinstance(child, list):
                    annotations.extend(item for item in child if isinstance(item, dict))
                    continue
                visit(child)
            return

        if isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return tuple(annotations)


def parse_json_output(output_text: str) -> object:
    try:
        return json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise ModelTransportError("model output was not valid JSON") from exc
