from __future__ import annotations

from dataclasses import dataclass


class RunnerConfigError(ValueError):
    """Raised when runner configuration is invalid."""


@dataclass(frozen=True)
class RunnerCommand:
    argv: tuple[str, ...]


def validate_runner_command(value: object) -> RunnerCommand:
    if not isinstance(value, list) or not value:
        raise RunnerConfigError("runner.command must be a non-empty list of strings")

    argv: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RunnerConfigError(
                "runner.command must contain only non-empty strings"
            )
        argv.append(item)

    return RunnerCommand(argv=tuple(argv))

