#!/usr/bin/env bash
# Tamaño de la base: total, top 10 tablas, ir_attachment y estimación sin adjuntos.
# Uso: tamano_base.sh [db] [port]
set -euo pipefail
DB="${1:-r3_med_base}"; PORT="${2:-5432}"
export PGPASSWORD=odoo
q() { psql -h localhost -p "$PORT" -U odoo -d "$DB" -P pager=off -c "$1"; }
q "select pg_size_pretty(pg_database_size(current_database())) total, pg_database_size(current_database()) bytes"
q "select relname, pg_size_pretty(pg_total_relation_size(c.oid)) total, pg_size_pretty(pg_relation_size(c.oid)) heap,
          pg_size_pretty(pg_total_relation_size(c.oid)-pg_relation_size(c.oid)-coalesce(pg_total_relation_size(reltoastrelid),0)) idx,
          pg_size_pretty(coalesce(pg_total_relation_size(reltoastrelid),0)) toast
     from pg_class c join pg_namespace n on n.oid=c.relnamespace
    where n.nspname='public' and relkind='r' order by pg_total_relation_size(c.oid) desc limit 10"
q "select count(*) n, pg_size_pretty(sum(file_size)) file_size,
          pg_size_pretty(sum(octet_length(db_datas))) db_datas,
          sum(octet_length(db_datas)) db_datas_bytes
     from ir_attachment"
q "select coalesce(res_model,'(sin modelo)') res_model, mimetype, count(*), pg_size_pretty(sum(octet_length(db_datas))) bytes
     from ir_attachment group by 1,2 order by sum(octet_length(db_datas)) desc nulls last limit 12"
q "select pg_size_pretty(pg_total_relation_size('ir_attachment')) ir_attachment_total,
          pg_size_pretty(pg_database_size(current_database()) - pg_total_relation_size('ir_attachment')) resto_sin_ir_attachment"
