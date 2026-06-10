from __future__ import annotations

from pathlib import Path

from wiki_agent.config import load_config


def test_env_override_for_postgres_dsn(monkeypatch) -> None:
    config_path = Path(__file__).parent / "fixtures" / "config.toml"
    monkeypatch.setenv(
        "WIKI_AGENT_POSTGRES_DSN",
        "postgresql://override:override@localhost:5432/override_db",
    )

    config = load_config(config_path)

    assert config.postgres.dsn.endswith("/override_db")


def test_load_config_reads_wikigo_and_runner_openai_settings() -> None:
    config_path = Path(__file__).parent / "fixtures" / "config.toml"

    config = load_config(config_path)

    assert config.wikigo.base_url == "http://127.0.0.1:4010"
    assert config.wikigo.username == "marvin"
    assert config.wikigo.password == "marvin-pass"
    assert config.runner_openai.api_key == "test-openai-key"
    assert config.runner_openai.model == "gpt-4o-2024-08-06"
    assert config.runner_openai.max_input_bytes == 32768
    assert config.runner_openai.max_output_bytes == 40960
    assert config.runner_openai.timeout_seconds == 60.0


def test_service_timing_defaults_are_loaded() -> None:
    config_path = Path(__file__).parent / "fixtures" / "config.toml"

    config = load_config(config_path)

    assert config.service.scan_interval.total_seconds() == 60
    assert config.service.stale_processing_timeout.total_seconds() == 900


def test_service_timing_env_overrides_are_applied(monkeypatch) -> None:
    config_path = Path(__file__).parent / "fixtures" / "config.toml"
    monkeypatch.setenv("WIKI_AGENT_SCAN_INTERVAL", "5")
    monkeypatch.setenv("WIKI_AGENT_STALE_PROCESSING_TIMEOUT", "11")

    config = load_config(config_path)

    assert config.service.scan_interval.total_seconds() == 5
    assert config.service.stale_processing_timeout.total_seconds() == 11
