#!/bin/sh
# Check the repository root, bring every schema up to date, then run the service's command.
set -eu

if [ ! -w /srv/repos ]; then
    echo "The repository root /srv/repos is not writable by the application; make the mounted directory writable by uid 1000." >&2
    exit 1
fi

python manage.py migrate_schemas
python manage.py seed_languages

exec "$@"
