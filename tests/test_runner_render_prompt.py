from __future__ import annotations

from wiki_agent import runner


def test_render_prompt_preserves_literal_placeholder_text_inside_values() -> None:
    template = (
        "Target={{TARGET_PAGE}}\n"
        "Prompt={{PROMPT}}\n"
        "Comment={{ORIGINAL_COMMENT_TEXT}}\n"
        "Content={{CURRENT_PAGE_CONTENT}}\n"
    )

    rendered = runner.render_prompt(
        template=template,
        prompt="Keep the literal token {{CURRENT_PAGE_CONTENT}} in the page.",
        original_comment_text="@marvin note {{TARGET_PAGE}} literally",
        target_page="/pages/example",
        current_page_content="Current content also mentions {{PROMPT}} literally.\n",
    )

    assert rendered == (
        "Target=/pages/example\n"
        "Prompt=Keep the literal token {{CURRENT_PAGE_CONTENT}} in the page.\n"
        "Comment=@marvin note {{TARGET_PAGE}} literally\n"
        "Content=Current content also mentions {{PROMPT}} literally.\n\n"
    )
