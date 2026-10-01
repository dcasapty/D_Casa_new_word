#!/usr/bin/env bash
# S3 local para CI (en lugar de R2): moto por HTTP detrás de stunnel con TLS autofirmado.
# pgBackRest exige https y el TLS de werkzeug corta sin close_notify (OpenSSL 3 da
# «unexpected eof»), por eso TLS lo termina stunnel (mismo montaje que
# docs/auditoria/ronda3/datos/01_s3_local.sh, donde se midió el RPO/RTO).
#
# Uso: s3_local.sh DIRECTORIO PUERTO_TLS BUCKET
#   Requiere: python3 con `moto[server]` y `boto3` instalados, y stunnel4.
#   Queda escuchando en https://127.0.0.1:PUERTO_TLS con el bucket creado
#   (credenciales cualesquiera: moto no las valida).
set -euo pipefail

dir="${1:?directorio}"
puerto="${2:?puerto TLS}"
bucket="${3:?bucket}"
mkdir -p "$dir"

openssl req -x509 -newkey rsa:2048 -nodes -keyout "$dir/s3.key" -out "$dir/s3.crt" -days 2 \
  -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" 2>/dev/null

nohup moto_server -H 127.0.0.1 -p "$((puerto + 1))" > "$dir/moto.log" 2>&1 &

cat > "$dir/stunnel.conf" <<CONF
foreground = no
pid = $dir/stunnel.pid
output = $dir/stunnel.log
[s3]
accept = 127.0.0.1:$puerto
connect = 127.0.0.1:$((puerto + 1))
cert = $dir/s3.crt
key = $dir/s3.key
CONF
stunnel4 "$dir/stunnel.conf"

for _ in $(seq 1 30); do
  if curl -ksS -o /dev/null "https://127.0.0.1:$puerto/"; then break; fi
  sleep 1
done

AWS_ACCESS_KEY_ID=ci AWS_SECRET_ACCESS_KEY=ci python3 -W ignore - "$puerto" "$bucket" <<'PY'
import sys
import boto3
puerto, bucket = sys.argv[1], sys.argv[2]
s3 = boto3.client("s3", endpoint_url=f"https://127.0.0.1:{puerto}", verify=False, region_name="us-east-1")
s3.create_bucket(Bucket=bucket)
print(f"S3 local listo: https://127.0.0.1:{puerto}/{bucket}")
PY
