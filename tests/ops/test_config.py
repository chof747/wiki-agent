from __future__ import annotations

from pathlib import Path

from wiki_agent.ops.config import load_config


def _fixture_config_path():
    return Path(__file__).resolve().parents[1] / "fixtures" / "config.toml"


def _clear_runner_env(monkeypatch) -> None:
    for name in (
        "OPENAI_API_KEY",
        "WIKI_AGENT_RUNNER_OPENAI_MODEL",
        "WIKI_AGENT_RUNNER_MAX_INPUT_BYTES",
        "WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES",
        "WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS",
        "WIKI_AGENT_RUNNER_MAX_SEARCH_ACTIONS",
        "WIKI_AGENT_RUNNER_MAX_OPENED_LINKS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_env_override_for_postgres_dsn(monkeypatch) -> None:
    config_path = _fixture_config_path()
    monkeypatch.setenv(
        "WIKI_AGENT_POSTGRES_DSN",
        "postgresql://override:override@localhost:5432/override_db",
    )

    config = load_config(config_path)

    assert config.postgres.dsn.endswith("/override_db")


def test_load_config_reads_wikigo_and_runner_openai_settings(monkeypatch) -> None:
    config_path = _fixture_config_path()
    _clear_runner_env(monkeypatch)

    config = load_config(config_path)

    assert config.wikigo.base_url == "http://127.0.0.1:4010"
    assert config.wikigo.username == "marvin"
    assert config.wikigo.password == "marvin-pass"
    assert config.runner_openai.api_key == "test-openai-key"
    assert config.runner_openai.model == "gpt-4o-2024-08-06"
    assert config.runner_openai.max_input_bytes == 32768
    assert config.runner_openai.max_output_bytes == 40960
    assert config.runner_openai.timeout_seconds == 60.0


def test_service_timing_defaults_are_loaded(monkeypatch) -> None:
    config_path = _fixture_config_path()
    _clear_runner_env(monkeypatch)

    config = load_config(config_path)

    assert config.service.scan_interval.total_seconds() == 60
    assert config.service.stale_processing_timeout.total_seconds() == 900


def test_service_timing_env_overrides_are_applied(monkeypatch) -> None:
    config_path = _fixture_config_path()
    monkeypatch.setenv("WIKI_AGENT_SCAN_INTERVAL", "5")
    monkeypatch.setenv("WIKI_AGENT_STALE_PROCESSING_TIMEOUT", "11")

    config = load_config(config_path)

    assert config.service.scan_interval.total_seconds() == 5
    assert config.service.stale_processing_timeout.total_seconds() == 11


def test_runner_research_budget_defaults_are_loaded(monkeypatch) -> None:
    config_path = _fixture_config_path()
    _clear_runner_env(monkeypatch)

    config = load_config(config_path)

    assert config.runner_research_budget.max_search_actions == 3
    assert config.runner_research_budget.max_opened_links == 5


def test_runner_research_budget_env_overrides_are_applied(monkeypatch) -> None:
    config_path = _fixture_config_path()
    monkeypatch.setenv("WIKI_AGENT_RUNNER_MAX_SEARCH_ACTIONS", "4")
    monkeypatch.setenv("WIKI_AGENT_RUNNER_MAX_OPENED_LINKS", "7")

    config = load_config(config_path)

    assert config.runner_research_budget.max_search_actions == 4
    assert config.runner_research_budget.max_opened_links == 7
