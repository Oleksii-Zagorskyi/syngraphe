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

# git and gettext; weasyprint's Pango and HarfBuzz, and fonts that cover Cyrillic in every face,
# italic included (ADR-0013).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git gettext \
       fontconfig fonts-dejavu-core fonts-dejavu-extra \
       libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
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

# Pandoc's source for the exact release the Python package bundles, shipped beside it (ADR-0013);
# the build below refuses an image whose Pandoc is another release.
ARG PANDOC_VERSION=3.9
ARG PANDOC_SOURCE_SHA256=5a8c44ce2f4d0708babbabe09fb02b412ac4a96514654d45d70bdc4a41c81679
RUN mkdir -p /usr/share/doc/pandoc \
    && python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" \
       "https://hackage.haskell.org/package/pandoc-${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}.tar.gz" \
       "/usr/share/doc/pandoc/pandoc-${PANDOC_VERSION}.tar.gz" \
    && echo "$PANDOC_SOURCE_SHA256  /usr/share/doc/pandoc/pandoc-${PANDOC_VERSION}.tar.gz" | sha256sum -c -

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app /srv/repos /srv/exports \
    && chown app:app /app /srv/repos /srv/exports

USER app
WORKDIR /app
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
RUN test "$(python -c 'import pypandoc; print(pypandoc.get_pandoc_version())')" = "$PANDOC_VERSION"

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
