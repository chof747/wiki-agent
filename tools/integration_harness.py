from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import shutil
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psycopg


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = REPO_ROOT / ".runtime" / "integration-harness"
DATA_ROOT = RUNTIME_ROOT / "wikigo-data"
SHIMS_ROOT = RUNTIME_ROOT / "bin"
FIXTURE_PATH = REPO_ROOT / "tests" / "integration_fixtures" / "scanner_dry_run.json"
STATE_PATH = RUNTIME_ROOT / "state.json"
BOT_CONFIG_PATH = RUNTIME_ROOT / "wikigo-bot-config.json"
ADMIN_CONFIG_PATH = RUNTIME_ROOT / "wikigo-admin-config.json"
WIKI_AGENT_CONFIG_PATH = RUNTIME_ROOT / "wiki-agent.integration.toml"
WIKIGO_IMAGE = "leomoonstudios/wiki-go:1.8.9@sha256:4777627c5475f9893ae42ad9af629838723d5bc90f74a3b811a997f5ff85cd20"
BOT_USERNAME = "marvin"
BOT_PASSWORD = "marvin-pass"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"
CONTAINER_NAME = "wiki-agent-integration-harness"
DEFAULT_ADMIN_POSTGRES_DSN = "postgresql://integration:integration@localhost:5432/postgres"
DEFAULT_RUNTIME_POSTGRES_DSN = "postgresql://integration:integration@localhost:5432/wiki_agent_integration"
ADMIN_POSTGRES_DSN_ENV = "WIKI_AGENT_INTEGRATION_ADMIN_DSN"
RUNTIME_POSTGRES_DSN_ENV = "WIKI_AGENT_INTEGRATION_RUNTIME_DSN"
MAIN_APP_POSTGRES_DSN_ENV = "WIKI_AGENT_POSTGRES_DSN"
WIKIGO_READY_TIMEOUT_SECONDS = 90.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="integration-harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("up")
    subparsers.add_parser("reset")
    subparsers.add_parser("test")
    subparsers.add_parser("down")
    args = parser.parse_args(argv)

    if args.command == "up":
        up()
        return 0
    if args.command == "reset":
        up()
        reset()
        return 0
    if args.command == "test":
        up()
        reset()
        run_test()
        return 0
    if args.command == "down":
        down()
        return 0

    parser.error("unsupported command")
    return 2


def up() -> None:
    state = load_or_create_state()
    if container_exists() and container_host_port() is None:
        run_docker(["rm", "-f", CONTAINER_NAME])
    if container_exists():
        state = sync_state_with_container(state)
    ensure_runtime_files(state)

    if not container_exists():
        if not (DATA_ROOT / "config.yaml").exists():
            bootstrap_default_data_dir(state)
        start_container(state)
    elif not container_running():
        start_container(state)

    state = sync_state_with_container(state)
    ensure_runtime_files(state)
    wait_for_http(state["base_url"])
    if not can_login(state["base_url"], ADMIN_USERNAME, ADMIN_PASSWORD):
        down()
        wipe_data_root()
        bootstrap_default_data_dir(state)
        start_container(state)
        state = sync_state_with_container(state)
        ensure_runtime_files(state)
        wait_for_http(state["base_url"])
    print(f"Wiki-Go harness is ready at {state['base_url']}")


def reset() -> None:
    state = load_or_create_state()
    env_admin = helper_env(ADMIN_CONFIG_PATH)
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    ensure_runtime_database()
    ensure_user(env_admin, BOT_USERNAME, BOT_PASSWORD, role="admin")

    delete_documents(env_admin, [doc["path"] for doc in fixture["documents"]])
    create_documents_and_comments(env_admin, fixture)

    print(f"Seeded scanner dry-run fixture set at {state['base_url']}")


def run_test() -> None:
    env = os.environ.copy()
    env["PATH"] = f"{SHIMS_ROOT}:{env['PATH']}"
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", "/private/tmp/uv-cache")
    env["WIKI_AGENT_INTEGRATION_CONFIG"] = str(WIKI_AGENT_CONFIG_PATH)
    env[ADMIN_POSTGRES_DSN_ENV] = admin_postgres_dsn()
    env[RUNTIME_POSTGRES_DSN_ENV] = runtime_postgres_dsn()
    result = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "--override-ini=addopts=",
            "-m",
            "integration",
            "tests/integration",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout or "integration pytest run failed")

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=os.sys.stderr)


