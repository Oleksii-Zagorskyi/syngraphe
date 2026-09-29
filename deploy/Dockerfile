# The editor's bundle, built from the lockfile; only its output reaches the application image.
FROM node:22-bookworm-slim AS editor
WORKDIR /build
COPY package.json package-lock.json esbuild.config.mjs ./
RUN npm ci --no-audit --no-fund
COPY src/editing ./src/editing
RUN npm run build

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

# rclone from its release, version and checksums pinned (DL-0312); the checksums are those of the
# release's signed SHA256SUMS.
ARG RCLONE_VERSION=1.68.2
ARG RCLONE_SHA256_AMD64=0e6fa18051e67fc600d803a2dcb10ddedb092247fc6eee61be97f64ec080a13c
ARG RCLONE_SHA256_ARM64=c6e9d4cf9c88b279f6ad80cd5675daebc068e404890fa7e191412c1bc7a4ac5f
RUN arch="$(dpkg --print-architecture)" \
    && case "$arch" in amd64) sum="$RCLONE_SHA256_AMD64" ;; arm64) sum="$RCLONE_SHA256_ARM64" ;; \
       *) echo "no rclone for $arch" >&2; exit 1 ;; esac \
    && python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/tmp/rclone.zip')" \
       "https://downloads.rclone.org/v${RCLONE_VERSION}/rclone-v${RCLONE_VERSION}-linux-${arch}.zip" \
    && echo "$sum  /tmp/rclone.zip" | sha256sum -c - \
    && python -c "import sys, zipfile; zipfile.ZipFile('/tmp/rclone.zip').extract(sys.argv[1], '/tmp')" \
       "rclone-v${RCLONE_VERSION}-linux-${arch}/rclone" \
    && install -m 755 "/tmp/rclone-v${RCLONE_VERSION}-linux-${arch}/rclone" /usr/local/bin/rclone \
    && rm -rf /tmp/rclone.zip "/tmp/rclone-v${RCLONE_VERSION}-linux-${arch}"

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app /srv/repos \
    && chown app:app /app /srv/repos

USER app
WORKDIR /app
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY --chown=app:app src ./src
COPY --from=editor --chown=app:app /build/src/editing/static/editing/ ./src/editing/static/editing/
# The catalogue is compiled here as well as committed, so an edited .po never ships stale.
RUN msgfmt --check --statistics -o src/shell/locale/uk/LC_MESSAGES/django.mo src/shell/locale/uk/LC_MESSAGES/django.po
COPY --chown=app:app deploy/entrypoint.sh deploy/gunicorn.conf.py ./
# Set here, not with COPY --chmod, so the image builds without BuildKit too.
RUN chmod 755 entrypoint.sh

WORKDIR /app/src
EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--config", "/app/gunicorn.conf.py", "syngraphe.wsgi:application"]
