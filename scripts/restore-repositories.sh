#!/bin/sh
# Every repository, or one, from its newest full bundle and every bundle after it, in order.
# A repository already on disk is left alone, so the script can be run again after a failure.
# From the repository checkout on the host:
#   scripts/restore-repositories.sh [--tenant N [--document M]]
set -eu
compose="${COMPOSE:-docker compose}"
exec $compose run --rm --no-deps --entrypoint python worker manage.py restore_repositories "$@"
