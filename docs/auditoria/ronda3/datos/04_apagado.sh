#!/usr/bin/env bash
# Ruta "apagado ordenado" (lo que haría el manejador de SIGTERM del contenedor) frente al
# apagado ingenuo (pg_ctl stop sin forzar cambio de segmento). Después se borra el disco,
# se restaura desde S3 y se cuentan los commits perdidos.
# Uso: 04_apagado.sh MODO SEGUNDOS_DE_CARGA   (MODO: ordenado | ingenuo)
set -uo pipefail; source "$(dirname "$0")/env.sh"; D="$(cd "$(dirname "$0")" && pwd)"
MODO=${1:-ordenado}; N=${2:-90}; RUN=$(date +%Y%m%d-%H%M%S); LOG=$R3/carga-$RUN.log; OUT=$D/salidas/apagado-$MODO-$RUN.txt
mkdir -p $D/salidas; : > $LOG
$R3/venv/bin/python $D/carga.py $PGPORT_P $LOG 1 & WPID=$!
sleep $N
kill $WPID; wait $WPID 2>/dev/null          # 1) Odoo deja de aceptar escrituras
T0=$(date +%s.%N)
if [[ $MODO == ordenado ]]; then
  psqlp "CHECKPOINT" >/dev/null             # 2) checkpoint: acorta el apagado
  SEG=$(psqlp "SELECT pg_walfile_name(pg_switch_wal())")   # 3) cierra el segmento en curso
  until [[ "$(psqlp "SELECT last_archived_wal >= '$SEG' FROM pg_stat_archiver")" == "t" ]]; do sleep 0.1; done
  T1=$(date +%s.%N)                          #    ... y espera a que el archivador lo suba
fi
asp "$PGBIN/pg_ctl -D $PGDATA_P -m fast -w stop" >/dev/null   # 4) parada rápida
T2=$(date +%s.%N); T1=${T1:-$T2}
rm -rf $PGDATA_P
T3=$(date +%s.%N)
mkdir -p $PGDATA_P; chmod 700 $PGDATA_P; chown postgres: $PGDATA_P
asp "pgbackrest --config=$PGBR_CONF --stanza=$STANZA --log-level-console=warn restore"
asp "$PGBIN/pg_ctl -D $PGDATA_P -l $R3/log/pg5440.log -w -t 600 start" >/dev/null
until [[ "$(psqlp 'select pg_is_in_recovery()' 2>/dev/null)" == "f" ]]; do sleep 0.2; done
T4=$(date +%s.%N)
MAXR=$(psqlp "SELECT coalesce(max(id),0) FROM r3_asiento"); LAST_ID=$(tail -1 $LOG | cut -d, -f1)
{
echo "apagado=$MODO ensayo=$RUN carga_s=$N"
printf "t_checkpoint_switch_push_s=%.2f t_pg_ctl_stop_s=%.2f t_apagado_total_s=%.2f\n" "$(echo "$T1-$T0"|bc)" "$(echo "$T2-$T1"|bc)" "$(echo "$T2-$T0"|bc)"
echo "commits_confirmados=$LAST_ID restaurados=$MAXR perdidos=$((LAST_ID-MAXR))"
printf "RTO_total_s=%.1f\n" "$(echo "$T4-$T3"|bc)"
} | tee $OUT