def down() -> None:
    if container_exists():
        run_docker(["rm", "-f", CONTAINER_NAME])
        print("Wiki-Go harness container removed.")
    else:
        print("Wiki-Go harness container is not present.")


def ensure_runtime_files(state: dict[str, Any]) -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    SHIMS_ROOT.mkdir(parents=True, exist_ok=True)
    BOT_CONFIG_PATH.write_text(
        json.dumps(
            {
                "base_url": state["base_url"],
                "username": BOT_USERNAME,
                "password": BOT_PASSWORD,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ADMIN_CONFIG_PATH.write_text(
        json.dumps(
            {
                "base_url": state["base_url"],
                "username": ADMIN_USERNAME,
                "password": ADMIN_PASSWORD,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    WIKI_AGENT_CONFIG_PATH.write_text(
        (
            f'bot_name = "{BOT_USERNAME}"\n\n'
            "[postgres]\n"
            f'dsn = "{runtime_postgres_dsn()}"\n\n'
            "[wikigo]\n"
            f'base_url = "{state["base_url"]}"\n'
            f'username = "{BOT_USERNAME}"\n'
            f'password = "{BOT_PASSWORD}"\n\n'
            "[runner]\n"
            'command = ["wiki-agent-runner"]\n\n'
            "[runner.openai]\n"
            f'api_key = "{_toml_string(os.environ.get("OPENAI_API_KEY", "replace-me"))}"\n'
            f'model = "{_toml_string(os.environ.get("WIKI_AGENT_RUNNER_OPENAI_MODEL", "gpt-4o-2024-08-06"))}"\n'
            f'max_input_bytes = {int(os.environ.get("WIKI_AGENT_RUNNER_MAX_INPUT_BYTES", "32768"))}\n'
            f'max_output_bytes = {int(os.environ.get("WIKI_AGENT_RUNNER_MAX_OUTPUT_BYTES", "40960"))}\n'
            f'timeout_seconds = {float(os.environ.get("WIKI_AGENT_RUNNER_MODEL_TIMEOUT_SECONDS", "60"))}\n\n'
            "[service]\n"
            'log_level = "INFO"\n'
        ),
        encoding="utf-8",
    )
    write_shims()


def load_or_create_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    port = allocate_port()
    state = {"base_url": f"http://127.0.0.1:{port}", "port": port}
    save_state(state)
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def sync_state_with_container(state: dict[str, Any]) -> dict[str, Any]:
    if not container_exists():
        return state

    port = container_host_port()
    if port is None:
        raise SystemExit(
            f"{CONTAINER_NAME} exists but does not publish 8080/tcp; remove it and rerun the harness"
        )
    if port == state["port"]:
        return state

    synced_state = {"base_url": f"http://127.0.0.1:{port}", "port": port}
    save_state(synced_state)
    return synced_state


def container_host_port() -> int | None:
    result = subprocess.run(
        ["docker", "port", CONTAINER_NAME, "8080/tcp"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if "No public port '8080/tcp' published" in detail:
            return None
        raise SystemExit(detail or "docker command failed")

    mapping = result.stdout.strip()
    _, _, host_port = mapping.rpartition(":")
    if not host_port.isdigit():
        raise SystemExit(f"unable to determine Wiki-Go harness port from: {mapping}")
    return int(host_port)


def allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def helper_env(config_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["WIKIGO_RUNTIME_CONFIG"] = str(config_path)
    return env


def admin_postgres_dsn() -> str:
    return _dsn_from_env(
        ADMIN_POSTGRES_DSN_ENV,
        fallback_env=MAIN_APP_POSTGRES_DSN_ENV,
        default=DEFAULT_ADMIN_POSTGRES_DSN,
    )


def runtime_postgres_dsn() -> str:
    return _dsn_from_env(
        RUNTIME_POSTGRES_DSN_ENV,
        fallback_env=MAIN_APP_POSTGRES_DSN_ENV,
        default=DEFAULT_RUNTIME_POSTGRES_DSN,
    )


def _dsn_from_env(primary_env: str, *, fallback_env: str, default: str) -> str:
    primary_value = os.environ.get(primary_env)
    if primary_value:
        return primary_value

    fallback_value = os.environ.get(fallback_env)
    if fallback_value:
        return fallback_value

    return default


def ensure_runtime_database() -> None:
    runtime = psycopg.conninfo.conninfo_to_dict(runtime_postgres_dsn())
    database_name = runtime.get("dbname")
    if not isinstance(database_name, str) or not database_name:
        raise SystemExit("runtime Postgres DSN must include a database name")

    admin = psycopg.conninfo.conninfo_to_dict(admin_postgres_dsn())
    admin["dbname"] = admin.get("dbname") or "postgres"

    with psycopg.connect(**admin, autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,))
        if cursor.fetchone() is not None:
            return
        cursor.execute(
            f'CREATE DATABASE "{database_name.replace(chr(34), chr(34) * 2)}"'
        )


def bootstrap_default_data_dir(state: dict[str, Any]) -> None:
    start_container(state)
    wait_for_http(state["base_url"])
    run_docker(["stop", CONTAINER_NAME])

    config_path = DATA_ROOT / "config.yaml"
    text = config_path.read_text(encoding="utf-8")
    text = text.replace("allow_insecure_cookies: false", "allow_insecure_cookies: true")
    config_path.write_text(text, encoding="utf-8")


def start_container(state: dict[str, Any]) -> None:
    if container_exists():
        if not container_running():
            run_docker(["start", CONTAINER_NAME])
        return
    user = f"{os.getuid()}:{os.getgid()}"
    run_docker(
        [
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "--user",
            user,
            "-p",
            f"{state['port']}:8080",
            "-v",
            f"{DATA_ROOT}:/wiki/data",
            WIKIGO_IMAGE,
        ]
    )


def write_shims() -> None:
    shim_map = {
        "wikigo-config": ["config"],
        "wikigo-api": ["api"],
        "wikigo-comments": ["comments"],
        "wikigo-comments-scan": ["comments-scan"],
        "wikigo-create-document": ["create-document"],
        "wikigo-page": ["page"],
    }
    for name, helper_args in shim_map.items():
        shim_path = SHIMS_ROOT / name
        argv = " ".join(helper_args)
        shim_path.write_text(
            (
                "#!/bin/sh\n"
                f': "${{WIKI_AGENT_CONFIG_PATH:={WIKI_AGENT_CONFIG_PATH}}}"\n'
                "export WIKI_AGENT_CONFIG_PATH\n"
                f'exec env UV_CACHE_DIR="${{UV_CACHE_DIR:-/private/tmp/uv-cache}}" '
                f'uv run wikigo-helper {argv} "$@"\n'
            ),
            encoding="utf-8",
        )
        shim_path.chmod(0o755)


def _toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def run_docker(args: list[str]) -> str:
    result = subprocess.run(
        ["docker", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "docker command failed")
    return result.stdout.strip()


def container_exists() -> bool:
    result = subprocess.run(
        ["docker", "container", "inspect", CONTAINER_NAME],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def container_running() -> bool:
    result = subprocess.run(
        ["docker", "container", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def wait_for_http(base_url: str, timeout_seconds: float = WIKIGO_READY_TIMEOUT_SECONDS) -> None:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/check-auth", timeout=2) as response:
                if response.status in {200, 401}:
                    return
        except urllib.error.HTTPError as exc:
            if exc.code in {200, 401}:
                return
            last_error = f"HTTP {exc.code}: {exc.reason}"
        except OSError:
            last_error = "connection refused or timed out"
            time.sleep(0.5)
            continue
        time.sleep(0.5)
    raise SystemExit(readiness_timeout_message(base_url, last_error))


def readiness_timeout_message(base_url: str, last_error: str | None) -> str:
    parts = [f"Wiki-Go did not become ready at {base_url}"]
    if last_error:
        parts.append(f"Last readiness probe error: {last_error}")
    if container_exists():
        parts.append(container_state_summary())
        logs = container_logs()
        if logs:
            parts.append(f"Wiki-Go container logs:\n{logs}")
    else:
        parts.append(f"Wiki-Go container {CONTAINER_NAME} was not found")
    return "\n\n".join(parts)


def container_state_summary() -> str:
    result = subprocess.run(
        ["docker", "container", "inspect", CONTAINER_NAME],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return detail or f"unable to inspect {CONTAINER_NAME}"

    payload = json.loads(result.stdout)
    state = payload[0].get("State", {})
    status = state.get("Status", "unknown")
    exit_code = state.get("ExitCode", "unknown")
    error = state.get("Error") or "none"
    started_at = state.get("StartedAt", "unknown")
    finished_at = state.get("FinishedAt", "unknown")
    return (
        f"Wiki-Go container state: status={status}, exit_code={exit_code}, "
        f"error={error}, started_at={started_at}, finished_at={finished_at}"
    )


def container_logs() -> str:
    result = subprocess.run(
        ["docker", "logs", "--tail", "200", CONTAINER_NAME],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())


def can_login(base_url: str, username: str, password: str) -> bool:
    request = urllib.request.Request(
        urllib.parse.urljoin(f"{base_url}/", "api/login"),
        method="POST",
        data=json.dumps(
            {
                "username": username,
                "password": password,
                "keeploggedin": False,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5):
            return True
    except urllib.error.HTTPError:
        return False
    except OSError:
        return False


def ensure_user(env_admin: dict[str, str], username: str, password: str, *, role: str) -> None:
    payload = write_temp_json(
        {
            "username": username,
            "password": password,
            "role": role,
        }
    )
    try:
        result = subprocess.run(
            [str(SHIMS_ROOT / "wikigo-api"), "POST", "/api/users", str(payload), "application/json"],
            cwd=REPO_ROOT,
            env=env_admin,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return
        update_payload = write_temp_json(
            {
                "username": username,
                "new_password": password,
                "role": role,
            }
        )
        update_result = subprocess.run(
            [str(SHIMS_ROOT / "wikigo-api"), "PUT", "/api/users", str(update_payload), "application/json"],
            cwd=REPO_ROOT,
            env=env_admin,
            capture_output=True,
            text=True,
            check=False,
        )
        if update_result.returncode != 0:
            raise SystemExit(update_result.stderr or update_result.stdout or "unable to ensure bot user")
    finally:
        payload.unlink(missing_ok=True)
        if "update_payload" in locals():
            update_payload.unlink(missing_ok=True)


def delete_documents(env_admin: dict[str, str], doc_paths: list[str]) -> None:
    for path in sorted(doc_paths, key=lambda item: item.count("/"), reverse=True):
        result = subprocess.run(
            [str(SHIMS_ROOT / "wikigo-api"), "DELETE", f"/api/document/{path}"],
            cwd=REPO_ROOT,
            env=env_admin,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode not in {0, 1}:
            raise SystemExit(result.stderr or result.stdout or f"unable to delete document {path}")


def create_documents_and_comments(env_admin: dict[str, str], fixture: dict[str, Any]) -> None:
    for document in fixture["documents"]:
        content_path = write_temp_markdown(str(document["markdown"]))
        try:
            result = subprocess.run(
                [
                    str(SHIMS_ROOT / "wikigo-create-document"),
                    document["title"],
                    document["path"],
                    str(content_path),
                ],
                cwd=REPO_ROOT,
                env=env_admin,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise SystemExit(result.stderr or result.stdout or f"unable to create document {document['path']}")
        finally:
            content_path.unlink(missing_ok=True)

        for comment in document.get("comments", []):
            user_config = ADMIN_CONFIG_PATH if comment["author"] == ADMIN_USERNAME else BOT_CONFIG_PATH
            env = helper_env(user_config)
            payload = write_temp_json({"content": comment["content"]})
            try:
                result = subprocess.run(
                    [
                        str(SHIMS_ROOT / "wikigo-api"),
                        "POST",
                        f"/api/comments/add/{document['path']}",
                        str(payload),
                        "application/json",
                    ],
                    cwd=REPO_ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    raise SystemExit(result.stderr or result.stdout or "unable to add fixture comment")
            finally:
                payload.unlink(missing_ok=True)


def write_temp_json(payload: dict[str, Any]) -> Path:
    path = RUNTIME_ROOT / f"tmp-{time.time_ns()}.json"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return path


def write_temp_markdown(markdown: str) -> Path:
    path = RUNTIME_ROOT / f"tmp-{time.time_ns()}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def wipe_data_root() -> None:
    shutil.rmtree(DATA_ROOT, ignore_errors=True)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
