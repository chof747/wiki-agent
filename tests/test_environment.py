from __future__ import annotations

import os

from wiki_agent.environment import load_repo_environment


def test_load_repo_environment_sets_missing_values_from_repo_dotenv(monkeypatch, tmp_path) -> None:
    (tmp_path / ".env").write_text(
        "WIKI_AGENT_POSTGRES_DSN=postgresql://dotenv:dotenv@localhost:5432/wiki_agent\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("WIKI_AGENT_POSTGRES_DSN", raising=False)

    loaded_path = load_repo_environment(repo_root=tmp_path)

    assert loaded_path == tmp_path / ".env"
    assert os.environ["WIKI_AGENT_POSTGRES_DSN"] == "postgresql://dotenv:dotenv@localhost:5432/wiki_agent"


def test_load_repo_environment_preserves_existing_environment(monkeypatch, tmp_path) -> None:
    (tmp_path / ".env").write_text(
        "WIKI_AGENT_POSTGRES_DSN=postgresql://dotenv:dotenv@localhost:5432/wiki_agent\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "WIKI_AGENT_POSTGRES_DSN",
        "postgresql://exported:exported@localhost:5432/wiki_agent",
    )

    load_repo_environment(repo_root=tmp_path)

    assert os.environ["WIKI_AGENT_POSTGRES_DSN"] == "postgresql://exported:exported@localhost:5432/wiki_agent"
