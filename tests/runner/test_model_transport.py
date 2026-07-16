from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from wiki_agent.runner.model_transport import (
    ModelTransportError,
    ModelTransportRequest,
    OpenAIResponsesTransport,
    parse_json_output,
)
from wiki_agent.runner.capabilities.web_research import WebResearchBudget


def test_openai_responses_transport_builds_one_structured_request() -> None:
    seen: dict[str, object] = {}

    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(status="completed", output_text=json.dumps({"action": "update"}))

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **kwargs: seen.update(kwargs) or FakeClient(),
    )

    response = transport.generate(
        ModelTransportRequest(
            model="gpt-test",
            system_instruction="system instruction",
            user_prompt="user prompt",
            response_format={"type": "json_schema"},
            tools=({"type": "web_search"},),
            tool_choice="required",
        )
    )

    assert response.output_text == '{"action": "update"}'
    assert seen == {
        "api_key": "test-key",
        "timeout": 12.5,
        "model": "gpt-test",
        "input": [
            {"role": "system", "content": "system instruction"},
            {"role": "user", "content": "user prompt"},
        ],
        "text": {"format": {"type": "json_schema"}},
        "tools": [{"type": "web_search"}],
        "tool_choice": "required",
    }


def test_openai_responses_transport_extracts_surfaced_web_search_urls() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **_kwargs):
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"action": "update"}),
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            type="search",
                            sources=[
                                SimpleNamespace(type="url", url="https://example.com/1"),
                                SimpleNamespace(type="url", url="https://example.com/1"),
                                SimpleNamespace(type="url", url="https://example.com/2"),
                            ],
                        ),
                    )
                ],
            )

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    response = transport.generate(
        ModelTransportRequest(
            model="gpt-test",
            system_instruction="system instruction",
            user_prompt="user prompt",
            response_format={"type": "json_schema"},
        )
    )

    assert [item.url for item in response.web_research_outputs] == [
        "https://example.com/1",
        "https://example.com/2",
    ]


def test_openai_responses_transport_extracts_opened_and_cited_web_urls() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **_kwargs):
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"action": "update"}),
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            type="search",
                            queries=["latest wiki agent release"],
                        ),
                    ),
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            type="open_page",
                            url="https://example.com/opened",
                            title="Opened Source",
                        ),
                    ),
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(
                                type="output_text",
                                text="Used sources",
                                annotations=[
                                    SimpleNamespace(
                                        type="url_citation",
                                        title="Cited Source",
                                        url="https://example.com/cited",
                                    ),
                                    SimpleNamespace(
                                        type="url_citation",
                                        title="Opened Source",
                                        url="https://example.com/opened",
                                    ),
                                ],
                            )
                        ],
                    ),
                ],
            )

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    response = transport.generate(
        ModelTransportRequest(
            model="gpt-test",
            system_instruction="system instruction",
            user_prompt="user prompt",
            response_format={"type": "json_schema"},
        )
    )

    assert [(item.title, item.url) for item in response.web_research_outputs] == [
        ("Opened Source", "https://example.com/opened"),
        ("Cited Source", "https://example.com/cited"),
    ]


def test_openai_responses_transport_extracts_cited_urls_when_search_call_has_no_url_records() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **_kwargs):
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"action": "update"}),
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(type="search", query="latest postgresql release"),
                        status="completed",
                    ),
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(
                                type="output_text",
                                text="PostgreSQL 17.5 was released.",
                                annotations=[
                                    SimpleNamespace(
                                        type="url_citation",
                                        title="PostgreSQL: Release notes",
                                        url="https://www.postgresql.org/docs/release/17.5/",
                                    )
                                ],
                            )
                        ],
                    ),
                ],
            )

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    response = transport.generate(
        ModelTransportRequest(
            model="gpt-test",
            system_instruction="system instruction",
            user_prompt="user prompt",
            response_format={"type": "json_schema"},
            research_budget=WebResearchBudget(max_search_actions=3, max_opened_links=3),
        )
    )

    assert [(item.title, item.url) for item in response.web_research_outputs] == [
        ("PostgreSQL: Release notes", "https://www.postgresql.org/docs/release/17.5/")
    ]
    assert response.web_research_budget_usage.search_actions_used == 1
    assert response.web_research_budget_usage.opened_links_used == 0
    assert response.web_research_budget_usage.materially_constrained is False


