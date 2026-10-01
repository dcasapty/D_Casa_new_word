#!/usr/bin/env bash
# Ensayo de "muerte del contenedor": carga continua, kill -9 de PostgreSQL (sin gracia),
# borrado del directorio de datos (disco efímero), restauración desde S3 y verificación.
# Uso: 03_ensayo_muerte.sh SEGUNDOS_DE_CARGA [INTERVALO_S]
set -uo pipefail; source "$(dirname "$0")/env.sh"; D="$(cd "$(dirname "$0")" && pwd)"
N=${1:-120}; INT=${2:-1}; RUN=$(date +%Y%m%d-%H%M%S); LOG=$R3/carga-$RUN.log; OUT=$D/salidas/muerte-$RUN.txt
mkdir -p $D/salidas; : > $LOG
ops0=$(wc -l < $R3/moto.log)
$R3/venv/bin/python $D/carga.py $PGPORT_P $LOG $INT & WPID=$!
sleep $N
# --- muerte sin gracia: SIGKILL al postmaster y a todos sus hijos (incluido el archivador) ---
PM=$(head -1 $PGDATA_P/postmaster.pid); KIDS=$(pgrep -P $PM | tr '\n' ' ')
kill -9 $PM $KIDS; T_KILL=$(date +%s.%N); kill $WPID 2>/dev/null; wait $WPID 2>/dev/null
rm -rf $PGDATA_P                                   # el disco efímero desaparece
ops1=$(wc -l < $R3/moto.log)
# --- restauración de extremo a extremo ---
T0=$(date +%s.%N)
mkdir -p $PGDATA_P; chmod 700 $PGDATA_P; chown postgres: $PGDATA_P
asp "pgbackrest --config=$PGBR_CONF --stanza=$STANZA --log-level-console=warn restore"
T1=$(date +%s.%N)
asp "$PGBIN/pg_ctl -D $PGDATA_P -l $R3/log/pg5440.log -w -t 600 start" >/dev/null
until [[ "$(psqlp 'select pg_is_in_recovery()' 2>/dev/null)" == "f" ]]; do sleep 0.2; done
T2=$(date +%s.%N)
ops2=$(wc -l < $R3/moto.log)
V=$(asp "$PGBIN/psql -X -h 127.0.0.1 -p $PGPORT_P -U postgres -d dcasa -tA -F'|' -f $D/verificar.sql")
MAXR=$(echo "$V" | awk -F'|' '$1=="asientos_max_id"{print $2}')
LAST=$(tail -1 $LOG); LAST_ID=${LAST%%,*}; LAST_TS=${LAST##*,}
TS_R=$(awk -F, -v m=$MAXR '$1==m{print $2}' $LOG); TS_R=${TS_R:-$(head -1 $LOG | cut -d, -f2)}
{
echo "ensayo=$RUN carga_s=$N intervalo_s=$INT"
echo "commits_confirmados=$LAST_ID restaurados=$MAXR perdidos=$((LAST_ID-MAXR))"
printf "RPO_s=%.1f (ultimo commit confirmado - ultimo commit restaurado)\n" "$(echo "$LAST_TS - $TS_R" | bc)"
printf "kill_a_ultimo_commit_s=%.1f\n" "$(echo "$T_KILL - $LAST_TS" | bc)"
printf "t_restore_pgbackrest_s=%.1f t_replay_y_promocion_s=%.1f RTO_total_s=%.1f\n" \
  "$(echo "$T1-$T0"|bc)" "$(echo "$T2-$T1"|bc)" "$(echo "$T2-$T0"|bc)"
echo "ops_s3_durante_carga=$((ops1-ops0)) ops_s3_restauracion=$((ops2-ops1))"
sed -n "$((ops0+1)),${ops1}p" $R3/moto.log | grep -oE '"[A-Z]+ ' | sort | uniq -c | tr '\n' ' '; echo
echo "--- verificacion"; echo "$V"
echo "--- referencia (5432)"; cat $R3/referencia_5432.txt
} | tee $OUT
