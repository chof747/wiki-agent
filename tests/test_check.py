from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from wiki_agent.check import run_installation_shakedown
from wiki_agent.config import load_config


def test_installation_shakedown_reports_success_with_non_openai_runner_probe() -> None:
    config = load_config(_fixture_config_path())
    calls: list[tuple[str, tuple[str, ...], str | None]] = []

    class FakeRepository:
        def __init__(self, dsn: str) -> None:
            calls.append(("repository", (dsn,), None))

        def ensure_schema(self) -> None:
            calls.append(("repository.ensure_schema", (), None))

    def fake_run(
        argv: list[str],
        *,
        input: str | None = None,
        capture_output: bool,
        text: bool,
        check: bool,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output is True
        assert text is True
        assert check is False
        if argv == ["wikigo-comments-scan"]:
            calls.append(("scan", tuple(argv), input))
            return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")
        if argv == ["wiki-agent-runner"]:
            calls.append(("runner", tuple(argv), input))
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        "status": "UPDATE_FAILED",
                        "error_code": "PROMPT_ENVELOPE_INVALID",
                        "message": "stdin must contain one JSON prompt envelope",
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected argv: {argv}")

    stdout = io.StringIO()

    assert (
        run_installation_shakedown(
            config,
            config_path=_fixture_config_path(),
            stdout=stdout,
            repository_factory=FakeRepository,
            subprocess_run=fake_run,
        )
        == 0
    )

    payload = json.loads(stdout.getvalue())
    assert payload == {
        "checks": [
            {
                "message": f"loaded configuration from {_fixture_config_path()}",
                "name": "config",
                "status": "ok",
            },
            {
                "message": "connected and ensured comment_jobs schema readiness",
                "name": "postgres",
                "status": "ok",
            },
            {
                "message": "wikigo-comments-scan executed and returned parseable output",
                "name": "wikigo_comments_scan",
                "status": "ok",
            },
            {
                "message": "runner finalized an invalid-envelope smoke invocation with UPDATE_FAILED without reaching the model",
                "name": "runner",
                "status": "ok",
            },
        ],
        "ok": True,
    }
    assert calls == [
        ("repository", (config.postgres.dsn,), None),
        ("repository.ensure_schema", (), None),
        ("scan", ("wikigo-comments-scan",), None),
        ("runner", ("wiki-agent-runner",), "{}"),
    ]


def test_installation_shakedown_reports_actionable_runner_failure() -> None:
    config = load_config(_fixture_config_path())

    class FakeRepository:
        def __init__(self, _dsn: str) -> None:
            return None

        def ensure_schema(self) -> None:
            return None

    def fake_run(
        argv: list[str],
        *,
        input: str | None = None,
        capture_output: bool,
        text: bool,
        check: bool,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del input, capture_output, text, check, timeout
        if argv == ["wikigo-comments-scan"]:
            return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")
        if argv == ["wiki-agent-runner"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps({"status": "SUCCESS"}),
                stderr="",
            )
        raise AssertionError(f"unexpected argv: {argv}")

    stdout = io.StringIO()

    assert (
        run_installation_shakedown(
            config,
            config_path=_fixture_config_path(),
            stdout=stdout,
            repository_factory=FakeRepository,
            subprocess_run=fake_run,
        )
        == 1
    )

    payload = json.loads(stdout.getvalue())
    assert payload["ok"] is False
    assert payload["checks"][-1] == {
        "message": "runner smoke invocation must finalize with UPDATE_FAILED for an invalid prompt envelope",
        "name": "runner",
        "status": "failed",
    }


def _fixture_config_path() -> Path:
    return Path(__file__).parent / "fixtures" / "config.toml"
