from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def test_runner_executes_successful_page_update_flow(tmp_path: Path) -> None:
    script = shutil.which("wiki-agent-runner")
    assert script is not None

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "page_markdown": "# Current page\n",
                "saved_markdown": None,
                "deleted_comment_ids": [],
                "comments": [{"id": "comment-1", "text": "@marvin rewrite this page"}],
            }
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "helper-log.jsonl"
    _write_wikigo_page_helper(tmp_path / "wikigo-page", state_path, log_path)
    _write_wikigo_comments_helper(tmp_path / "wikigo-comments", state_path, log_path)

    envelope = {
        "prompt": "# Replacement page\n\nUpdated content.\n",
        "original_comment_text": "@marvin rewrite this page",
        "target_page": "/pages/example",
        "comment_identity": "comment-1",
        "source_metadata": {"source_system": "wiki-go", "author": "alice"},
        "constraints": {
            "single_target_scope": {
                "target_page": "/pages/example",
                "mode": "attached_target_page_only",
            }
        },
    }

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [script],
        input=json.dumps(envelope),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "SUCCESS"}

    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [call["command"] for call in calls] == [
        "page.get",
        "page.save",
        "page.get",
        "comments.delete",
        "comments.list",
    ]
    assert calls[0]["page"] == "/pages/example"
    assert calls[1]["page"] == "/pages/example"
    assert calls[1]["content"] == "# Replacement page\n\nUpdated content.\n"
    assert calls[3] == {
        "command": "comments.delete",
        "comment_id": "comment-1",
        "page": "/pages/example",
    }
    assert calls[4]["page"] == "/pages/example"

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["saved_markdown"] == "# Replacement page\n\nUpdated content.\n"
    assert state["deleted_comment_ids"] == ["comment-1"]


def test_runner_returns_update_failed_when_save_confirmation_does_not_match(tmp_path: Path) -> None:
    script = shutil.which("wiki-agent-runner")
    assert script is not None

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "page_markdown": "# Current page\n",
                "saved_markdown": None,
                "comments": [{"id": "comment-1", "text": "@marvin rewrite this page"}],
                "skip_save": True,
            }
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "helper-log.jsonl"
    _write_wikigo_page_helper(tmp_path / "wikigo-page", state_path, log_path)
    _write_wikigo_comments_helper(tmp_path / "wikigo-comments", state_path, log_path)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [script],
        input=json.dumps(_envelope()),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "UPDATE_FAILED"}

    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [call["command"] for call in calls] == ["page.get", "page.save", "page.get"]


def test_runner_returns_delete_failed_when_comment_still_exists_after_delete(tmp_path: Path) -> None:
    script = shutil.which("wiki-agent-runner")
    assert script is not None

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "page_markdown": "# Current page\n",
                "saved_markdown": None,
                "deleted_comment_ids": [],
                "comments": [{"id": "comment-1", "text": "@marvin rewrite this page"}],
                "keep_comment_after_delete": True,
            }
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "helper-log.jsonl"
    _write_wikigo_page_helper(tmp_path / "wikigo-page", state_path, log_path)
    _write_wikigo_comments_helper(tmp_path / "wikigo-comments", state_path, log_path)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [script],
        input=json.dumps(_envelope()),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "DELETE_FAILED"}

    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [call["command"] for call in calls] == [
        "page.get",
        "page.save",
        "page.get",
        "comments.delete",
        "comments.list",
    ]


def _envelope() -> dict[str, object]:
    return {
        "prompt": "# Replacement page\n\nUpdated content.\n",
        "original_comment_text": "@marvin rewrite this page",
        "target_page": "/pages/example",
        "comment_identity": "comment-1",
        "source_metadata": {"source_system": "wiki-go", "author": "alice"},
        "constraints": {
            "single_target_scope": {
                "target_page": "/pages/example",
                "mode": "attached_target_page_only",
            }
        },
    }


def _write_wikigo_page_helper(path: Path, state_path: Path, log_path: Path) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import pathlib\n"
            "import sys\n"
            f"state_path = pathlib.Path({str(state_path)!r})\n"
            f"log_path = pathlib.Path({str(log_path)!r})\n"
            "state = json.loads(state_path.read_text(encoding='utf-8'))\n"
            "command = sys.argv[1]\n"
            "if command == 'get':\n"
            "    page = sys.argv[2]\n"
            "    log_path.write_text(log_path.read_text(encoding='utf-8') + json.dumps({'command': 'page.get', 'page': page}) + '\\n', encoding='utf-8') if log_path.exists() else log_path.write_text(json.dumps({'command': 'page.get', 'page': page}) + '\\n', encoding='utf-8')\n"
            "    markdown = state.get('saved_markdown') or state.get('page_markdown') or ''\n"
            "    sys.stdout.write(json.dumps({'markdown': markdown}))\n"
            "    raise SystemExit(0)\n"
            "if command == 'save':\n"
            "    page = sys.argv[2]\n"
            "    content = pathlib.Path(sys.argv[3]).read_text(encoding='utf-8')\n"
            "    log_path.write_text(log_path.read_text(encoding='utf-8') + json.dumps({'command': 'page.save', 'page': page, 'content': content}) + '\\n', encoding='utf-8') if log_path.exists() else log_path.write_text(json.dumps({'command': 'page.save', 'page': page, 'content': content}) + '\\n', encoding='utf-8')\n"
            "    if not state.get('skip_save'):\n"
            "        state['saved_markdown'] = content\n"
            "        state_path.write_text(json.dumps(state), encoding='utf-8')\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(f'unsupported wikigo-page command: {command}')\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_wikigo_comments_helper(path: Path, state_path: Path, log_path: Path) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import pathlib\n"
            "import sys\n"
            f"state_path = pathlib.Path({str(state_path)!r})\n"
            f"log_path = pathlib.Path({str(log_path)!r})\n"
            "state = json.loads(state_path.read_text(encoding='utf-8'))\n"
            "command = sys.argv[1]\n"
            "if command == 'delete':\n"
            "    comment_id = sys.argv[2]\n"
            "    page = sys.argv[3]\n"
            "    log_path.write_text(log_path.read_text(encoding='utf-8') + json.dumps({'command': 'comments.delete', 'comment_id': comment_id, 'page': page}) + '\\n', encoding='utf-8') if log_path.exists() else log_path.write_text(json.dumps({'command': 'comments.delete', 'comment_id': comment_id, 'page': page}) + '\\n', encoding='utf-8')\n"
            "    deleted = state.setdefault('deleted_comment_ids', [])\n"
            "    deleted.append(comment_id)\n"
            "    if not state.get('keep_comment_after_delete'):\n"
            "        state['comments'] = [item for item in state.get('comments', []) if item.get('id') != comment_id]\n"
            "    state_path.write_text(json.dumps(state), encoding='utf-8')\n"
            "    raise SystemExit(0)\n"
            "if command == 'list':\n"
            "    page = sys.argv[2]\n"
            "    log_path.write_text(log_path.read_text(encoding='utf-8') + json.dumps({'command': 'comments.list', 'page': page}) + '\\n', encoding='utf-8') if log_path.exists() else log_path.write_text(json.dumps({'command': 'comments.list', 'page': page}) + '\\n', encoding='utf-8')\n"
            "    sys.stdout.write(json.dumps(state.get('comments', [])))\n"
            "    raise SystemExit(0)\n"
            "raise SystemExit(f'unsupported wikigo-comments command: {command}')\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
