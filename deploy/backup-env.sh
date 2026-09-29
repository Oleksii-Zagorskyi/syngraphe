#!/bin/sh
# Run as root at the start of the db and backup containers: the backup store from `.env`, written
# where pgBackRest reads it, so the archive command, cron and an operator's `exec` read the same.
# BACKUP_TARGET names the store's kind, `sftp` or `s3`; every other key follows from it.
set -eu
umask 077

missing=""
need() {
    for key in "$@"; do
        eval "value=\${$key:-}"
        if [ -z "$value" ] || [ "$value" = '???' ]; then
            missing="$missing $key"
        fi
    done
}
# `???` is the template's mark for a value nobody supplied: absent, whatever its key.
for key in BACKUP_SFTP_PORT BACKUP_S3_REGION BACKUP_WAL_QUEUE_MAX; do
    eval "value=\${$key:-}"
    [ "$value" = '???' ] && unset "$key"
done
need BACKUP_TARGET BACKUP_DB_CIPHER_PASS POSTGRES_USER
case "${BACKUP_TARGET:-}" in
sftp) need BACKUP_SFTP_HOST BACKUP_SFTP_USER BACKUP_SFTP_PATH BACKUP_SFTP_KNOWN_HOSTS ;;
s3) need BACKUP_S3_ENDPOINT BACKUP_S3_BUCKET BACKUP_S3_PATH BACKUP_S3_ACCESS_KEY BACKUP_S3_SECRET_KEY ;;
esac
if [ -n "$missing" ]; then
    echo "backup: missing in .env:$missing" >&2
    exit 1
fi
if [ "$BACKUP_TARGET" = sftp ] && [ ! -s /run/backup/key.src ]; then
    echo "backup: BACKUP_KEY_FILE names no key file" >&2
    exit 1
fi

size() {
    # pgBackRest counts KB, MB, GB and TB in powers of 1024, as `.env` does with KiB and GiB.
    printf '%s' "$1" | sed -e 's/iB$/B/'
}

store() {
    case "$BACKUP_TARGET" in
    sftp)
        cat <<EOF
repo1-type=sftp
repo1-sftp-host=$BACKUP_SFTP_HOST
repo1-sftp-host-port=${BACKUP_SFTP_PORT:-22}
repo1-sftp-host-user=$BACKUP_SFTP_USER
repo1-sftp-private-key-file=/run/backup/key
repo1-sftp-host-key-check-type=strict
repo1-sftp-host-key-hash-type=sha256
repo1-sftp-known-host=/run/backup/known_hosts
repo1-path=/${BACKUP_SFTP_PATH#/}/database
EOF
        ;;
    s3)
        cat <<EOF
repo1-type=s3
repo1-s3-endpoint=$BACKUP_S3_ENDPOINT
repo1-s3-bucket=$BACKUP_S3_BUCKET
repo1-s3-region=${BACKUP_S3_REGION:-us-east-1}
repo1-s3-key=$BACKUP_S3_ACCESS_KEY
repo1-s3-key-secret=$BACKUP_S3_SECRET_KEY
repo1-s3-uri-style=path
repo1-path=/${BACKUP_S3_PATH#/}/database
EOF
        ;;
    *)
        echo "backup: BACKUP_TARGET must be sftp or s3 in .env" >&2
        exit 1
        ;;
    esac
}

install -d -m 755 /etc/pgbackrest/conf.d
conf="$(mktemp /etc/pgbackrest/conf.d/.store.XXXXXX)"
{
    echo '[global]'
    store
    echo "repo1-cipher-pass=$BACKUP_DB_CIPHER_PASS"
    echo "archive-push-queue-max=$(size "${BACKUP_WAL_QUEUE_MAX:-10GiB}")"
    echo '[syngraphe]'
    echo "pg1-user=$POSTGRES_USER"
} > "$conf"
chown postgres:postgres "$conf"
mv "$conf" /etc/pgbackrest/conf.d/store.conf

# The key and the pinned host key, readable by postgres alone.
if [ -f /run/backup/key.src ]; then
    install -o postgres -g postgres -m 600 /run/backup/key.src /run/backup/key
fi
printf '%s\n' "${BACKUP_SFTP_KNOWN_HOSTS:-}" > /run/backup/known_hosts
chown postgres:postgres /run/backup/known_hosts
