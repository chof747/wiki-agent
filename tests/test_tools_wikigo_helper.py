from __future__ import annotations

from tools import wikigo_helper


def test_tools_wrapper_delegates_to_src_helper(monkeypatch) -> None:
    captured: list[list[str] | None] = []

    def fake_main(argv: list[str] | None = None) -> int:
        captured.append(argv)
        return 7

    monkeypatch.setattr(wikigo_helper._impl, "main", fake_main)

    assert wikigo_helper.main(["comments-scan"]) == 7
    assert captured == [["comments-scan"]]
