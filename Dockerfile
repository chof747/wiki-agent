FROM python:3.14-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:0.8.8 /uv /uvx /bin/

WORKDIR /build

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY tools ./tools

RUN uv export --locked --no-dev --no-emit-project --format requirements-txt -o requirements.txt
RUN uv build --wheel
RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python --requirement requirements.txt dist/*.whl


FROM python:3.14-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install --yes --no-install-recommends bash curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd \
    --create-home \
    --home-dir /home/wiki-agent \
    --shell /usr/sbin/nologin \
    --uid 10001 \
    wiki-agent \
    && mkdir /config \
    && chown wiki-agent:wiki-agent /config

COPY --from=build /opt/venv /opt/venv

RUN set -eu; \
    for name in wikigo-config wikigo-api wikigo-comments wikigo-comments-scan wikigo-create-document wikigo-page; do \
        case "$name" in \
            wikigo-config) helper_args='config' ;; \
            wikigo-api) helper_args='api' ;; \
            wikigo-comments) helper_args='comments' ;; \
            wikigo-comments-scan) helper_args='comments-scan' ;; \
            wikigo-create-document) helper_args='create-document' ;; \
            wikigo-page) helper_args='page' ;; \
        esac; \
        { \
            printf '%s\n' '#!/bin/sh'; \
            printf '%s\n' "exec wikigo-helper ${helper_args} \"\$@\""; \
        } > "/usr/local/bin/${name}"; \
        chmod 0755 "/usr/local/bin/${name}"; \
    done

ENV PATH="/opt/venv/bin:${PATH}"

HEALTHCHECK --interval=60s --timeout=30s --start-period=30s --retries=3 \
    CMD ["wiki-agent", "check", "--config", "/config/config.toml"]

USER wiki-agent
WORKDIR /home/wiki-agent

ENTRYPOINT ["wiki-agent"]
CMD ["run", "--config", "/config/config.toml"]
