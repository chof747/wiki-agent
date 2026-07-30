from __future__ import annotations

from wiki_agent import runner


def test_load_context_template_reads_packaged_markdown_resource() -> None:
    template = runner._load_context_template()

    assert "Target page: {{TARGET_PAGE}}" in template
    assert "Stripped prompt:" in template
    assert "{{CURRENT_PAGE_CONTENT}}" in template
    assert "{{PROMPT}}" in template


def test_load_system_template_reads_packaged_markdown_resource() -> None:
    template = runner._load_system_template()

    assert "Write concise search queries tailored to the stripped prompt and target topic" in template
    assert "Return only structured JSON matching the provided schema." in template
    assert "{{TARGET_PAGE}}" not in template
