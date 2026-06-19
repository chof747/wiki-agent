from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from wiki_agent.comment_jobs import CommentJobRepository
from wiki_agent.config import AppConfig
from wiki_agent.domain import STATUS_UPDATE_FAILED
from wiki_agent.runner_client import RunnerInvocationError, parse_runner_response
from wiki_agent.scanner import ScannerError, parse_scan_helper_output


RUNNER_SMOKE_ENVELOPE = "{}"
RUNNER_SMOKE_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "message": self.message}


def run_installation_shakedown(
    config: AppConfig,
    *,
    config_path: Path,
    stdout: TextIO = sys.stdout,
    repository_factory: type[CommentJobRepository] = CommentJobRepository,
    subprocess_run: Any = subprocess.run,
) -> int:
    results = [
        CheckResult(
            name="config",
            status="ok",
            message=f"loaded configuration from {config_path}",
        )
    ]

    results.append(_check_postgres(config, repository_factory=repository_factory))
    results.append(_check_wikigo_comments_scan(subprocess_run=subprocess_run))
    results.append(_check_runner(config, subprocess_run=subprocess_run))

    payload = {
        "ok": all(result.status == "ok" for result in results),
        "checks": [result.as_dict() for result in results],
    }
    json.dump(payload, stdout, sort_keys=True)
    stdout.write("\n")
    return 0 if payload["ok"] else 1


def _check_postgres(
    config: AppConfig,
    *,
    repository_factory: type[CommentJobRepository],
) -> CheckResult:
    try:
        repository = repository_factory(config.postgres.dsn)
        repository.ensure_schema()
    except Exception as exc:
        return CheckResult(
            name="postgres",
            status="failed",
            message=f"postgres readiness check failed: {exc}",
        )

    return CheckResult(
        name="postgres",
        status="ok",
        message="connected and ensured comment_jobs schema readiness",
    )


def _check_wikigo_comments_scan(*, subprocess_run: Any) -> CheckResult:
    try:
        result = subprocess_run(
            ["wikigo-comments-scan"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return CheckResult(
            name="wikigo_comments_scan",
            status="failed",
            message="wikigo-comments-scan executable was not found",
        )

    if result.returncode != 0:
        return CheckResult(
            name="wikigo_comments_scan",
            status="failed",
            message=(
                "wikigo-comments-scan exited with "
                f"{result.returncode}: {result.stderr.strip() or 'no stderr'}"
            ),
        )

    try:
        parse_scan_helper_output(result.stdout)
    except ScannerError as exc:
        return CheckResult(
            name="wikigo_comments_scan",
            status="failed",
            message=f"wikigo-comments-scan returned invalid output: {exc}",
        )

    return CheckResult(
        name="wikigo_comments_scan",
        status="ok",
        message="wikigo-comments-scan executed and returned parseable output",
    )


def _check_runner(config: AppConfig, *, subprocess_run: Any) -> CheckResult:
    try:
        result = subprocess_run(
            list(config.runner.argv),
            input=RUNNER_SMOKE_ENVELOPE,
            capture_output=True,
            text=True,
            check=False,
            timeout=RUNNER_SMOKE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        command = " ".join(config.runner.argv)
        return CheckResult(
            name="runner",
            status="failed",
            message=f"runner executable was not found: {command}",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="runner",
            status="failed",
            message="runner smoke invocation timed out",
        )

    if result.returncode != 0:
        return CheckResult(
            name="runner",
            status="failed",
            message=(
                "runner smoke invocation exited with "
                f"{result.returncode}: {result.stderr.strip() or 'no stderr'}"
            ),
        )

    try:
        payload = parse_runner_response(result.stdout)
    except RunnerInvocationError as exc:
        return CheckResult(
            name="runner",
            status="failed",
            message=f"runner smoke invocation returned invalid output: {exc}",
        )

    if payload.get("status") != STATUS_UPDATE_FAILED:
        return CheckResult(
            name="runner",
            status="failed",
            message="runner smoke invocation must finalize with UPDATE_FAILED for an invalid prompt envelope",
        )

    return CheckResult(
        name="runner",
        status="ok",
        message="runner finalized an invalid-envelope smoke invocation with UPDATE_FAILED without reaching the model",
    )
