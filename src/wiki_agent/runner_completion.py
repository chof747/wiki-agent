from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from wiki_agent.domain import (
    STATUS_DELETE_FAILED,
    STATUS_REJECTED_WITH_COMMENT,
    STATUS_SUCCESS,
    STATUS_UPDATE_FAILED,
)


@dataclass(frozen=True)
class CompletionResult:
    status: str
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class RunnerCompletion:
    read_page: Callable[[str], str]
    save_page: Callable[[str, str], None]
    create_comment: Callable[[str, str], None]
    list_comments: Callable[[str], list[dict[str, Any]]]
    delete_comment: Callable[[str, str], None]

    def complete_update(
        self,
        *,
        target_page: str,
        comment_identity: str,
        final_page_content: str,
    ) -> CompletionResult:
        try:
            self.save_page(target_page, final_page_content)
        except Exception as exc:
            return CompletionResult(STATUS_UPDATE_FAILED, "PAGE_SAVE_FAILED", str(exc))

        try:
            confirmed_markdown = self.read_page(target_page)
        except Exception as exc:
            return CompletionResult(STATUS_UPDATE_FAILED, "UPDATE_CONFIRMATION_FAILED", str(exc))

        if confirmed_markdown != final_page_content:
            return CompletionResult(
                STATUS_UPDATE_FAILED,
                "UPDATE_CONFIRMATION_FAILED",
                "saved page content did not match confirmation fetch",
            )

        return self._complete_after_visible_work(
            comment_identity=comment_identity,
            target_page=target_page,
            success_status=STATUS_SUCCESS,
        )

    def complete_rejection(
        self,
        *,
        target_page: str,
        comment_identity: str,
        replacement_comment: str,
    ) -> CompletionResult:
        try:
            self.create_comment(target_page, replacement_comment)
        except Exception as exc:
            return CompletionResult(STATUS_UPDATE_FAILED, "COMMENT_CREATE_FAILED", str(exc))

        try:
            replacement_comments = self.list_comments(target_page)
        except Exception as exc:
            return CompletionResult(STATUS_UPDATE_FAILED, "REPLACEMENT_CONFIRMATION_FAILED", str(exc))

        expected_replacement_comment = replacement_comment.strip()
        if not any(
            isinstance(comment.get("text"), str) and comment["text"].strip() == expected_replacement_comment
            for comment in replacement_comments
        ):
            return CompletionResult(
                STATUS_UPDATE_FAILED,
                "REPLACEMENT_CONFIRMATION_FAILED",
                "replacement comment was not present during confirmation",
            )

        return self._complete_after_visible_work(
            comment_identity=comment_identity,
            target_page=target_page,
            success_status=STATUS_REJECTED_WITH_COMMENT,
        )

    def _complete_after_visible_work(
        self,
        *,
        comment_identity: str,
        target_page: str,
        success_status: str,
    ) -> CompletionResult:
        try:
            self.delete_comment(comment_identity, target_page)
        except Exception as exc:
            return CompletionResult(STATUS_DELETE_FAILED, "COMMENT_DELETE_FAILED", str(exc))

        try:
            remaining_comments = self.list_comments(target_page)
        except Exception as exc:
            return CompletionResult(STATUS_DELETE_FAILED, "DELETE_CONFIRMATION_FAILED", str(exc))

        if any(comment.get("id") == comment_identity for comment in remaining_comments):
            return CompletionResult(
                STATUS_DELETE_FAILED,
                "DELETE_CONFIRMATION_FAILED",
                "source comment still present after delete confirmation",
            )

        return CompletionResult(success_status)
