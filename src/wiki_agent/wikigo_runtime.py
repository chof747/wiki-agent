from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

from wiki_agent.config import ConfigError, load_wikigo_config


def load_runtime_config() -> dict[str, str]:
    config_value = os.environ.get("WIKIGO_RUNTIME_CONFIG")
    if config_value:
        config_path = Path(config_value)
        if not config_path.exists():
            raise SystemExit(f"WIKIGO_RUNTIME_CONFIG does not exist: {config_path}")
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        payload, config_path = _load_runtime_config_from_app_config()

    for key in ("base_url", "username", "password"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise SystemExit(f"runtime config field '{key}' must be a non-empty string")
    payload["config_file"] = str(config_path)
    return payload


def _load_runtime_config_from_app_config() -> tuple[dict[str, Any], Path]:
    config_value = os.environ.get("WIKI_AGENT_CONFIG_PATH")
    if not config_value:
        raise SystemExit("WIKIGO_RUNTIME_CONFIG is not set")

    config_path = Path(config_value)
    try:
        wikigo = load_wikigo_config(config_path)
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    payload = {
        "base_url": wikigo.base_url,
        "username": wikigo.username,
        "password": wikigo.password,
    }
    return payload, config_path


class WikiGoSession:
    def __init__(self, *, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self._login()

    def _login(self) -> None:
        payload = json.dumps(
            {
                "username": self._username,
                "password": self._password,
                "keeploggedin": False,
            }
        ).encode("utf-8")
        self.request("POST", "/api/login", body=payload, content_type="application/json")

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> bytes:
        request = urllib.request.Request(
            urllib.parse.urljoin(f"{self._base_url}/", endpoint.lstrip("/")),
            method=method,
            data=body,
        )
        if content_type:
            request.add_header("Content-Type", content_type)
        try:
            with self._opener.open(request) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(
                f"{method} {endpoint} failed with HTTP {exc.code}: {error_body}"
            ) from exc

    def get_json(self, endpoint: str) -> dict[str, Any]:
        payload = json.loads(self.request("GET", endpoint).decode("utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit(f"{endpoint} did not return a JSON object")
        return payload

    def post_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.request(
            "POST",
            endpoint,
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        if not response.strip():
            return {}
        parsed = json.loads(response.decode("utf-8"))
        if not isinstance(parsed, dict):
            return {}
        return parsed


def quote_page(page: str) -> str:
    return urllib.parse.quote(page, safe="/")
