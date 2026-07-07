from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from wiki_agent.runner.capabilities.web_research import WebResearchOutput


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


@dataclass(frozen=True)
class ModelTransportResponse:
    output_text: str
    web_research_outputs: tuple[WebResearchOutput, ...] = ()


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

        return ModelTransportResponse(
            output_text=output_text,
            web_research_outputs=_extract_web_research_outputs(response),
        )


def _emit_web_search_debug_log(response: Any) -> None:
    output_items = getattr(response, "output", ()) or ()
    web_search_items = [item for item in output_items if getattr(item, "type", None) == "web_search_call"]
    if not web_search_items:
        return

    payload = {
        "event": "runner.web_search_output",
        "web_search_output": [_json_safe(item) for item in web_search_items],
    }
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


def _extract_web_research_outputs(response: Any) -> tuple[WebResearchOutput, ...]:
    outputs: list[WebResearchOutput] = []
    seen_urls: set[str] = set()

    for item in getattr(response, "output", ()) or ():
        item_type = getattr(item, "type", None)
        item_payload = _json_safe(item)

        if item_type == "web_search_call":
            for url, title in _extract_url_records(item_payload):
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                outputs.append(WebResearchOutput(title=title, url=url))
            continue

        for annotation in _extract_annotations(item_payload):
            url = annotation.get("url")
            if not isinstance(url, str) or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = annotation.get("title")
            outputs.append(WebResearchOutput(title=title if isinstance(title, str) and title else url, url=url))

    return tuple(outputs)


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
