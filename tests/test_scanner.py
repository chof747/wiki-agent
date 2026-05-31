from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from wiki_agent.config import load_config
from wiki_agent.scanner import Scanner, ScannerError, WikiGoCommentScanAdapter


def test_scanner_scan_filters_and_normalizes_eligible_comment_events() -> None:
    config = load_config(Path(__file__).parent / "fixtures" / "config.toml")
    scanner = Scanner(
        config,
        scan_adapter=FakeScanAdapter(
            [
                {
                    "page": "__tests__/scanner-dry-run/eligible",
                    "id": "c-1",
                    "text": "@marvin: tighten the intro",
                    "author": "alice",
                },
                {
                    "page": "__tests__/scanner-dry-run/self",
                    "id": "c-2",
                    "text": "@marvin self-authored",
                    "author": "marvin",
                },
                {
                    "page": "__tests__/scanner-dry-run/marker",
                    "id": "c-3",
                    "text": "@marvin wiki-agent: already handled",
                    "author": "alice",
                },
                {
                    "page": "__tests__/scanner-dry-run/non-matching",
                    "id": "c-4",
                    "text": "@other-bot leave this alone",
                    "author": "alice",
                },
            ]
        ),
    )

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


def test_wikigo_comment_scan_adapter_accepts_matches_summary_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper_output = """
    {
      "target_user": "marvin",
      "scanned_pages": 3,
      "matched_comments": 1,
      "matches": [
        {
          "page": "__tests__/scanner-dry-run/eligible",
          "id": "c-1",
          "text": "@marvin: tighten the intro",
          "author": "alice"
        }
      ]
    }
    """

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args[0], 0, stdout=helper_output, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert WikiGoCommentScanAdapter().scan_records() == [
        {
            "page": "__tests__/scanner-dry-run/eligible",
            "id": "c-1",
            "text": "@marvin: tighten the intro",
            "author": "alice",
        }
    ]


def test_wikigo_comment_scan_adapter_raises_on_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args[0], 0, stdout="not json", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ScannerError, match="invalid JSON"):
        WikiGoCommentScanAdapter().scan_records()


class FakeScanAdapter:
    def __init__(self, records: list[object]) -> None:
        self._records = records

    def scan_records(self) -> list[object]:
        return list(self._records)
