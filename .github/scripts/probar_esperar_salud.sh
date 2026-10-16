#!/usr/bin/env bash
# Prueba .github/scripts/esperar_salud.sh contra un sitio falso (un servidor local que contesta lo que
# cada caso le pide), sin Cloudflare. Lo que se prueba es el incidente del 2026-10-16 (#97): el despliegue
# dijo «sano» porque Odoo contestaba 200, aunque respondía otra imagen o la base no estaba actualizada.
set -euo pipefail

cd "$(dirname "$0")"
SCRIPT="$PWD/esperar_salud.sh"
VERSION=0123456789abcdef0123456789abcdef01234567
tmp="$(mktemp -d)"
servidor_pid=""
trap '[[ -z "$servidor_pid" ]] || kill "$servidor_pid" 2>/dev/null || true; rm -rf "$tmp"' EXIT

cat >"$tmp/sitio_falso.py" <<'PY'
"""Sitio falso: /__edge/health contesta, en orden, las respuestas de respuestas.json (la última se repite)."""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

carpeta = sys.argv[1]


class Sitio(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/__edge/health':
            self.send_response(200)
            self.end_headers()
            return
        with open(f'{carpeta}/respuestas.json', encoding='utf-8') as archivo:
            respuestas = json.load(archivo)
        with open(f'{carpeta}/vueltas', 'a+', encoding='utf-8') as archivo:
            archivo.seek(0)
            vuelta = len(archivo.read())
            archivo.write('.')
        estado, detalle = respuestas[min(vuelta, len(respuestas) - 1)]
        cuerpo = json.dumps({'borde': 'ok', 'odoo': 'ok', 'detalle': json.dumps(detalle)}).encode()
        self.send_response(estado)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *args):
        pass


servidor = HTTPServer(('127.0.0.1', 0), Sitio)
with open(f'{carpeta}/puerto', 'w', encoding='utf-8') as archivo:
    archivo.write(str(servidor.server_port))
servidor.serve_forever()
PY

python3 "$tmp/sitio_falso.py" "$tmp" &
servidor_pid=$!
for _ in $(seq 1 50); do [[ -s "$tmp/puerto" ]] && break; sleep 0.1; done
URL="http://127.0.0.1:$(cat "$tmp/puerto")"

fallos=0
# caso <descripción> <código de salida esperado> <respuestas JSON> [CONFIRMAR_S]
caso() {
  printf '%s' "$3" >"$tmp/respuestas.json"
  rm -f "$tmp/vueltas"
  local rc=0
  URL_SITIO="$URL" APP_VERSION="$VERSION" ESPERA_SEGUNDOS=2 PAUSA_S=0.2 CONFIRMAR_S="${4:-0}" \
    "$SCRIPT" >"$tmp/salida" 2>&1 || rc=$?
  if [[ "$rc" == "$2" ]]; then
    echo "ok   $1"
  else
    echo "FALLA $1 (salida $rc, esperaba $2)"
    sed 's/^/  | /' "$tmp/salida"
    fallos=$((fallos + 1))
  fi
}

NUEVA='{"ok": true, "version": "0123456789ab", "base_al_dia": true}'
caso "la versión nueva con la base al día está sana" 0 "[[200, $NUEVA]]"
caso "arranca (503) y luego queda sana: espera y pasa" 0 "[[503, {}], [503, {}], [200, $NUEVA]]"
caso "un 200 de una imagen sin versión (la anterior) NO es sano" 1 '[[200, {"ok": true}]]'
caso "un 200 de otra versión NO es sano" 1 '[[200, {"ok": true, "version": "fedcba987654", "base_al_dia": true}]]'
caso "la versión nueva con la base sin actualizar NO es sana (lo que pasó el 2026-10-16)" 1 \
  '[[200, {"ok": true, "version": "0123456789ab", "base_al_dia": false}]]'
caso "primero responde la anterior y después la nueva: espera y pasa" 0 \
  "[[200, {\"ok\": true}], [200, {\"ok\": true}], [200, $NUEVA]]"
caso "sana al principio pero a la confirmación responde la anterior: falla" 1 \
  "[[200, $NUEVA], [200, {\"ok\": true}]]" 1
caso "sana al principio y sigue sana a la confirmación: pasa" 0 "[[200, $NUEVA]]" 1

rc=0
URL_SITIO="$URL" "$SCRIPT" >"$tmp/salida" 2>&1 || rc=$?
if [[ "$rc" != 0 ]] && grep -q 'Falta APP_VERSION' "$tmp/salida"; then
  echo "ok   sin APP_VERSION no adivina: se niega"
else
  echo "FALLA sin APP_VERSION debería negarse"
  fallos=$((fallos + 1))
fi

if ((fallos)); then
  echo "$fallos prueba(s) fallaron"
  exit 1
fi
echo "Todas las pruebas de esperar_salud.sh pasaron."
