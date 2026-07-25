from __future__ import annotations

from wiki_agent import runner


def test_load_prompt_template_reads_packaged_markdown_resource() -> None:
    template = runner._load_prompt_template()

    assert "Target page: {{TARGET_PAGE}}" in template
    assert "Original source comment:" in template
    assert "{{CURRENT_PAGE_CONTENT}}" in template
