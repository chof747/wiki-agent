from __future__ import annotations

import json
from typing import Any


class WikiGoAdapterError(ValueError):
    """Raised when Wiki-Go/helper payloads are missing or malformed."""


def parse_scan_helper_output(raw_output: str) -> list[object]:
    stripped = raw_output.strip()
    if not stripped:
        return []

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return _parse_ndjson(stripped)

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for field in ("comments", "matches"):
            records = payload.get(field)
            if isinstance(records, list):
                return records

    raise WikiGoAdapterError(
        "wikigo-comments-scan output must be a JSON array, object, or NDJSON stream"
    )


def normalize_scan_record(record: object) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise WikiGoAdapterError("wikigo-comments-scan output must contain objects")

    author = _resolve_author(record)
    source_metadata = {
        "source_system": "wiki-go",
        **_collect_source_metadata(record),
    }
    if author is not None:
        source_metadata["author"] = author

    return {
        "comment_identity": _require_string(
            record,
            "comment identity",
            ("comment_identity", "comment_id", "id"),
        ),
        "target_page": _require_string(
            record,
            "target page",
            ("target_page", "page_path", "page", "path"),
        ),
        "original_comment_text": _require_string(
            record,
            "comment text",
            ("body", "comment_text", "text"),
        ),
        "author": author,
        "source_metadata": source_metadata,
    }


def normalize_comments_payload(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return _normalize_comment_items(payload)

    if isinstance(payload, dict):
        raw_items = payload.get("comments", [])
        if not isinstance(raw_items, list):
            return []
        return _normalize_comment_items(raw_items)

    return []


def parse_helper_comments_output(raw_output: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise WikiGoAdapterError("wikigo-comments list emitted invalid JSON") from exc

    if not isinstance(payload, list):
        raise WikiGoAdapterError("wikigo-comments list must return a JSON array")

    return normalize_comments_payload(payload)


def extract_markdown(payload: bytes | str) -> str:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text

    if isinstance(parsed, dict):
        for key in ("markdown", "content"):
            value = parsed.get(key)
            if isinstance(value, str):
                return value

        document = parsed.get("document")
        if isinstance(document, dict):
            for key in ("markdown", "content"):
                value = document.get(key)
                if isinstance(value, str):
                    return value

    raise WikiGoAdapterError("GET page response is missing markdown content")


def parse_helper_page_output(raw_output: str) -> str:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise WikiGoAdapterError("wikigo-helper page get emitted invalid JSON") from exc

    if not isinstance(payload, dict):
        raise WikiGoAdapterError("wikigo-helper page get must return a JSON object")

    try:
        return extract_markdown(raw_output)
    except WikiGoAdapterError as exc:
        raise WikiGoAdapterError("wikigo-helper page get response is missing markdown content") from exc


def _parse_ndjson(raw_output: str) -> list[object]:
    records: list[object] = []
    for line in raw_output.splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise WikiGoAdapterError("wikigo-comments-scan emitted invalid JSON") from exc
    return records


def _normalize_comment_items(raw_items: list[object]) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        comment_id = item.get("id", item.get("ID"))
        text = item.get("text", item.get("Content"))
        if not isinstance(comment_id, int | str) or not isinstance(text, str):
            continue

        author = item.get("author", item.get("Author", ""))
        created_at = item.get("created_at", item.get("Timestamp"))
        comments.append(
            {
                "id": str(comment_id),
                "text": text.strip(),
                "author": str(author),
                "created_at": created_at,
            }
        )
    return comments


def _require_string(record: dict[str, Any], field_name: str, aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        value = record.get(alias)
        if isinstance(value, str) and value:
            return value
    raise WikiGoAdapterError(f"wikigo-comments-scan record is missing {field_name}")


def _resolve_author(record: dict[str, Any]) -> str | None:
    author = record.get("author")
    if isinstance(author, str) and author:
        return author
    if isinstance(author, dict):
        for key in ("name", "login", "username", "display_name"):
            value = author.get(key)
            if isinstance(value, str) and value:
                return value

    for alias in ("author_name", "username", "user"):
        value = record.get(alias)
        if isinstance(value, str) and value:
            return value

    return None


def _collect_source_metadata(record: dict[str, Any]) -> dict[str, Any]:
    excluded = {
        "author",
        "author_name",
        "body",
        "comment_id",
        "comment_identity",
        "comment_text",
        "id",
        "page",
        "page_path",
        "path",
        "target_page",
        "text",
        "user",
        "username",
    }
    return {key: value for key, value in record.items() if key not in excluded}
