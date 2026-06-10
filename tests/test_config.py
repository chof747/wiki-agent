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
