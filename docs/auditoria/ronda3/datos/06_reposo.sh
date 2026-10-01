#!/usr/bin/env bash
# Mide el archivado en "reposo de Odoo": un UPDATE de ir_cron por minuto (como el hilo de cron)
# o carga de ventas (1 inserción cada INT s). Cuenta peticiones S3 por tipo y bytes de WAL subidos.
# Uso: 06_reposo.sh MINUTOS MODO INT   (MODO: cron | asiento)
set -uo pipefail; source "$(dirname "$0")/env.sh"; D="$(cd "$(dirname "$0")" && pwd)"
MIN=${1:-15}; MODO=${2:-cron}; INT=${3:-60}; RUN=$(date +%Y%m%d-%H%M%S); OUT=$D/salidas/reposo-$MODO-$RUN.txt
W0=$(psqlp "select archived_count from pg_stat_archiver"); ops0=$(wc -l < $R3/moto.log); T0=$(date +%s)
$R3/venv/bin/python $D/carga.py $PGPORT_P $R3/carga-$RUN.log $INT $MODO & WPID=$!
sleep $((MIN*60)); kill $WPID; wait $WPID 2>/dev/null
sleep 5; T1=$(date +%s); ops1=$(wc -l < $R3/moto.log); W1=$(psqlp "select archived_count from pg_stat_archiver")
{
echo "modo=$MODO minutos=$MIN intervalo_s=$INT wal_recycle=$(psqlp 'show wal_recycle') wal_init_zero=$(psqlp 'show wal_init_zero')"
echo "segmentos_archivados=$((W1-W0)) por_hora=$(( (W1-W0)*3600/(T1-T0) ))"
echo "peticiones_s3=$((ops1-ops0)) por_hora=$(( (ops1-ops0)*3600/(T1-T0) ))"
sed -n "$((ops0+1)),${ops1}p" $R3/moto.log | grep -oE '"[A-Z]+ [^ ]+' | awk '{m=$1; sub(/"/,"",m); k="obj"; if($2 ~ /list-type/) k="LIST"; else if ($2 ~ /uploads/) k="MULTIPART"; print m"_"k}' | sort | uniq -c | tr '\n' ' '; echo
$R3/venv/bin/python $D/s3_inventario.py $T0 $T1
} | tee $OUT
