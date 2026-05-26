from __future__ import annotations

from pathlib import Path

from tools import integration_harness


def test_ensure_runtime_files_uses_runtime_dsn_env_override(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    data_root = runtime_root / "wikigo-data"
    shims_root = runtime_root / "bin"
    bot_config_path = runtime_root / "wikigo-bot-config.json"
    admin_config_path = runtime_root / "wikigo-admin-config.json"
    wiki_agent_config_path = runtime_root / "wiki-agent.integration.toml"

    monkeypatch.setattr(integration_harness, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(integration_harness, "DATA_ROOT", data_root)
    monkeypatch.setattr(integration_harness, "SHIMS_ROOT", shims_root)
    monkeypatch.setattr(integration_harness, "BOT_CONFIG_PATH", bot_config_path)
    monkeypatch.setattr(integration_harness, "ADMIN_CONFIG_PATH", admin_config_path)
    monkeypatch.setattr(integration_harness, "WIKI_AGENT_CONFIG_PATH", wiki_agent_config_path)
    monkeypatch.setenv(
        integration_harness.RUNTIME_POSTGRES_DSN_ENV,
        "postgresql://ci:ci@localhost:5432/wiki_agent_ci",
    )

    integration_harness.ensure_runtime_files({"base_url": "http://127.0.0.1:4010", "port": 4010})

    config_text = wiki_agent_config_path.read_text(encoding="utf-8")
    assert 'dsn = "postgresql://ci:ci@localhost:5432/wiki_agent_ci"' in config_text
