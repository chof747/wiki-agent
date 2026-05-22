from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from wiki_agent.runner_client import RunnerCommand, validate_runner_command


class ConfigError(ValueError):
    """Raised when configuration is missing or malformed."""


@dataclass(frozen=True)
class PostgresConfig:
    dsn: str


@dataclass(frozen=True)
class ServiceConfig:
    log_level: str


@dataclass(frozen=True)
class AppConfig:
    bot_name: str
    postgres: PostgresConfig
    runner: RunnerCommand
    service: ServiceConfig


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"config file does not exist: {path}")

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    bot_name = _env_or_value("WIKI_AGENT_BOT_NAME", raw.get("bot_name"))
    if not isinstance(bot_name, str) or not bot_name.strip():
        raise ConfigError("bot_name must be a non-empty string")

    postgres = raw.get("postgres")
    postgres_dsn = _env_or_value(
        "WIKI_AGENT_POSTGRES_DSN",
        postgres.get("dsn") if isinstance(postgres, dict) else None,
    )
    if not isinstance(postgres_dsn, str) or not _looks_like_postgres_dsn(postgres_dsn):
        raise ConfigError("postgres.dsn must be a non-empty postgres DSN")

    runner = raw.get("runner")
    runner_value = runner.get("command") if isinstance(runner, dict) else None
    runner_override = os.getenv("WIKI_AGENT_RUNNER_COMMAND_JSON")
    if runner_override:
        try:
            runner_value = json.loads(runner_override)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                "WIKI_AGENT_RUNNER_COMMAND_JSON must be valid JSON"
            ) from exc

    service = raw.get("service")
    log_level = _env_or_value(
        "WIKI_AGENT_LOG_LEVEL",
        service.get("log_level") if isinstance(service, dict) else None,
    )
    if not isinstance(log_level, str) or not log_level.strip():
        raise ConfigError("service.log_level must be a non-empty string")

    try:
        runner_command = validate_runner_command(runner_value)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    return AppConfig(
        bot_name=bot_name.strip(),
        postgres=PostgresConfig(dsn=postgres_dsn),
        runner=runner_command,
        service=ServiceConfig(log_level=log_level.strip().upper()),
    )


def _env_or_value(env_name: str, current: object) -> object:
    value = os.getenv(env_name)
    if value is not None:
        return value
    return current


def _looks_like_postgres_dsn(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"postgres", "postgresql"} and bool(parsed.path)

