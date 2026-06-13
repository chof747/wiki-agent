from __future__ import annotations

import json
from pathlib import Path

import pytest

from wiki_agent import wikigo_helper


def test_page_get_reads_source_endpoint_and_emits_markdown(monkeypatch, capsys) -> None:
    recorded: list[tuple[str, str]] = []

    class FakeSession:
        def __init__(self, *, base_url: str, username: str, password: str) -> None:
            assert base_url == "http://example.test"
            assert username == "admin"
            assert password == "secret"

        def request(
            self,
            method: str,
            endpoint: str,
            *,
            body: bytes | None = None,
            content_type: str | None = None,
        ) -> bytes:
            del body, content_type
            recorded.append((method, endpoint))
            if endpoint == "/api/source/team/roadmap":
                return b"# Team Roadmap\n"
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(
        wikigo_helper,
        "load_runtime_config",
        lambda: {
            "base_url": "http://example.test",
            "username": "admin",
            "password": "secret",
        },
    )
    monkeypatch.setattr(wikigo_helper, "WikiGoSession", FakeSession)

    exit_code = wikigo_helper.main(["page", "get", "team/roadmap"])

    assert exit_code == 0
    assert recorded == [("GET", "/api/source/team/roadmap")]
    assert capsys.readouterr().out == json.dumps({"markdown": "# Team Roadmap\n"}) + "\n"


def test_extract_markdown_accepts_plain_text_source() -> None:
    assert wikigo_helper.extract_markdown(b"# Title\n\nBody\n") == "# Title\n\nBody\n"


def test_comments_list_uses_supported_endpoint(monkeypatch, capsys) -> None:
    recorded: list[tuple[str, str]] = []

    class FakeSession:
        def __init__(self, *, base_url: str, username: str, password: str) -> None:
            del base_url, username, password

        def request(
            self,
            method: str,
            endpoint: str,
            *,
            body: bytes | None = None,
            content_type: str | None = None,
        ) -> bytes:
            del body, content_type
            recorded.append((method, endpoint))
            if endpoint == "/api/comments/team/roadmap":
                return json.dumps(
                    {
                        "comments": [
                            {
                                "ID": "comment-1",
                                "Content": "@marvin tighten intro",
                                "Author": "alice",
                                "Timestamp": "2026-05-27T06:00:00Z",
                            }
                        ]
                    }
                ).encode("utf-8")
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(
        wikigo_helper,
        "load_runtime_config",
        lambda: {
            "base_url": "http://example.test",
            "username": "marvin",
            "password": "secret",
        },
    )
    monkeypatch.setattr(wikigo_helper, "WikiGoSession", FakeSession)

    exit_code = wikigo_helper.main(["comments", "list", "team/roadmap", "--mention-only"])

    assert exit_code == 0
    assert recorded == [("GET", "/api/comments/team/roadmap")]
    assert json.loads(capsys.readouterr().out) == [
        {
            "id": "comment-1",
            "text": "@marvin tighten intro",
            "author": "alice",
            "created_at": "2026-05-27T06:00:00Z",
        }
    ]


def test_comments_delete_uses_supported_endpoint(monkeypatch, capsys) -> None:
    recorded: list[tuple[str, str, bytes | None, str | None]] = []

    class FakeSession:
        def __init__(self, *, base_url: str, username: str, password: str) -> None:
            del base_url, username, password

        def request(
            self,
            method: str,
            endpoint: str,
            *,
            body: bytes | None = None,
            content_type: str | None = None,
        ) -> bytes:
            recorded.append((method, endpoint, body, content_type))
            if endpoint == "/api/comments/delete/team/roadmap/comment-1":
                return b""
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(
        wikigo_helper,
        "load_runtime_config",
        lambda: {
            "base_url": "http://example.test",
            "username": "marvin",
            "password": "secret",
        },
    )
    monkeypatch.setattr(wikigo_helper, "WikiGoSession", FakeSession)

    exit_code = wikigo_helper.main(["comments", "delete", "comment-1", "team/roadmap"])

    assert exit_code == 0
    assert capsys.readouterr().out == "deleted comment: comment-1\n"
    assert [item[:2] for item in recorded] == [("DELETE", "/api/comments/delete/team/roadmap/comment-1")]


def test_comments_create_uses_supported_endpoint(tmp_path, monkeypatch, capsys) -> None:
    recorded: list[tuple[str, str, dict[str, object]]] = []
    content_path = tmp_path / "comment.md"
    content_path.write_text("Visible rejection comment", encoding="utf-8")

    class FakeSession:
        def __init__(self, *, base_url: str, username: str, password: str) -> None:
            del base_url, username, password

        def post_json(self, endpoint: str, payload: dict[str, object]) -> dict[str, object]:
            recorded.append(("POST", endpoint, payload))
            if endpoint == "/api/comments/add/team/roadmap":
                assert payload == {"content": "Visible rejection comment"}
                return {"id": "comment-2", "content": "Visible rejection comment"}
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(
        wikigo_helper,
        "load_runtime_config",
        lambda: {
            "base_url": "http://example.test",
            "username": "marvin",
            "password": "secret",
        },
    )
    monkeypatch.setattr(wikigo_helper, "WikiGoSession", FakeSession)

    exit_code = wikigo_helper.main(["comments", "create", "team/roadmap", str(content_path)])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": "comment-2",
        "content": "Visible rejection comment",
    }
    assert [item[:2] for item in recorded] == [("POST", "/api/comments/add/team/roadmap")]


def test_comments_create_preserves_http_failure_details(tmp_path, monkeypatch) -> None:
    recorded: list[tuple[str, str, dict[str, object]]] = []
    content_path = tmp_path / "comment.md"
    content_path.write_text("Visible rejection comment", encoding="utf-8")

    class FakeSession:
        def __init__(self, *, base_url: str, username: str, password: str) -> None:
            del base_url, username, password

        def post_json(self, endpoint: str, payload: dict[str, object]) -> dict[str, object]:
            recorded.append(("POST", endpoint, payload))
            if endpoint == "/api/comments/add/team/roadmap":
                raise SystemExit(
                    "POST /api/comments/add/team/roadmap failed with HTTP 500: exploded"
                )
            raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(
        wikigo_helper,
        "load_runtime_config",
        lambda: {
            "base_url": "http://example.test",
            "username": "marvin",
            "password": "secret",
        },
    )
    monkeypatch.setattr(wikigo_helper, "WikiGoSession", FakeSession)

    with pytest.raises(
        SystemExit,
        match=r"POST /api/comments/add/team/roadmap failed with HTTP 500: exploded",
    ):
        wikigo_helper.main(["comments", "create", "team/roadmap", str(content_path)])

    assert [item[:2] for item in recorded] == [("POST", "/api/comments/add/team/roadmap")]


def test_load_runtime_config_reads_wikigo_section_from_app_config(monkeypatch) -> None:
    config_path = Path(__file__).parent / "fixtures" / "config.toml"
    monkeypatch.delenv("WIKIGO_RUNTIME_CONFIG", raising=False)
    monkeypatch.setenv("WIKI_AGENT_CONFIG_PATH", str(config_path))

    config = wikigo_helper.load_runtime_config()

    assert config == {
        "base_url": "http://127.0.0.1:4010",
        "username": "marvin",
        "password": "marvin-pass",
        "config_file": str(config_path),
    }
