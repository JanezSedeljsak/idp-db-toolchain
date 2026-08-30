# syntax=docker/dockerfile:1

FROM python:3.14-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY README.md manage.py backupper.toml ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.14-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.14/site-packages/pip* \
    && rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.14

WORKDIR /app

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin backupper

COPY --from=builder --chown=backupper:backupper /app /app

USER backupper

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "manage.py"]
