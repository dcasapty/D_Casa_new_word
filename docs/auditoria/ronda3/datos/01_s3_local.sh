#!/usr/bin/env bash
# S3 local compatible: moto (HTTP, puerto S3_PORT+1) detrás de stunnel (TLS, puerto S3_PORT).
# pgBackRest exige https; el servidor TLS de werkzeug corta sin close_notify (OpenSSL 3 da
# "unexpected eof"), por eso se termina TLS con stunnel. MinIO (dl.min.io) está bloqueado por el proxy.
set -euo pipefail; source "$(dirname "$0")/env.sh"
mkdir -p $R3; cd $R3
[[ -x venv/bin/moto_server ]] || { python3 -m venv venv; venv/bin/pip install -q "moto[server]" boto3; }
command -v stunnel4 >/dev/null || apt-get install -y -q stunnel4
[[ -f s3.crt ]] || openssl req -x509 -newkey rsa:2048 -nodes -keyout s3.key -out s3.crt -days 30 \
   -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1,DNS:localhost"
# El registro de moto (una línea por petición HTTP) sirve para contar PUT/GET/HEAD/LIST.
nohup venv/bin/moto_server -H 127.0.0.1 -p $((S3_PORT+1)) > moto.log 2>&1 &
cat > stunnel.conf <<CONF
foreground = no
pid = $R3/stunnel.pid
output = $R3/stunnel.log
[s3]
accept = 127.0.0.1:$S3_PORT
connect = 127.0.0.1:$((S3_PORT+1))
cert = $R3/s3.crt
key = $R3/s3.key
CONF
stunnel4 stunnel.conf
sleep 3
AWS_ACCESS_KEY_ID=x AWS_SECRET_ACCESS_KEY=x venv/bin/python -W ignore -c "
import boto3; s=boto3.client('s3',endpoint_url='https://127.0.0.1:$S3_PORT',verify=False,region_name='us-east-1')
s.create_bucket(Bucket='$S3_BUCKET'); print('bucket listo')"
