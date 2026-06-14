from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_defines_runtime_image_contract() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.14-slim" in dockerfile
    assert "AS build" in dockerfile
    assert "AS runtime" in dockerfile
    assert "uv export --locked --no-dev" in dockerfile
    assert "uv build --wheel" in dockerfile
    assert "dist/*.whl" in dockerfile
    assert 'ENTRYPOINT ["wiki-agent"]' in dockerfile
    assert 'CMD ["run", "--config", "/config/config.toml"]' in dockerfile
    assert "bash curl" in dockerfile
    assert "USER wiki-agent" in dockerfile


def test_dockerignore_excludes_non_runtime_context() -> None:
    dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert ".env" in dockerignore
    assert ".env.*" in dockerignore
    assert "config.toml" in dockerignore
    assert ".runtime/" in dockerignore
    assert ".venv/" in dockerignore
    assert "tests/" in dockerignore
    assert "docs/" in dockerignore


def test_publish_workflow_targets_ghcr_contract() -> None:
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "publish-docker-image.yml"
    ).read_text(encoding="utf-8")

    assert "pull_request:" not in workflow
    assert "push:" in workflow
    assert "- main" in workflow
    assert "workflow_dispatch:" in workflow
    assert "github.repository == 'chof747/wiki-agent'" in workflow
    assert "ghcr.io/${{ github.repository }}" in workflow
    assert "docker/metadata-action" in workflow
    assert "docker/setup-buildx-action" in workflow
    assert "type=gha" in workflow
    assert "linux/amd64" in workflow
    assert "wiki-agent --help" in workflow
    assert "type=sha" in workflow
    assert "type=ref,event=branch" in workflow
    assert "{{branch}}-sha-{{sha}}" in workflow
    assert "latest" in workflow


def test_docker_operator_doc_covers_runtime_usage() -> None:
    doc = (REPO_ROOT / "docs" / "operators" / "docker-image.md").read_text(
        encoding="utf-8"
    )

    assert "ghcr.io/chof747/wiki-agent" in doc
    assert "/config/config.toml" in doc
    assert "docker compose" in doc.lower()
    assert "Postgres" in doc
    assert "Wiki-Go" in doc
    assert "public" in doc
    assert "workflow_dispatch" in doc
    assert "healthcheck" in doc.lower()
