from __future__ import annotations

import pytest

from wiki_agent.wikigo_adapter import (
    WikiGoAdapterError,
    extract_markdown,
    normalize_comments_payload,
    normalize_scan_record,
    parse_helper_comments_output,
    parse_helper_page_output,
)


def test_normalize_scan_record_accepts_helper_aliases() -> None:
    normalized = normalize_scan_record(
        {
            "comment_id": "comment-1",
            "page_path": "/pages/example",
            "body": "@marvin tighten this page",
            "author": {"login": "alice"},
            "comment_url": "https://example.test/comments/1",
        }
    )

    assert normalized == {
        "comment_identity": "comment-1",
        "target_page": "/pages/example",
        "original_comment_text": "@marvin tighten this page",
        "author": "alice",
        "source_metadata": {
            "source_system": "wiki-go",
            "author": "alice",
            "comment_url": "https://example.test/comments/1",
        },
    }


def test_normalize_comments_payload_accepts_api_shape() -> None:
    comments = normalize_comments_payload(
        {
            "comments": [
                {
                    "ID": 7,
                    "Content": " hello ",
                    "Author": "alice",
                    "Timestamp": "2026-05-27T06:00:00Z",
                }
            ]
        }
    )

    assert comments == [
        {
            "id": "7",
            "text": "hello",
            "author": "alice",
            "created_at": "2026-05-27T06:00:00Z",
        }
    ]


def test_parse_helper_comments_output_requires_json_array() -> None:
    with pytest.raises(WikiGoAdapterError, match="must return a JSON array"):
        parse_helper_comments_output('{"comments": []}')


def test_parse_helper_page_output_accepts_canonical_helper_shape() -> None:
    assert parse_helper_page_output('{"markdown": "# Title\\n"}') == "# Title\n"


def test_extract_markdown_accepts_nested_document_content() -> None:
    assert extract_markdown(b'{"document": {"content": "# Title\\n"}}') == "# Title\n"
