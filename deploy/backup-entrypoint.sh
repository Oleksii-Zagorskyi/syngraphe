#!/bin/sh
# The backup service: creates the stanza once the database answers, then runs cron.
set -eu
/usr/local/bin/backup-env.sh
state="${BACKUP_STATE_DIR:-/srv/backup-state}"
# One folder per writer, each readable by every service: `backup/` this service's, as postgres;
# `worker/` the application's, uid 1000 in its image.
chmod 755 "$state"
install -d -o postgres -g postgres -m 755 "$state/backup"
install -d -o 1000 -g 1000 -m 755 "$state/worker"
# cron starts its jobs with an empty environment; the two values the jobs need are kept here.
printf "export POSTGRES_USER='%s'\nexport BACKUP_STATE_DIR='%s'\n" "$POSTGRES_USER" "$state" \
    > /run/backup/environment
chown postgres:postgres /run/backup/environment
# Written to pgBackRest's own file; cron and its jobs never see them.
unset BACKUP_DB_CIPHER_PASS BACKUP_S3_ACCESS_KEY BACKUP_S3_SECRET_KEY
until su postgres -s /bin/sh -c 'pg_isready -q -h /var/run/postgresql'; do sleep 2; done
su postgres -s /bin/sh -c 'pgbackrest --stanza=syngraphe stanza-create'
crontab /etc/syngraphe/backup-cron
exec cron -f
