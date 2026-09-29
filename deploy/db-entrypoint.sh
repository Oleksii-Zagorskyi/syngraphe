#!/bin/sh
# The database, refusing to start with an unset credential, its archive shipped by pgBackRest.
set -eu
for v in "$POSTGRES_DB" "$POSTGRES_USER" "$POSTGRES_PASSWORD"; do
    if [ -z "$v" ] || [ "$v" = '???' ]; then
        echo 'db: POSTGRES_DB, POSTGRES_USER and POSTGRES_PASSWORD must be set in .env' >&2
        exit 1
    fi
done
/usr/local/bin/backup-env.sh
# Written to pgBackRest's own file; the database server and its archive command never see them.
unset BACKUP_DB_CIPHER_PASS BACKUP_S3_ACCESS_KEY BACKUP_S3_SECRET_KEY
exec docker-entrypoint.sh "$@"
