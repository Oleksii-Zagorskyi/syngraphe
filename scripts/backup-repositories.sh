#!/bin/sh
# One bundle run now, as the ten-minute task runs it; the worker holds the store's key.
# From the repository checkout on the host: scripts/backup-repositories.sh
set -eu
compose="${COMPOSE:-docker compose}"
exec $compose exec worker python manage.py backup_repositories
