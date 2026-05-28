from __future__ import annotations

from pathlib import Path

import pytest

from tools import integration_harness


def test_load_or_create_state_creates_runtime_directory(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "runtime" / "integration-harness" / "state.json"

    monkeypatch.setattr(integration_harness, "STATE_PATH", state_path)

    state = integration_harness.load_or_create_state()

    assert state_path.exists()
    assert state_path.parent.is_dir()
    assert state["base_url"].startswith("http://127.0.0.1:")
    assert isinstance(state["port"], int)


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


def test_wait_for_http_includes_container_diagnostics_on_timeout(monkeypatch) -> None:
    timeline = iter([0.0, 0.0, 1.0])

    def fake_urlopen(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(integration_harness.time, "time", lambda: next(timeline))
    monkeypatch.setattr(integration_harness.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(integration_harness.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(integration_harness, "container_exists", lambda: True)
    monkeypatch.setattr(
        integration_harness,
        "container_state_summary",
        lambda: "Wiki-Go container state: status=exited, exit_code=1, error=none",
    )
    monkeypatch.setattr(integration_harness, "container_logs", lambda: "boot failed")

    with pytest.raises(SystemExit, match="Wiki-Go did not become ready") as excinfo:
        integration_harness.wait_for_http("http://127.0.0.1:4010", timeout_seconds=0.5)

    message = str(excinfo.value)
    assert "Last readiness probe error: connection refused or timed out" in message
    assert "Wiki-Go container state: status=exited, exit_code=1, error=none" in message
    assert "Wiki-Go container logs:\nboot failed" in message


def test_start_container_runs_wikigo_as_host_user(monkeypatch) -> None:
    captured: list[str] = []

    monkeypatch.setattr(integration_harness, "container_exists", lambda: False)
    monkeypatch.setattr(integration_harness.os, "getuid", lambda: 1001)
    monkeypatch.setattr(integration_harness.os, "getgid", lambda: 1002)
    monkeypatch.setattr(integration_harness, "run_docker", lambda args: captured.extend(args) or "")

    integration_harness.start_container({"base_url": "http://127.0.0.1:4010", "port": 4010})

    assert captured[:6] == [
        "run",
        "-d",
        "--name",
        integration_harness.CONTAINER_NAME,
        "--user",
        "1001:1002",
    ]
