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
class WikiGoConfig:
    base_url: str
    username: str
    password: str


@dataclass(frozen=True)
class RunnerOpenAIConfig:
    api_key: str
    model: str
    max_input_bytes: int
    max_output_bytes: int
    timeout_seconds: float


@dataclass(frozen=True)
class ServiceConfig:
    log_level: str


@dataclass(frozen=True)
class AppConfig:
    bot_name: str
    postgres: PostgresConfig
    wikigo: WikiGoConfig
    runner: RunnerCommand
    runner_openai: RunnerOpenAIConfig
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

    wikigo = raw.get("wikigo")
    if not isinstance(wikigo, dict):
        raise ConfigError("wikigo must be a table")

    base_url = wikigo.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ConfigError("wikigo.base_url must be a non-empty string")

    username = wikigo.get("username")
    if not isinstance(username, str) or not username.strip():
        raise ConfigError("wikigo.username must be a non-empty string")

    password = wikigo.get("password")
    if not isinstance(password, str) or not password.strip():
        raise ConfigError("wikigo.password must be a non-empty string")

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

    runner_openai = runner.get("openai") if isinstance(runner, dict) else None
    if not isinstance(runner_openai, dict):
        raise ConfigError("runner.openai must be a table")

    openai_api_key = _env_or_value("OPENAI_API_KEY", runner_openai.get("api_key"))
    if not isinstance(openai_api_key, str) or not openai_api_key.strip():
        raise ConfigError("runner.openai.api_key must be a non-empty string")

    openai_model = _env_or_value("WIKI_AGENT_RUNNER_OPENAI_MODEL", runner_openai.get("model"))
    if not isinstance(openai_model, str) or not openai_model.strip():
        raise ConfigError("runner.openai.model must be a non-empty string")

    max_input_bytes = _env_or_value(
        "WIKI_AGENT_RUNNER_MAX_INPUT_BYTES",
        runner_openai.get("max_input_bytes"),
    )
    if not _is_positive_int(max_input_bytes):
        raise ConfigError("runner.openai.max_input_bytes must be a positive integer")

    max_output_bytes = _env_or_value(
        "WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES",
        runner_openai.get("max_output_bytes"),
    )
    if not _is_positive_int(max_output_bytes):
        raise ConfigError("runner.openai.max_output_bytes must be a positive integer")

    timeout_seconds = _env_or_value(
        "WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS",
        runner_openai.get("timeout_seconds"),
    )
    if not _is_positive_float(timeout_seconds):
        raise ConfigError("runner.openai.timeout_seconds must be a positive number")

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
        wikigo=WikiGoConfig(
            base_url=base_url.strip(),
            username=username.strip(),
            password=password.strip(),
        ),
        runner=runner_command,
        runner_openai=RunnerOpenAIConfig(
            api_key=openai_api_key.strip(),
            model=openai_model.strip(),
            max_input_bytes=int(max_input_bytes),
            max_output_bytes=int(max_output_bytes),
            timeout_seconds=float(timeout_seconds),
        ),
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


def _is_positive_int(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    if isinstance(value, str):
        try:
            return int(value) > 0
        except ValueError:
            return False
    return False


def _is_positive_float(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return float(value) > 0
    if isinstance(value, str):
        try:
            return float(value) > 0
        except ValueError:
            return False
    return False
