#!/usr/bin/env bash
# Compara el tamaño de los segmentos WAL forzados por archive_timeout en reposo (cron/minuto):
# fase 1 con wal_recycle=off + wal_init_zero=on; fase 2 con los valores por defecto (recycle=on,
# init_zero=off) después de una ráfaga de escritura que deja segmentos reciclados con datos viejos.
set -uo pipefail; source "$(dirname "$0")/env.sh"; D="$(cd "$(dirname "$0")" && pwd)"
MIN=${1:-15}
psqlp "ALTER SYSTEM SET wal_recycle=off"; psqlp "ALTER SYSTEM SET wal_init_zero=on"; psqlp "select pg_reload_conf()" >/dev/null
bash $D/06_reposo.sh $MIN cron 60
psqlp "ALTER SYSTEM SET wal_recycle=on"; psqlp "ALTER SYSTEM SET wal_init_zero=off"; psqlp "select pg_reload_conf()" >/dev/null
# ráfaga: ~200 MB de WAL, luego checkpoints para que esos segmentos se reciclen
psqlp "DROP TABLE IF EXISTS r3_rafaga; CREATE TABLE r3_rafaga AS SELECT g, md5(g::text)||md5((g*7)::text) t FROM generate_series(1,1500000) g" >/dev/null
psqlp "CHECKPOINT" >/dev/null; sleep 70; psqlp "CHECKPOINT" >/dev/null; psqlp "DROP TABLE r3_rafaga" >/dev/null; psqlp "CHECKPOINT" >/dev/null
bash $D/06_reposo.sh $MIN cron 60
psqlp "ALTER SYSTEM RESET wal_recycle"; psqlp "ALTER SYSTEM RESET wal_init_zero"; psqlp "select pg_reload_conf()" >/dev/null
