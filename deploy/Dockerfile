FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends git gettext \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app /srv/repos \
    && chown app:app /app /srv/repos

USER app
WORKDIR /app
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY --chown=app:app src ./src
COPY --chown=app:app --chmod=755 deploy/entrypoint.sh deploy/gunicorn.conf.py ./

WORKDIR /app/src
EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--config", "/app/gunicorn.conf.py", "syngraphe.wsgi:application"]
