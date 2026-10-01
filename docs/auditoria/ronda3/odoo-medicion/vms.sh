#!/usr/bin/env bash
# Memoria VIRTUAL (VmSize, lo que compara limit_memory_soft en Linux) vs RSS de Odoo en hilos bajo
# 50 peticiones concurrentes (5432, r3_med_base, db_maxconn 60). 3 repeticiones.
set -euo pipefail
D=$(cd "$(dirname "$0")" && pwd)
for rep in 1 2 3; do
  PID=$(DB=r3_med_base PGPORT=5432 TAG=vms_$rep "$D/odoo_run.sh" 8176 0 1 60)
  python3 "$D/medir.py" esperar http://127.0.0.1:8176/ 300 >/dev/null
  DB=r3_med_base python3 "$D/medir.py" calentar http://127.0.0.1:8176 >/dev/null
  echo "rep=$rep caliente: $(grep -E 'VmSize|VmRSS|Threads' /proc/$PID/status | tr -s ' \t' ' ' | paste -sd' ')"
  ( pico=0; while kill -0 $PID 2>/dev/null; do v=$(awk '/VmSize/{print $2}' /proc/$PID/status 2>/dev/null || echo 0); [ "${v:-0}" -gt $pico ] && pico=$v && echo $pico > /tmp/r3_med_vms_pico; sleep 0.2; done ) &
  MON=$!
  DB=r3_med_base python3 "$D/medir.py" carga http://127.0.0.1:8176 $PID 50 500 > /tmp/r3_med_vms_carga_$rep.json
  echo "rep=$rep tras 50 conc: $(grep -E 'VmSize|VmHWM|Threads' /proc/$PID/status | tr -s ' \t' ' ' | paste -sd' ') pico_VmSize_kB=$(cat /tmp/r3_med_vms_pico) errores=$(python3 -c "import json;print(json.load(open('/tmp/r3_med_vms_carga_$rep.json'))['errores'])")"
  kill $PID; wait $MON 2>/dev/null || true; sleep 2
done
