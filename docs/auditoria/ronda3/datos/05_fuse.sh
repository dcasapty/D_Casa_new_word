#!/usr/bin/env bash
# (C) ¿PostgreSQL con el directorio de datos sobre un montaje FUSE a S3 (como R2 por FUSE)?
# s3fs-fuse contra el S3 local; pgbench en FUSE (puerto 5442) frente a disco local (5443);
# después "muerte" (kill -9 + desmontar sin vaciar caché) y arranque desde el bucket.
set -uo pipefail; source "$(dirname "$0")/env.sh"; D="$(cd "$(dirname "$0")" && pwd)"
RUN=$(date +%Y%m%d-%H%M%S); OUT=$D/salidas/fuse-$RUN.txt; BK=dcasa-fuse-$RUN; MNT=$R3/fuse; CACHE=$R3/fuse-cache
exec > >(tee $OUT) 2>&1
AWS_ACCESS_KEY_ID=x AWS_SECRET_ACCESS_KEY=x $R3/venv/bin/python -W ignore -c "
import boto3; s=boto3.client('s3',endpoint_url='https://127.0.0.1:$S3_PORT',verify=False,region_name='us-east-1')
s.create_bucket(Bucket='$BK')" 2>/dev/null
echo "x:x" > $R3/s3fs.passwd; chmod 600 $R3/s3fs.passwd
mkdir -p $MNT $CACHE
PGUID=$(id -u postgres); PGGID=$(id -g postgres)
montar() { s3fs $BK $MNT -o url=https://127.0.0.1:$S3_PORT,use_path_request_style,no_check_certificate,ssl_verify_hostname=0,passwd_file=$R3/s3fs.passwd,allow_other,uid=$PGUID,gid=$PGGID,mp_umask=077,use_cache=$CACHE,endpoint=us-east-1; sleep 2; }
montar; mkdir -p $MNT/pg; chown postgres: $MNT/pg; chmod 700 $MNT/pg
banco() { # $1=datadir $2=puerto $3=etiqueta
  mkdir -p $1; chown postgres: $1; chmod 700 $1
  asp "$PGBIN/initdb -D $1 -U postgres >/dev/null 2>&1" || { echo "$3: initdb FALLA"; return 1; }
  printf "port = $2\nlisten_addresses='127.0.0.1'\nunix_socket_directories='$R3/sock'\n" >> $1/postgresql.conf
  t0=$(date +%s.%N)
  timeout 300 su postgres -s /bin/bash -c "$PGBIN/pg_ctl -D $1 -l $R3/log/pg$2.log -w -t 240 start" >/dev/null || { echo "$3: arranque FALLA"; tail -5 $R3/log/pg$2.log; return 1; }
  echo "$3: initdb+arranque OK ($(echo "$(date +%s.%N)-$t0"|bc) s de arranque)"
  timeout 300 su postgres -s /bin/bash -c "pgbench -h 127.0.0.1 -p $2 -U postgres -i -s 2 postgres" >/dev/null 2>&1 || echo "$3: pgbench -i FALLA"
  timeout 200 su postgres -s /bin/bash -c "pgbench -h 127.0.0.1 -p $2 -U postgres -c 2 -T 30 -N postgres" 2>/dev/null | grep -E "^tps|latency average" | sed "s/^/$3: /"
}
banco $R3/pg5443-local 5443 LOCAL
asp "$PGBIN/pg_ctl -D $R3/pg5443-local -m fast stop" >/dev/null; rm -rf $R3/pg5443-local
banco $MNT/pg/data 5442 FUSE
# --- muerte: kill -9 y desmontaje sin vaciar (la caché local del contenedor desaparece) ---
PM=$(head -1 $MNT/pg/data/postmaster.pid 2>/dev/null); [[ -n "$PM" ]] && kill -9 $PM $(pgrep -P $PM) 2>/dev/null
fusermount -uz $MNT; pkill -9 -x s3fs; rm -rf $CACHE; mkdir -p $CACHE; sleep 2
montar
rm -f $MNT/pg/data/postmaster.pid
timeout 300 su postgres -s /bin/bash -c "$PGBIN/pg_ctl -D $MNT/pg/data -l $R3/log/pg5442b.log -w -t 240 start" >/dev/null && {
  echo "FUSE tras muerte: arranca (esperado tras el ultimo pgbench: count=200000)"; asp "$PGBIN/psql -X -h 127.0.0.1 -p 5442 -U postgres -tAc 'select count(*) from pgbench_accounts; select sum(abalance) from pgbench_accounts'"
  asp "$PGBIN/pg_ctl -D $MNT/pg/data -m immediate stop" >/dev/null; } || { echo "FUSE tras muerte: NO arranca"; tail -8 $R3/log/pg5442b.log; }
fusermount -uz $MNT; pkill -x s3fs
grep -c "/$BK" $R3/moto.log | sed 's/^/peticiones S3 al bucket FUSE: /'
