from __future__ import annotations

from pathlib import Path

import wiki_agent.environment as environment
from wiki_agent import cli


def test_main_loads_repo_dotenv_before_loading_config(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "WIKI_AGENT_POSTGRES_DSN=postgresql://dotenv:dotenv@localhost:5432/wiki_agent\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        (
            'bot_name = "marvin"\n\n'
            "[wikigo]\n"
            'base_url = "http://127.0.0.1:4010"\n'
            'username = "marvin"\n'
            'password = "marvin-pass"\n\n'
            "[runner]\n"
            'command = ["wiki-agent-runner"]\n\n'
            "[runner.openai]\n"
            'api_key = "test-openai-key"\n'
            'model = "gpt-4o-2024-08-06"\n'
            "max_input_bytes = 32768\n"
            "max_output_bytes = 40960\n"
            "timeout_seconds = 60\n\n"
            "[service]\n"
            'log_level = "INFO"\n'
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class FakeApp:
        def __init__(self, config) -> None:  # type: ignore[no-untyped-def]
            captured["config"] = config

        def run_once(self, *, dry_run: bool) -> int:
            captured["dry_run"] = dry_run
            return 0

    monkeypatch.setattr(environment, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("WIKI_AGENT_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("WIKI_AGENT_CONFIG_PATH", raising=False)
    monkeypatch.setattr(cli, "WikiAgentApp", FakeApp)
    monkeypatch.setattr(cli, "configure_logging", lambda *_args, **_kwargs: None)

    assert cli.main(["run-once", "--dry-run", "--config", str(config_path)]) == 0
    assert captured["dry_run"] is True
    assert captured["config"].postgres.dsn == "postgresql://dotenv:dotenv@localhost:5432/wiki_agent"
