#!/usr/bin/env bash
# Clúster PostgreSQL 16 PROPIO de la medición (no toca el principal 5432).
#   pg_propio.sh init                -> initdb en /tmp/r3_med_pgdata, rol odoo/odoo
#   pg_propio.sh start <shared_buffers> [extra -c ...]  -> arranca en 5441 con parámetros mínimos
#   pg_propio.sh stop
set -euo pipefail
PGBIN=/usr/lib/postgresql/16/bin
DATA=/tmp/r3_med_pgdata
PORT=5441
as_pg() { su postgres -s /bin/bash -c "$*"; }
case "$1" in
  init)
    mkdir -p "$DATA" && chown postgres:postgres "$DATA"
    as_pg "$PGBIN/initdb -D $DATA -U postgres --auth=trust -E UTF8 --locale=C.UTF-8 >/dev/null"
    ;;
  start)
    SB="${2:-128MB}"; shift 2 || true
    # Parámetros "mínimos razonables" para una sola instancia de Odoo pequeña.
    as_pg "$PGBIN/pg_ctl -D $DATA -l $DATA/server.log -w start -o \"-p $PORT -k /tmp \
      -c listen_addresses=localhost -c shared_buffers=$SB -c max_connections=40 \
      -c work_mem=4MB -c maintenance_work_mem=64MB -c effective_cache_size=256MB \
      -c wal_buffers=4MB -c shared_preload_libraries=pg_stat_statements \
      -c pg_stat_statements.track=all -c track_io_timing=on $*\""
    psql -h localhost -p $PORT -U postgres -d postgres -Atc \
      "DO \$\$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='odoo') THEN CREATE ROLE odoo LOGIN SUPERUSER PASSWORD 'odoo'; END IF; END\$\$" ;;
  stop)
    as_pg "$PGBIN/pg_ctl -D $DATA -m fast -w stop" ;;
esac
