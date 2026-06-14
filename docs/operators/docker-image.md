# Docker Image

Wiki Agent publishes a runtime image to GitHub Container Registry at:

`ghcr.io/chof747/wiki-agent`

## Tags

- `latest`: published on pushes to `main`
- `sha-<full-commit-sha>`: immutable tag published on pushes to `main`
- `<branch-name>`: moving tag published by manual `workflow_dispatch` runs
- `<branch-name>-sha-<full-commit-sha>`: immutable tag published by manual `workflow_dispatch` runs

The first publish may require a one-time manual GHCR package visibility change to public.

## Runtime contract

The image is application-only. Postgres and Wiki-Go stay external and must be reachable from the container at runtime.

The default container command is:

```text
wiki-agent run --config /config/config.toml
```

Mount your runtime config at `/config/config.toml`. Supply secrets and configuration through that mounted TOML and/or environment variables. Do not bake secrets into the image.

There is no Docker healthcheck in this slice. Wait for the local health/status endpoint work before relying on a container `HEALTHCHECK`.

## Compose snippet

This issue does not add a full Compose stack, but operators with an existing `docker compose` setup can use the image like this:

```yaml
services:
  wiki-agent:
    image: ghcr.io/chof747/wiki-agent:latest
    restart: unless-stopped
    volumes:
      - ./wiki-agent/config.toml:/config/config.toml:ro
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
```

Wire Postgres and Wiki-Go connectivity through the mounted config and your existing network setup.

## Branch image testing

Use `workflow_dispatch` on the branch you want to test. That publishes:

- a moving `<branch-name>` tag for repeated branch testing
- an immutable `<branch-name>-sha-<full-commit-sha>` tag for pinning a specific branch build

The moving branch tag is expected to change on later manual publishes from the same branch.

## Local verification

Build the image locally:

```bash
docker build -t wiki-agent:local .
```

Run safe installed entrypoint smoke checks:

```bash
docker run --rm wiki-agent:local --help
docker run --rm --entrypoint wikigo-helper wiki-agent:local --help
docker run --rm --entrypoint wikigo-page wiki-agent:local --help
```

`wiki-agent-runner --help` is intentionally not part of the smoke checks because the runner currently expects a prompt envelope on stdin rather than offering a safe help mode.
