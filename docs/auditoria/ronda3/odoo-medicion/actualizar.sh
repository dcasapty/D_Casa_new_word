#!/usr/bin/env bash
# Tiempo de lo que hace docker/entrypoint.sh en cada deploy con versión nueva:
#   odoo -d DB -i MODS -u MODS --stop-after-init   (8 módulos de D'CASA)
# sobre copias de r3_med_base en el clúster principal 5432 (base de nadie más). 3 repeticiones.
# También mide el pico de RSS del proceso con /usr/bin/time -v.
set -euo pipefail
ROOT=/home/user/D_Casa_new_word
MODS=dcasa_base,dcasa_invoice,dcasa_socios,website_dcasa,dcasa_catalogo,dcasa_interfaz,dcasa_contabilidad,dcasa_brian
export PGPASSWORD=odoo
for rep in 1 2 3; do
  db=r3_med_upd
  dropdb --if-exists -h localhost -U odoo "$db"; createdb -h localhost -U odoo -T r3_med_base "$db"
  s=$(date +%s.%N)
  python3 /home/user/D_Casa_new_word/docs/auditoria/ronda3/odoo-medicion/cronometro.py python3 "$ROOT/vendor/odoo/odoo-bin" \
    --addons-path="$ROOT/vendor/odoo/addons,$ROOT/vendor/odoo/odoo/addons,$ROOT/addons" \
    --db_host=localhost --db_user=odoo --db_password=odoo -d "$db" --http-port=8179 \
    -i "$MODS" -u "$MODS" --stop-after-init --log-level=warn > /tmp/r3_med_upd_$rep.log 2>&1
  e=$(echo "$(date +%s.%N) - $s" | bc)
  rss=$(grep "Maximum resident" /tmp/r3_med_upd_$rep.log | awk '{print $NF}')
  cpu=$(grep -E "User time|System time" /tmp/r3_med_upd_$rep.log | awk '{s+=$NF} END {print s}')
  errs=$(grep -cE " (ERROR|CRITICAL) " /tmp/r3_med_upd_$rep.log || true)
  echo "update rep=$rep secs=$e cpu_s=$cpu max_rss_kB=$rss errores=$errs"
done
dropdb --if-exists -h localhost -U odoo r3_med_upd
