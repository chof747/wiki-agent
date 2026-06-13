from __future__ import annotations

from pathlib import Path

import pytest

from tools import integration_harness


def test_main_loads_root_dotenv_before_running_command(monkeypatch, tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        'export WIKI_AGENT_POSTGRES_DSN="postgresql://dotenv:dotenv@localhost:5432/wiki_agent"\n',
        encoding="utf-8",
    )
    observed: list[str | None] = []

    monkeypatch.setattr(integration_harness, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("WIKI_AGENT_POSTGRES_DSN", raising=False)
    monkeypatch.delenv(integration_harness.RUNTIME_POSTGRES_DSN_ENV, raising=False)
    monkeypatch.delenv(integration_harness.ADMIN_POSTGRES_DSN_ENV, raising=False)
    monkeypatch.setattr(
        integration_harness,
        "up",
        lambda: observed.append(integration_harness.runtime_postgres_dsn()),
    )

    assert integration_harness.main(["up"]) == 0
    assert observed == ["postgresql://dotenv:dotenv@localhost:5432/wiki_agent"]


def test_main_preserves_exported_environment_over_root_dotenv(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "WIKI_AGENT_POSTGRES_DSN=postgresql://dotenv:dotenv@localhost:5432/wiki_agent\n",
        encoding="utf-8",
    )
    observed: list[str | None] = []

    monkeypatch.setattr(integration_harness, "REPO_ROOT", tmp_path)
    monkeypatch.delenv(integration_harness.RUNTIME_POSTGRES_DSN_ENV, raising=False)
    monkeypatch.delenv(integration_harness.ADMIN_POSTGRES_DSN_ENV, raising=False)
    monkeypatch.setenv(
        "WIKI_AGENT_POSTGRES_DSN",
        "postgresql://exported:exported@localhost:5432/wiki_agent",
    )
    monkeypatch.setattr(
        integration_harness,
        "up",
        lambda: observed.append(integration_harness.runtime_postgres_dsn()),
    )

    assert integration_harness.main(["up"]) == 0
    assert observed == ["postgresql://exported:exported@localhost:5432/wiki_agent"]


def test_load_or_create_state_creates_runtime_directory(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "runtime" / "integration-harness" / "state.json"

    monkeypatch.setattr(integration_harness, "STATE_PATH", state_path)
    monkeypatch.setattr(integration_harness, "allocate_port", lambda: 4010)

    state = integration_harness.load_or_create_state()

    assert state_path.exists()
    assert state_path.parent.is_dir()
    assert state["base_url"] == "http://127.0.0.1:4010"
    assert state["port"] == 4010


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


def test_runtime_postgres_dsn_falls_back_to_main_app_dsn(monkeypatch) -> None:
    monkeypatch.delenv(integration_harness.RUNTIME_POSTGRES_DSN_ENV, raising=False)
    monkeypatch.setenv(
        "WIKI_AGENT_POSTGRES_DSN",
        "postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent",
    )

    assert (
        integration_harness.runtime_postgres_dsn()
        == "postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent"
    )


def test_admin_postgres_dsn_falls_back_to_main_app_dsn(monkeypatch) -> None:
    monkeypatch.delenv(integration_harness.ADMIN_POSTGRES_DSN_ENV, raising=False)
    monkeypatch.setenv(
        "WIKI_AGENT_POSTGRES_DSN",
        "postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent",
    )

    assert (
        integration_harness.admin_postgres_dsn()
        == "postgresql://wiki_agent:wiki_agent@localhost:5432/wiki_agent"
    )


def test_app_env_uses_generated_harness_config_and_clears_helper_identity(monkeypatch, tmp_path: Path) -> None:
    shims_root = tmp_path / "bin"
    config_path = tmp_path / "wiki-agent.integration.toml"

    monkeypatch.setattr(integration_harness, "SHIMS_ROOT", shims_root)
    monkeypatch.setattr(integration_harness, "WIKI_AGENT_CONFIG_PATH", config_path)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("WIKIGO_RUNTIME_CONFIG", "/tmp/ambient-admin.json")
    monkeypatch.setenv("WIKI_AGENT_CONFIG_PATH", "/tmp/ambient-config.toml")
    monkeypatch.setenv(
        "WIKI_AGENT_POSTGRES_DSN",
        "postgresql://shared:shared@localhost:5432/wiki_agent",
    )

    env = integration_harness.app_env()

    assert env["PATH"] == f"{shims_root}:/usr/bin"
    assert env["WIKI_AGENT_CONFIG_PATH"] == str(config_path)
    assert env["WIKI_AGENT_INTEGRATION_CONFIG"] == str(config_path)
    assert "WIKIGO_RUNTIME_CONFIG" not in env
    assert (
        env[integration_harness.ADMIN_POSTGRES_DSN_ENV]
        == "postgresql://shared:shared@localhost:5432/wiki_agent"
    )
    assert (
        env[integration_harness.RUNTIME_POSTGRES_DSN_ENV]
        == "postgresql://shared:shared@localhost:5432/wiki_agent"
    )


def test_helper_env_uses_explicit_runtime_identity(monkeypatch, tmp_path: Path) -> None:
    shims_root = tmp_path / "bin"
    admin_config_path = tmp_path / "wikigo-admin-config.json"
    config_path = tmp_path / "wiki-agent.integration.toml"

    monkeypatch.setattr(integration_harness, "SHIMS_ROOT", shims_root)
    monkeypatch.setattr(integration_harness, "WIKI_AGENT_CONFIG_PATH", config_path)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("WIKIGO_RUNTIME_CONFIG", "/tmp/ambient-bot.json")
    monkeypatch.setenv("WIKI_AGENT_CONFIG_PATH", "/tmp/ambient-config.toml")

    env = integration_harness.helper_env(admin_config_path)

    assert env["PATH"] == f"{shims_root}:/usr/bin"
    assert env["WIKIGO_RUNTIME_CONFIG"] == str(admin_config_path)
    assert env["WIKI_AGENT_INTEGRATION_CONFIG"] == str(config_path)
    assert "WIKI_AGENT_CONFIG_PATH" not in env


def test_run_once_uses_harness_app_env(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(integration_harness, "up", lambda: observed.setdefault("up", True))
    monkeypatch.setattr(
        integration_harness,
        "app_env",
        lambda: {
            "PATH": "/tmp/harness/bin:/usr/bin",
            "WIKI_AGENT_CONFIG_PATH": "/tmp/wiki-agent.integration.toml",
        },
    )

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed["env"] = kwargs["env"]
        return FakeResult()

    monkeypatch.setattr(integration_harness.subprocess, "run", fake_run)

    integration_harness.run_once(dry_run=True)

    assert observed["argv"] == [
        "uv",
        "run",
        "wiki-agent",
        "run-once",
        "--config",
        "/tmp/wiki-agent.integration.toml",
        "--dry-run",
    ]
    assert observed["env"] == {
        "PATH": "/tmp/harness/bin:/usr/bin",
        "WIKI_AGENT_CONFIG_PATH": "/tmp/wiki-agent.integration.toml",
    }


def test_seed_comment_uses_admin_runtime_identity(monkeypatch) -> None:
    observed: dict[str, object] = {}

    monkeypatch.setattr(integration_harness, "up", lambda: observed.setdefault("up", True))
    monkeypatch.setattr(integration_harness, "reset", lambda: observed.setdefault("reset", True))
    monkeypatch.setattr(
        integration_harness,
        "helper_env",
        lambda config_path: {"WIKIGO_RUNTIME_CONFIG": str(config_path)},
    )
    monkeypatch.setattr(
        integration_harness,
        "delete_all_comments",
        lambda page_path, *, env: observed.setdefault("delete", (page_path, env.copy())),
    )
    monkeypatch.setattr(
        integration_harness,
        "create_comment",
        lambda page_path, comment_text, *, env: observed.setdefault(
            "create", (page_path, comment_text, env.copy())
        ),
    )
    monkeypatch.setattr(
        integration_harness,
        "truncate_comment_jobs",
        lambda: observed.setdefault("truncate", True),
    )

    integration_harness.seed_comment(
        page_path="team/roadmap",
        comment_text="@marvin investigate this",
        reset_comment_jobs=False,
    )

    assert observed["reset"] is True
    assert "truncate" not in observed
    assert observed["delete"] == (
        "team/roadmap",
        {"WIKIGO_RUNTIME_CONFIG": str(integration_harness.ADMIN_CONFIG_PATH)},
    )
    assert observed["create"] == (
        "team/roadmap",
        "@marvin investigate this",
        {"WIKIGO_RUNTIME_CONFIG": str(integration_harness.ADMIN_CONFIG_PATH)},
    )


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


def test_ensure_runtime_database_creates_missing_database(monkeypatch) -> None:
    executed: list[tuple[str, tuple[object, ...] | None]] = []

    class FakeCursor:
        def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
            executed.append((query, params))

        def fetchone(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setenv(
        integration_harness.ADMIN_POSTGRES_DSN_ENV,
        "postgresql://admin:admin@localhost:5432/postgres",
    )
    monkeypatch.setenv(
        integration_harness.RUNTIME_POSTGRES_DSN_ENV,
        "postgresql://integration:integration@localhost:5432/wiki_agent_integration",
    )
    monkeypatch.setattr(integration_harness.psycopg, "connect", lambda **kwargs: FakeConnection())

    integration_harness.ensure_runtime_database()

    assert executed == [
        ("SELECT 1 FROM pg_database WHERE datname = %s", ("wiki_agent_integration",)),
        ('CREATE DATABASE "wiki_agent_integration"', None),
    ]


def test_ensure_runtime_database_skips_existing_database(monkeypatch) -> None:
    executed: list[tuple[str, tuple[object, ...] | None]] = []

    class FakeCursor:
        def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
            executed.append((query, params))

        def fetchone(self):
            return (1,)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setenv(
        integration_harness.ADMIN_POSTGRES_DSN_ENV,
        "postgresql://admin:admin@localhost:5432/postgres",
    )
    monkeypatch.setenv(
        integration_harness.RUNTIME_POSTGRES_DSN_ENV,
        "postgresql://integration:integration@localhost:5432/wiki_agent_integration",
    )
    monkeypatch.setattr(integration_harness.psycopg, "connect", lambda **kwargs: FakeConnection())

    integration_harness.ensure_runtime_database()

    assert executed == [
        ("SELECT 1 FROM pg_database WHERE datname = %s", ("wiki_agent_integration",)),
    ]
