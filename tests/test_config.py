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
