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

ENV PATH="/opt/venv/bin:${PATH}"

USER wiki-agent
WORKDIR /home/wiki-agent

ENTRYPOINT ["wiki-agent"]
CMD ["run", "--config", "/config/config.toml"]
