#!/usr/bin/env bash
# Red de seguridad mínima: pg_dump -Fc diario -> bucket aparte -> prueba automática de restauración
# en un clúster desechable (5444) -> comparación de checksums con la base viva. Falla con código != 0.
set -uo pipefail; source "$(dirname "$0")/env.sh"; D="$(cd "$(dirname "$0")" && pwd)"
RUN=$(date +%Y%m%d-%H%M%S); OUT=$D/salidas/red-$RUN.txt; DUMP=$R3/dump-$RUN.dump; BK=dcasa-dump
exec > >(tee $OUT) 2>&1
S3="$R3/venv/bin/python -W ignore -c"
CLI="import boto3,sys; s=boto3.client('s3',endpoint_url='https://127.0.0.1:$S3_PORT',verify=False,region_name='us-east-1',aws_access_key_id='x',aws_secret_access_key='x')"
$S3 "$CLI; s.create_bucket(Bucket='$BK')" 2>/dev/null
t0=$(date +%s.%N); asp "$PGBIN/pg_dump -h 127.0.0.1 -p $PGPORT_P -U postgres -Fc -Z zstd:3 -f /tmp/dump.tmp dcasa" && mv /tmp/dump.tmp $DUMP
t1=$(date +%s.%N); $S3 "$CLI; s.upload_file('$DUMP','$BK','diario/$RUN.dump')"; t2=$(date +%s.%N)
echo "pg_dump zstd: $(du -m $DUMP | cut -f1) MB en $(echo "$t1-$t0"|bc) s; subida $(echo "$t2-$t1"|bc) s"
# --- prueba de restauración en clúster desechable ---
P=5444; DD=$R3/pg5444; rm -rf $DD; mkdir -p $DD; chown postgres: $DD
asp "$PGBIN/initdb -D $DD -U postgres >/dev/null"; printf "port=$P\nlisten_addresses='127.0.0.1'\nunix_socket_directories='$R3/sock'\n" >> $DD/postgresql.conf
asp "$PGBIN/pg_ctl -D $DD -l $R3/log/pg5444.log -w start" >/dev/null
t3=$(date +%s.%N); rm -f $DUMP; $S3 "$CLI; s.download_file('$BK','diario/$RUN.dump','$R3/bajado.dump')"; chmod 644 $R3/bajado.dump
asp "$PGBIN/createdb -h 127.0.0.1 -p $P -U postgres dcasa"
asp "$PGBIN/pg_restore -h 127.0.0.1 -p $P -U postgres -d dcasa -j 2 $R3/bajado.dump"; t4=$(date +%s.%N)
echo "descarga + pg_restore: $(echo "$t4-$t3"|bc) s"
a=$(asp "$PGBIN/psql -X -h 127.0.0.1 -p $PGPORT_P -U postgres -d dcasa -tA -F'|' -f $D/verificar.sql" | grep -v asiento_ultimo)
b=$(asp "$PGBIN/psql -X -h 127.0.0.1 -p $P -U postgres -d dcasa -tA -F'|' -f $D/verificar.sql" | grep -v asiento_ultimo)
asp "$PGBIN/pg_ctl -D $DD -m fast stop" >/dev/null; rm -rf $DD $R3/bajado.dump
if [[ "$a" == "$b" ]]; then echo "PRUEBA DE RESTAURACION: OK (checksums iguales)"; else echo "PRUEBA DE RESTAURACION: FALLA"; diff <(echo "$a") <(echo "$b"); exit 1; fi
