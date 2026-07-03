from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_repo_environment(*, repo_root: Path | None = None) -> Path | None:
    root = repo_root or REPO_ROOT
    dotenv_path = root / ".env"
    if not dotenv_path.exists():
        return None

    load_dotenv(dotenv_path=dotenv_path, override=False)
    return dotenv_path
