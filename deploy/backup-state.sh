#!/bin/sh
# Writes the backup service's two files on the state volume (ADR-0019):
#   base — takes a full base backup, then writes `base-backup`: its label and stop time;
#   wal  — writes `wal`: the log waiting to be archived and the last segment archived.
# Each file is written to a temporary name and renamed.
set -eu
state="${BACKUP_STATE_DIR:-/srv/backup-state}/backup"
data=/var/lib/postgresql/data
segment=16777216

write() {
    tmp="$(mktemp "$state/.$1.XXXXXX")"
    printf '%s\n' "$2" > "$tmp"
    chmod 644 "$tmp"
    mv "$tmp" "$state/$1"
}

case "${1:-}" in
base)
    pgbackrest --stanza=syngraphe --type=full backup
    info="$(pgbackrest --stanza=syngraphe --output=json info)"
    label="$(printf '%s' "$info" | jq -r '.[0].backup[-1].label')"
    stop="$(printf '%s' "$info" | jq -r '.[0].backup[-1].timestamp.stop')"
    write base-backup "$(jq -cn --arg label "$label" --arg stop "$(date -u -d "@$stop" +%Y%m%dT%H%M%SZ)" \
        '{label: $label, stop: $stop}')"
    ;;
wal)
    ready="$(find "$data/pg_wal/archive_status" -name '*.ready' 2>/dev/null | wc -l)"
    archiver="$(psql -h /var/run/postgresql -U "$POSTGRES_USER" -d postgres -Atc \
        "SELECT last_archived_wal, to_char(last_archived_time AT TIME ZONE 'UTC', 'YYYYMMDD\"T\"HH24MISS\"Z\"') FROM pg_stat_archiver" \
        2>/dev/null || true)"
    segment_name="${archiver%%|*}"
    last="${archiver#*|}"
    # Past archive-push-queue-max, segments are acknowledged without being shipped: a segment
    # counts as archived only when the store's archive reaches it.
    stored="$(pgbackrest --stanza=syngraphe --output=json info 2>/dev/null \
        | jq -r '.[0].archive[-1].max // ""' 2>/dev/null || true)"
    if [ -z "$segment_name" ] || [ -z "$stored" ] || [ "$(printf '%s\n%s\n' "$segment_name" "$stored" | sort | tail -n 1)" != "$stored" ]; then
        last=""
    fi
    write wal "$(jq -cn --argjson waiting "$((ready * segment))" --arg last "$last" \
        '{waiting_bytes: $waiting, last_archived: (if $last == "" then null else $last end)}')"
    ;;
*)
    echo "usage: backup-state.sh base|wal" >&2
    exit 2
    ;;
esac
