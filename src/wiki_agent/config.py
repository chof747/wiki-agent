from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from datetime import timedelta
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
    scan_interval: timedelta
    stale_processing_timeout: timedelta


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
    scan_interval = _parse_duration_seconds(
        _env_or_value(
            "WIKI_AGENT_SCAN_INTERVAL",
            service.get("scan_interval", 60) if isinstance(service, dict) else 60,
        ),
        field_name="service.scan_interval",
    )
    stale_processing_timeout = _parse_duration_seconds(
        _env_or_value(
            "WIKI_AGENT_STALE_PROCESSING_TIMEOUT",
            service.get("stale_processing_timeout", 900) if isinstance(service, dict) else 900,
        ),
        field_name="service.stale_processing_timeout",
    )

    try:
        runner_command = validate_runner_command(runner_value)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    return AppConfig(
        bot_name=bot_name.strip(),
        postgres=PostgresConfig(dsn=postgres_dsn),
        runner=runner_command,
        service=ServiceConfig(
            log_level=log_level.strip().upper(),
            scan_interval=scan_interval,
            stale_processing_timeout=stale_processing_timeout,
        ),
    )


def _env_or_value(env_name: str, current: object) -> object:
    value = os.getenv(env_name)
    if value is not None:
        return value
    return current


def _looks_like_postgres_dsn(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"postgres", "postgresql"} and bool(parsed.path)


def _parse_duration_seconds(value: object, *, field_name: str) -> timedelta:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ConfigError(f"{field_name} must be a positive integer number of seconds")

    try:
        seconds = int(value)
    except ValueError as exc:
        raise ConfigError(f"{field_name} must be a positive integer number of seconds") from exc

    if seconds <= 0:
        raise ConfigError(f"{field_name} must be a positive integer number of seconds")

    return timedelta(seconds=seconds)
