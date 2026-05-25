from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from wiki_agent.config import AppConfig

if TYPE_CHECKING:
    from wiki_agent.comment_jobs import CommentJobRepository, EnqueueResult


class ScannerError(RuntimeError):
    """Raised when the scanner helper output is missing or malformed."""


@dataclass(frozen=True)
class CommentEvent:
    comment_identity: str
    target_page: str
    original_comment_text: str
    prompt: str
    source_metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "comment_identity": self.comment_identity,
            "target_page": self.target_page,
            "original_comment_text": self.original_comment_text,
            "prompt": self.prompt,
            "source_metadata": self.source_metadata,
        }


class Scanner:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._bot_mention = f"@{config.bot_name}"

    def dry_run(self) -> list[CommentEvent]:
        return self.scan()

    def scan(self) -> list[CommentEvent]:
        records = _parse_helper_output(_run_scan_helper())
        events: list[CommentEvent] = []
        for record in records:
            event = self._normalize_record(record)
            if event is not None:
                events.append(event)
        return events

    def enqueue(self, repository: "CommentJobRepository") -> list["EnqueueResult"]:
        results: list[EnqueueResult] = []
        for event in self.scan():
            results.append(repository.enqueue_event(event))
        return results

    def _normalize_record(self, record: object) -> CommentEvent | None:
        if not isinstance(record, dict):
            raise ScannerError("wikigo-comments-scan output must contain objects")

        original_comment_text = _require_string(record, "comment text", ("body", "comment_text", "text"))
        if not original_comment_text.startswith(self._bot_mention):
            return None
        if "wiki-agent:" in original_comment_text:
            return None

        author = _resolve_author(record)
        if author is not None and _is_bot_author(author, self._config.bot_name):
            return None

        comment_identity = _require_string(record, "comment identity", ("comment_identity", "comment_id", "id"))
        target_page = _require_string(record, "target page", ("target_page", "page_path", "page", "path"))

        source_metadata = {
            "source_system": "wiki-go",
            **_collect_source_metadata(record),
        }
        if author is not None:
            source_metadata["author"] = author

        return CommentEvent(
            comment_identity=comment_identity,
            target_page=target_page,
            original_comment_text=original_comment_text,
            prompt=original_comment_text[len(self._bot_mention) :].lstrip(),
            source_metadata=source_metadata,
        )


def _run_scan_helper() -> str:
    result = subprocess.run(
        ["wikigo-comments-scan"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ScannerError(
            "wikigo-comments-scan exited with "
            f"{result.returncode}: {result.stderr.strip() or 'no stderr'}"
        )
    return result.stdout


def _parse_helper_output(raw_output: str) -> list[object]:
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

    raise ScannerError("wikigo-comments-scan output must be a JSON array, object, or NDJSON stream")


def _parse_ndjson(raw_output: str) -> list[object]:
    records: list[object] = []
    for line in raw_output.splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ScannerError("wikigo-comments-scan emitted invalid JSON") from exc
    return records


def _require_string(record: dict[str, Any], field_name: str, aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        value = record.get(alias)
        if isinstance(value, str) and value:
            return value
    raise ScannerError(f"wikigo-comments-scan record is missing {field_name}")


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


def _is_bot_author(author: str, bot_name: str) -> bool:
    return author.lstrip("@").casefold() == bot_name.casefold()


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
