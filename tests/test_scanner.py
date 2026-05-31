from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from wiki_agent.config import load_config
from wiki_agent.scanner import Scanner, ScannerError


def test_scanner_scan_accepts_matches_summary_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config(Path(__file__).parent / "fixtures" / "config.toml")
    scanner = Scanner(config)

    helper_output = """
    {
      "target_user": "marvin",
      "scanned_pages": 3,
      "matched_comments": 4,
      "matches": [
        {
          "page": "__tests__/scanner-dry-run/eligible",
          "id": "c-1",
          "text": "@marvin: tighten the intro",
          "author": "alice"
        },
        {
          "page": "__tests__/scanner-dry-run/self",
          "id": "c-2",
          "text": "@marvin self-authored",
          "author": "marvin"
        },
        {
          "page": "__tests__/scanner-dry-run/marker",
          "id": "c-3",
          "text": "@marvin wiki-agent: already handled",
          "author": "alice"
        },
        {
          "page": "__tests__/scanner-dry-run/non-matching",
          "id": "c-4",
          "text": "@other-bot leave this alone",
          "author": "alice"
        }
      ]
    }
    """

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args[0], 0, stdout=helper_output, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    events = scanner.scan()

    assert [event.as_dict() for event in events] == [
        {
            "comment_identity": "c-1",
            "target_page": "__tests__/scanner-dry-run/eligible",
            "original_comment_text": "@marvin: tighten the intro",
            "prompt": ": tighten the intro",
            "source_metadata": {
                "author": "alice",
                "source_system": "wiki-go",
            },
        }
    ]


def test_scanner_scan_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config(Path(__file__).parent / "fixtures" / "config.toml")
    scanner = Scanner(config)

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args[0], 0, stdout="not json", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ScannerError, match="invalid JSON"):
        scanner.scan()
