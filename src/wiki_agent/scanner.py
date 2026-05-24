from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, TextIO

from wiki_agent.config import AppConfig


LOGGER = logging.getLogger(__name__)


class ScannerError(RuntimeError):
    """Raised when the scanner helper boundary fails."""


@dataclass(frozen=True)
class EligibleCommentEvent:
    source_system: str
    comment_identity: str
    target_page: str
    author: str
    comment_body: str
    prompt: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source_system": self.source_system,
            "comment_identity": self.comment_identity,
            "target_page": self.target_page,
            "author": self.author,
            "comment_body": self.comment_body,
            "prompt": self.prompt,
        }


class Scanner:
    def __init__(
        self,
        config: AppConfig,
        *,
        command: tuple[str, ...] = ("wikigo-comments-scan",),
    ) -> None:
        self._config = config
        self._command = command

    def run_dry_run(self, stdout: TextIO | None = None) -> int:
        output = stdout if stdout is not None else sys.stdout
        payload = self._invoke_helper()
        eligible_events = [
            event.as_dict()
            for event in (
                self._normalize_match(match)
                for match in self._matches_from_payload(payload)
            )
            if event is not None
        ]

        summary = {
            "mode": "scanner_dry_run",
            "bot_name": self._config.bot_name,
            "scanned_pages": payload.get("scanned_pages", 0),
            "matched_comments": payload.get("matched_comments", 0),
            "eligible_comment_events": eligible_events,
        }
        json.dump(summary, output, sort_keys=True)
        output.write("\n")

        LOGGER.info(
            "Scanner dry-run completed.",
            extra={
                "event": "scanner.dry_run_completed",
                "scanned_pages": summary["scanned_pages"],
                "matched_comments": summary["matched_comments"],
                "eligible_comment_events": len(eligible_events),
            },
        )
        return 0

    def _invoke_helper(self) -> dict[str, Any]:
        result = subprocess.run(
            list(self._command),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ScannerError(
                f"wikigo-comments-scan exited with {result.returncode}: {result.stderr.strip()}"
            )

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ScannerError("wikigo-comments-scan emitted invalid JSON") from exc

        if not isinstance(payload, dict):
            raise ScannerError("wikigo-comments-scan emitted a non-object JSON payload")

        return payload

    def _matches_from_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        matches = payload.get("matches", [])
        if not isinstance(matches, list):
            raise ScannerError("wikigo-comments-scan payload field 'matches' must be a list")

        normalized: list[dict[str, Any]] = []
        for item in matches:
            if isinstance(item, dict):
                normalized.append(item)
        return normalized

    def _normalize_match(self, match: dict[str, Any]) -> EligibleCommentEvent | None:
        text = str(match.get("text", "")).strip()
        author = str(match.get("author", "")).strip()
        page = str(match.get("page", "")).strip()
        comment_id = str(match.get("id", "")).strip()
        if not text or not page or not comment_id:
            return None
        if "wiki-agent:" in text.lower():
            return None
        if author.casefold() == self._config.bot_name.casefold():
            return None

        prompt = self._strip_bot_mention(text)
        if prompt is None:
            return None

        return EligibleCommentEvent(
            source_system="wikigo",
            comment_identity=comment_id,
            target_page=page,
            author=author,
            comment_body=text,
            prompt=prompt,
        )

    def _strip_bot_mention(self, comment_text: str) -> str | None:
        escaped_bot_name = re.escape(self._config.bot_name)
        pattern = re.compile(rf"^@{escaped_bot_name}\b(?:[\s,:-]*)", re.IGNORECASE)
        if not pattern.match(comment_text):
            return None
        return pattern.sub("", comment_text, count=1).strip()
