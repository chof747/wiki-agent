from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Protocol

from wiki_agent.config import AppConfig
from wiki_agent.wikigo_adapter import WikiGoAdapterError, normalize_scan_record, parse_scan_helper_output


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


class CommentScanAdapter(Protocol):
    def scan_records(self) -> list[object]: ...


class WikiGoCommentScanAdapter(CommentScanAdapter):
    def scan_records(self) -> list[object]:
        try:
            return parse_scan_helper_output(_run_scan_helper())
        except WikiGoAdapterError as exc:
            raise ScannerError(str(exc)) from exc


class Scanner:
    def __init__(
        self,
        config: AppConfig,
        *,
        scan_adapter: CommentScanAdapter | None = None,
    ) -> None:
        self._config = config
        self._bot_mention = f"@{config.bot_name}"
        self._scan_adapter = scan_adapter or WikiGoCommentScanAdapter()

    def scan(self) -> list[CommentEvent]:
        records = self._scan_adapter.scan_records()
        events: list[CommentEvent] = []
        for record in records:
            event = self._normalize_record(record)
            if event is not None:
                events.append(event)
        return events

    def _normalize_record(self, record: object) -> CommentEvent | None:
        try:
            normalized = normalize_scan_record(record)
        except WikiGoAdapterError as exc:
            raise ScannerError(str(exc)) from exc

        original_comment_text = normalized["original_comment_text"]
        if not original_comment_text.startswith(self._bot_mention):
            return None
        if "wiki-agent:" in original_comment_text:
            return None

        author = normalized["author"]
        if author is not None and _is_bot_author(author, self._config.bot_name):
            return None

        return CommentEvent(
            comment_identity=normalized["comment_identity"],
            target_page=normalized["target_page"],
            original_comment_text=original_comment_text,
            prompt=original_comment_text[len(self._bot_mention) :].lstrip(),
            source_metadata=normalized["source_metadata"],
        )


def _run_scan_helper() -> str:
    try:
        result = subprocess.run(
            ["wikigo-comments-scan"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ScannerError("wikigo-comments-scan executable was not found") from exc
    if result.returncode != 0:
        raise ScannerError(
            "wikigo-comments-scan exited with "
            f"{result.returncode}: {result.stderr.strip() or 'no stderr'}"
        )
    return result.stdout
def _is_bot_author(author: str, bot_name: str) -> bool:
    return author.lstrip("@").casefold() == bot_name.casefold()