def test_openai_responses_transport_logs_raw_web_search_output(capsys: pytest.CaptureFixture[str]) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **_kwargs):
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"action": "update"}),
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            type="search",
                            query="bambu lab 3d printer models reddit summary",
                            sources=[SimpleNamespace(type="url", url="https://example.com/1")],
                        ),
                        status="completed",
                    )
                ],
            )

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    transport.generate(
        ModelTransportRequest(
            model="gpt-test",
            system_instruction="system instruction",
            user_prompt="user prompt",
            response_format={"type": "json_schema"},
        )
    )

    stderr_lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert len(stderr_lines) == 3
    assert json.loads(stderr_lines[0]) == {
        "actions": [
            {
                "index": 1,
                "query": "bambu lab 3d printer models reddit summary",
                "type": "search",
            }
        ],
        "event": "runner.web_search_actions",
    }
    assert json.loads(stderr_lines[1]) == {
        "event": "runner.web_search_output",
        "web_search_output": [
            {
                "action": {
                    "query": "bambu lab 3d printer models reddit summary",
                    "sources": [{"type": "url", "url": "https://example.com/1"}],
                    "type": "search",
                },
                "status": "completed",
                "type": "web_search_call",
            }
        ],
    }
    assert json.loads(stderr_lines[2]) == {
        "event": "runner.web_research_budget_usage",
        "materially_constrained": False,
        "opened_links_used": 0,
        "search_actions_used": 1,
    }


def test_openai_responses_transport_stops_collecting_web_research_after_budget_exhaustion() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **_kwargs):
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"action": "update"}),
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            type="search",
                            sources=[
                                SimpleNamespace(type="url", url="https://example.com/1"),
                                SimpleNamespace(type="url", url="https://example.com/2"),
                            ],
                        ),
                    ),
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            type="open_page",
                            url="https://example.com/2",
                            title="Opened Source",
                        ),
                    ),
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            type="search",
                            sources=[SimpleNamespace(type="url", url="https://example.com/3")],
                        ),
                    ),
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(
                                type="output_text",
                                text="Used sources",
                                annotations=[
                                    SimpleNamespace(
                                        type="url_citation",
                                        title="Opened Source",
                                        url="https://example.com/2",
                                    ),
                                    SimpleNamespace(
                                        type="url_citation",
                                        title="Over Budget Source",
                                        url="https://example.com/3",
                                    ),
                                ],
                            )
                        ],
                    ),
                ],
            )

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    response = transport.generate(
        ModelTransportRequest(
            model="gpt-test",
            system_instruction="system instruction",
            user_prompt="user prompt",
            response_format={"type": "json_schema"},
            research_budget=WebResearchBudget(max_search_actions=1, max_opened_links=1),
        )
    )

    assert [(item.title, item.url) for item in response.web_research_outputs] == [
        ("https://example.com/1", "https://example.com/1"),
        ("https://example.com/2", "https://example.com/2"),
    ]
    assert response.web_research_budget_usage.search_actions_used == 1
    assert response.web_research_budget_usage.opened_links_used == 1
    assert response.web_research_budget_usage.materially_constrained is True


def test_openai_responses_transport_logs_budget_usage_counts(capsys: pytest.CaptureFixture[str]) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **_kwargs):
            return SimpleNamespace(
                status="completed",
                output_text=json.dumps({"action": "update"}),
                output=[
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            type="search",
                            sources=[SimpleNamespace(type="url", url="https://example.com/1")],
                        ),
                    ),
                    SimpleNamespace(
                        type="web_search_call",
                        action=SimpleNamespace(
                            type="open_page",
                            url="https://example.com/1",
                            title="Opened Source",
                        ),
                    ),
                ],
            )

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    transport.generate(
        ModelTransportRequest(
            model="gpt-test",
            system_instruction="system instruction",
            user_prompt="user prompt",
            response_format={"type": "json_schema"},
            research_budget=WebResearchBudget(max_search_actions=1, max_opened_links=1),
        )
    )

    stderr_lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert json.loads(stderr_lines[2]) == {
        "event": "runner.web_research_budget_usage",
        "materially_constrained": False,
        "max_opened_links": 1,
        "max_search_actions": 1,
        "opened_links_used": 1,
        "search_actions_used": 1,
    }


def test_openai_responses_transport_rejects_incomplete_status() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.responses = self

        def create(self, **_kwargs):
            return SimpleNamespace(status="incomplete", output_text="{}")

    transport = OpenAIResponsesTransport(
        api_key="test-key",
        timeout_seconds=12.5,
        client_factory=lambda **_kwargs: FakeClient(),
    )

    with pytest.raises(ModelTransportError, match="did not complete successfully"):
        transport.generate(
            ModelTransportRequest(
                model="gpt-test",
                system_instruction="system instruction",
                user_prompt="user prompt",
                response_format={"type": "json_schema"},
            )
        )


def test_parse_json_output_rejects_invalid_json() -> None:
    with pytest.raises(ModelTransportError, match="not valid JSON"):
        parse_json_output("{not json}")
