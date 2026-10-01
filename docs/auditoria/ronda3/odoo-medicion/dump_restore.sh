#!/usr/bin/env bash
# Tiempo y tamaño de pg_dump (-Fc gzip por defecto, zstd, lz4, sin compresión) desde 5432
# y de pg_restore hacia el clúster propio 5441. 3 repeticiones.
set -euo pipefail
SRC_DB="${SRC_DB:-r3_med_base}"; OUT="${OUT:-/tmp/r3_med_dumps}"; mkdir -p "$OUT"
export PGPASSWORD=odoo
t() { local s=$(date +%s.%N); "$@" >/dev/null; echo "$(date +%s.%N) - $s" | bc; }
for rep in 1 2 3; do
  for c in gzip zstd lz4 none; do
    f="$OUT/$SRC_DB.$c.dump"
    secs=$(t pg_dump -h localhost -p 5432 -U odoo -Fc -Z "$c" -f "$f" "$SRC_DB")
    echo "dump rep=$rep comp=$c secs=$secs bytes=$(stat -c %s "$f")"
  done
  for c in gzip zstd; do
    f="$OUT/$SRC_DB.$c.dump"; tgt="r3_med_rest"
    dropdb --if-exists -h localhost -p 5441 -U odoo "$tgt"; createdb -h localhost -p 5441 -U odoo "$tgt"
    secs=$(t pg_restore -h localhost -p 5441 -U odoo -d "$tgt" --no-owner "$f")
    echo "restore rep=$rep comp=$c jobs=1 secs=$secs"
    dropdb -h localhost -p 5441 -U odoo "$tgt"; createdb -h localhost -p 5441 -U odoo "$tgt"
    secs=$(t pg_restore -h localhost -p 5441 -U odoo -d "$tgt" --no-owner -j 4 "$f")
    echo "restore rep=$rep comp=$c jobs=4 secs=$secs"
  done
done
dropdb --if-exists -h localhost -p 5441 -U odoo r3_med_rest
