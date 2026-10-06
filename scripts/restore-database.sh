#!/bin/sh
# The database of a whole-host restore, never past the repositories (ADR-0019). Prints the newest
# clean marker's start, the last good moment and the end of the archive, and the one that
# governs; writes nothing until the operator types `restore`. From the repository checkout on the
# host, with `db`, `web` and `worker` stopped:
#   scripts/restore-database.sh [--dry-run] [--good YYYYMMDDTHHMMSSZ] [--marker YYYYMMDDTHHMMSSZ]
#                               [--end-of-archive] [--database-only] [--despite-verify]
set -eu
compose="${COMPOSE:-docker compose}"
moment='^[0-9]{8}T[0-9]{6}Z$'
dry_run=0
despite_verify=0
good=""
marker=""
end_of_archive=0
database_only=0
while [ $# -gt 0 ]; do
    case "$1" in
    --dry-run) dry_run=1 ;;
    --despite-verify) despite_verify=1 ;;
    --end-of-archive) end_of_archive=1 ;;
    --database-only) database_only=1 ;;
    --good|--marker)
        [ $# -ge 2 ] && printf '%s' "$2" | grep -Eq "$moment" \
            || { echo "restore-database: $1 takes a time as YYYYMMDDTHHMMSSZ" >&2; exit 2; }
        if [ "$1" = --good ]; then good="$2"; else marker="$2"; fi
        shift
        ;;
    *) echo "restore-database: unknown argument $1" >&2; exit 2 ;;
    esac
    shift
done

set --
[ -n "$good" ] && set -- "$@" --good "$good"
[ -n "$marker" ] && set -- "$@" --marker "$marker"
[ "$end_of_archive" = 1 ] && set -- "$@" --end-of-archive
[ "$database_only" = 1 ] && set -- "$@" --database-only

if verify="$($compose run --rm --no-deps --entrypoint sh backup -c \
    '/usr/local/bin/backup-env.sh && su postgres -s /bin/sh -c "pgbackrest --stanza=syngraphe verify --verbose"' \
    2>&1)"; then
    :
elif [ "$despite_verify" = 1 ]; then
    printf '%s\n' "$verify" >&2
    echo "restore-database: pgbackrest verify failed; going on, as --despite-verify asks" >&2
else
    printf '%s\n' "$verify" >&2
    echo "restore-database: pgbackrest verify failed; read it, then run again with --despite-verify if the archive is still usable" >&2
    exit 1
fi

plan="$(printf '%s\n' "$verify" | $compose run --rm --no-deps -T --entrypoint python worker \
    manage.py restore_plan "$@")"
printf '%s\n' "$plan"
recovery="$(printf '%s\n' "$plan" | tail -n 1)"
printf '%s' "$recovery" | grep -Eq '^(PGBACKREST_[A-Z_]+=[0-9A-Za-z:+-]+ ?)+$' \
    || { echo "restore-database: the plan's last line is not a recovery" >&2; exit 1; }

if [ "$dry_run" = 1 ]; then
    exit 0
fi
if [ -n "$($compose ps --status running -q db 2>/dev/null)" ]; then
    echo "restore-database: stop db first; a running database is never restored over" >&2
    exit 1
fi
printf 'Type restore to restore the database with: %s\n> ' "$recovery"
read -r answer
[ "$answer" = restore ] || { echo "restore-database: nothing written" >&2; exit 1; }
set --
for assignment in $recovery; do
    # pgBackRest reads a time target only with a space between the date and the time; the plan's
    # line keeps the target one word, so its `T` becomes the space here, the value passed whole.
    case $assignment in
        PGBACKREST_TARGET=*) assignment="$(printf '%s' "$assignment" | sed 's/\([0-9]\)T\([0-9]\)/\1 \2/')" ;;
    esac
    set -- "$@" -e "$assignment"
done
$compose run --rm --no-deps "$@" --entrypoint sh db -c \
    '/usr/local/bin/backup-env.sh && su postgres -s /bin/sh -c "pgbackrest --stanza=syngraphe --delta restore"'
echo "restore-database: restored; start db alone and confirm it accepts connections"
