#!/bin/sh
set -eu

: "${POSTGRES_USER:=postgres}"
: "${POSTGRES_DB:=$POSTGRES_USER}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${PGDATA:=/var/lib/postgresql/data}"

mkdir -p "$PGDATA" /run/postgresql
chown -R postgres:postgres "$PGDATA" /run/postgresql
chmod 0700 "$PGDATA"
chmod 2775 /run/postgresql

if [ ! -s "$PGDATA/PG_VERSION" ]; then
    password_file="/tmp/carbonlab-postgres-password"
    umask 077
    printf '%s\n' "$POSTGRES_PASSWORD" > "$password_file"
    chown postgres:postgres "$password_file"

    su-exec postgres initdb \
        --pgdata="$PGDATA" \
        --username="$POSTGRES_USER" \
        --pwfile="$password_file" \
        --auth-local=trust \
        --auth-host=scram-sha-256
    rm "$password_file"

    printf "password_encryption = 'scram-sha-256'\n" >> "$PGDATA/postgresql.conf"
    printf "host all all 0.0.0.0/0 scram-sha-256\n" >> "$PGDATA/pg_hba.conf"
    printf "host all all ::/0 scram-sha-256\n" >> "$PGDATA/pg_hba.conf"

    su-exec postgres pg_ctl \
        --pgdata="$PGDATA" \
        --options="-c listen_addresses='' -c unix_socket_directories=/tmp" \
        --wait start

    if [ "$POSTGRES_DB" != "postgres" ]; then
        su-exec postgres createdb \
            --host=/tmp \
            --username="$POSTGRES_USER" \
            --owner="$POSTGRES_USER" \
            "$POSTGRES_DB"
    fi

    su-exec postgres pg_ctl --pgdata="$PGDATA" --mode=fast --wait stop
fi

if [ "$#" -eq 0 ] || [ "$1" = "postgres" ]; then
    exec su-exec postgres postgres \
        --data-directory="$PGDATA" \
        -c listen_addresses='*' \
        -c unix_socket_directories=/run/postgresql
fi

exec "$@"
