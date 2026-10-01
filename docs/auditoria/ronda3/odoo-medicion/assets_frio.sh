#!/usr/bin/env bash
# Costo de regenerar los bundles JS/CSS (lo que pasa tras cada `-u`/deploy): borra los adjuntos
# /web/assets/% de una copia (5432) y mide la primera visita a / y al backend con sus bundles. 3 rep.
set -euo pipefail
D=$(cd "$(dirname "$0")" && pwd)
export PGPASSWORD=odoo
for rep in 1 2 3; do
  dropdb --if-exists -h localhost -U odoo r3_med_assets; createdb -h localhost -U odoo -T r3_med_base r3_med_assets
  psql -h localhost -U odoo -d r3_med_assets -Atqc "delete from ir_attachment where url like '/web/assets/%'"
  PID=$(DB=r3_med_assets PGPORT=5432 TAG=assets_$rep "$D/odoo_run.sh" 8178 0 0 16)
  python3 "$D/medir.py" esperar http://127.0.0.1:8178/web/login 300 >/dev/null
  c0=$(python3 -c "import sys;sys.path.insert(0,'$D');import medir;print(medir.cpu(medir.hijos($PID)))")
  s=$(date +%s.%N)
  DB=r3_med_assets python3 "$D/medir.py" calentar http://127.0.0.1:8178 > /tmp/r3_med_assets_$rep.txt
  e=$(echo "$(date +%s.%N) - $s" | bc)
  c1=$(python3 -c "import sys;sys.path.insert(0,'$D');import medir;print(medir.cpu(medir.hijos($PID)))")
  echo "rep=$rep calentar_con_bundles_en_frio_s=$e cpu_s=$(echo "$c1 - $c0" | bc) $(python3 "$D/medir.py" mem $PID)"
  grep -E "^/ |asset|/odoo " /tmp/r3_med_assets_$rep.txt | awk '{print "   ", $0}'
  kill $PID; sleep 3
done
dropdb -h localhost -U odoo r3_med_assets
