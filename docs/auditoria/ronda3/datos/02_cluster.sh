#!/usr/bin/env bash
# Clúster PostgreSQL 16 "efímero" en 5440 con archivado continuo de WAL a S3 (pgBackRest),
# carga la base real de prueba (pg_dump de dcasa_test) y hace el respaldo base.
# Variables: WAL_ZERO=1 (por defecto) usa wal_recycle=off + wal_init_zero=on (segmentos
# forzados por archive_timeout se comprimen casi a cero); WAL_ZERO=0 = valores por defecto.
set -euo pipefail; source "$(dirname "$0")/env.sh"
WAL_ZERO=${WAL_ZERO:-1}
mkdir -p $R3/log $R3/sock $R3/pgbr-log $R3/pgbr-lock $R3/pgbr-spool; chown -R postgres: $R3/log $R3/sock $R3/pgbr-*
cat > $PGBR_CONF <<CONF
[global]
repo1-type=s3
repo1-s3-endpoint=127.0.0.1
repo1-storage-port=$S3_PORT
repo1-storage-verify-tls=n
repo1-s3-uri-style=path
repo1-s3-bucket=$S3_BUCKET
repo1-s3-region=us-east-1
repo1-s3-key=x
repo1-s3-key-secret=x
repo1-path=/pgbackrest
repo1-retention-full=2
repo1-cipher-type=aes-256-cbc
repo1-cipher-pass=prueba-local-no-usar-en-produccion
compress-type=zst
compress-level=3
process-max=2
start-fast=y
log-path=$R3/pgbr-log
lock-path=$R3/pgbr-lock
spool-path=$R3/pgbr-spool
log-level-console=info
log-level-file=detail

[$STANZA]
pg1-path=$PGDATA_P
pg1-port=$PGPORT_P
pg1-socket-path=$R3/sock
CONF
chown postgres: $PGBR_CONF
rm -rf $PGDATA_P; mkdir -p $PGDATA_P; chown postgres: $PGDATA_P
asp "$PGBIN/initdb -D $PGDATA_P --data-checksums -E UTF8 --locale=C.UTF-8 -U postgres >/dev/null"
cat >> $PGDATA_P/postgresql.conf <<CONF
listen_addresses = '127.0.0.1'
port = $PGPORT_P
unix_socket_directories = '$R3/sock'
shared_buffers = 256MB
wal_level = replica
archive_mode = on
archive_command = 'pgbackrest --config=$PGBR_CONF --stanza=$STANZA archive-push %p'
archive_timeout = 60
max_wal_size = 1GB
log_checkpoints = on
CONF
if [[ $WAL_ZERO == 1 ]]; then printf "wal_recycle = off\nwal_init_zero = on\n" >> $PGDATA_P/postgresql.conf; fi
asp "$PGBIN/pg_ctl -D $PGDATA_P -l $R3/log/pg5440.log -w start"
asp "$PGBIN/createdb -h 127.0.0.1 -p $PGPORT_P -U postgres dcasa"
t0=$(date +%s.%N)
asp "$PGBIN/pg_restore -h 127.0.0.1 -p $PGPORT_P -U postgres -d dcasa --no-owner --no-acl -j 2 $R3/dcasa_test.dump" || true
echo "pg_restore del volcado: $(echo "$(date +%s.%N) - $t0" | bc) s"
psqlp "CREATE TABLE IF NOT EXISTS r3_asiento(id bigint PRIMARY KEY, ts timestamptz NOT NULL DEFAULT clock_timestamp(), monto numeric(12,2) NOT NULL, glosa text NOT NULL)"
asp "pgbackrest --config=$PGBR_CONF --stanza=$STANZA stanza-create"
asp "pgbackrest --config=$PGBR_CONF --stanza=$STANZA check"
t0=$(date +%s.%N)
asp "pgbackrest --config=$PGBR_CONF --stanza=$STANZA --type=full backup"
echo "respaldo base completo: $(echo "$(date +%s.%N) - $t0" | bc) s"
asp "pgbackrest --config=$PGBR_CONF --stanza=$STANZA info"
