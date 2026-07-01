from __future__ import annotations

from dataclasses import dataclass, field

from wiki_agent import runner_completion


@dataclass
class FakeCompletionIO:
    comments: list[dict[str, str]] = field(default_factory=lambda: [{"id": "comment-1", "text": "source"}])
    saved_markdown: str | None = None
    confirmed_markdown: str = "# Updated\n"
    keep_comment_after_delete: bool = False
    suppress_created_comment: bool = False
    strip_created_comment_text: bool = False
    calls: list[str] = field(default_factory=list)

    def read_page(self, _target_page: str) -> str:
        self.calls.append("page.get")
        return self.confirmed_markdown

    def save_page(self, _target_page: str, markdown: str) -> None:
        self.calls.append("page.save")
        self.saved_markdown = markdown
        self.confirmed_markdown = markdown

    def create_comment(self, _target_page: str, content: str) -> None:
        self.calls.append("comments.create")
        if not self.suppress_created_comment:
            stored_text = content.strip() if self.strip_created_comment_text else content
            self.comments.append({"id": "comment-created-1", "text": stored_text})

    def list_comments(self, _target_page: str) -> list[dict[str, str]]:
        self.calls.append("comments.list")
        return list(self.comments)

    def delete_comment(self, comment_identity: str, _target_page: str) -> None:
        self.calls.append("comments.delete")
        if not self.keep_comment_after_delete:
            self.comments = [comment for comment in self.comments if comment.get("id") != comment_identity]


def _completion(io: FakeCompletionIO) -> runner_completion.RunnerCompletion:
    return runner_completion.RunnerCompletion(
        read_page=io.read_page,
        save_page=io.save_page,
        create_comment=io.create_comment,
        list_comments=io.list_comments,
        delete_comment=io.delete_comment,
    )


def test_complete_update_confirms_update_before_delete_and_returns_success() -> None:
    io = FakeCompletionIO(confirmed_markdown="# Current\n")

    result = _completion(io).complete_update(
        target_page="/pages/example",
        comment_identity="comment-1",
        final_page_content="# Updated\n",
    )

    assert result == runner_completion.CompletionResult(status="SUCCESS")
    assert io.calls == ["page.save", "page.get", "comments.delete", "comments.list"]
    assert io.saved_markdown == "# Updated\n"


def test_complete_rejection_confirms_replacement_before_delete_and_returns_rejected() -> None:
    io = FakeCompletionIO()
    replacement_comment = "replacement comment\n"

    result = _completion(io).complete_rejection(
        target_page="/pages/example",
        comment_identity="comment-1",
        replacement_comment=replacement_comment,
    )

    assert result == runner_completion.CompletionResult(status="REJECTED_WITH_COMMENT")
    assert io.calls == ["comments.create", "comments.list", "comments.delete", "comments.list"]


def test_complete_rejection_returns_update_failed_when_replacement_confirmation_fails() -> None:
    io = FakeCompletionIO(suppress_created_comment=True)

    result = _completion(io).complete_rejection(
        target_page="/pages/example",
        comment_identity="comment-1",
        replacement_comment="replacement comment\n",
    )

    assert result == runner_completion.CompletionResult(
        status="UPDATE_FAILED",
        error_code="REPLACEMENT_CONFIRMATION_FAILED",
        message="replacement comment was not present during confirmation",
    )
    assert io.calls == ["comments.create", "comments.list"]


def test_complete_update_returns_delete_failed_after_confirmed_visible_work() -> None:
    io = FakeCompletionIO(confirmed_markdown="# Current\n", keep_comment_after_delete=True)

    result = _completion(io).complete_update(
        target_page="/pages/example",
        comment_identity="comment-1",
        final_page_content="# Updated\n",
    )

    assert result == runner_completion.CompletionResult(
        status="DELETE_FAILED",
        error_code="DELETE_CONFIRMATION_FAILED",
        message="source comment still present after delete confirmation",
    )
    assert io.calls == ["page.save", "page.get", "comments.delete", "comments.list"]
