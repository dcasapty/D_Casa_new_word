#!/usr/bin/env bash
# Espera a que el sitio recién desplegado esté sano CON LA VERSIÓN NUEVA y la base al día.
#
# Usa GET ${URL_SITIO}/__edge/health (edge/CONTRATO_CONTENEDOR.md §2): 200 solo si Odoo y la
# base responden (/dcasa/salud); 503 mientras arranca (restauración desde R2 + `odoo -u`).
# Ese endpoint no despierta el contenedor, así que cada vuelta también visita una página que SIEMPRE
# llega a Odoo (/web/login; una visita sí lo arranca y mientras tanto responde el 503 amable). La
# portada no sirve para esto: sale de la copia guardada en el borde (válida 1 hora) y no despierta
# nada; así falló el despliegue 95 (el contenedor quedó «stopped» los 20 minutos de espera).
#
# «Sano» no es «Odoo contesta» (incidente del 2026-10-16, #97: el despliegue dijo sano y producción
# corría otra imagen o la base sin actualizar). El `detalle` (lo que contesta /dcasa/salud) trae
# `version` (commit de la imagen que responde) y `base_al_dia` (la base se actualizó con el código de
# esa imagen). Se exige que `version` sea APP_VERSION y `base_al_dia` sea true; un 200 de la
# instancia anterior (o de una imagen sin esos datos) no cuenta. Y se vuelve a comprobar a los
# CONFIRMAR_S segundos: si para entonces responde otra versión (Cloudflare volvió a la imagen
# anterior), el despliegue falla en vez de quedar en verde.
#
# Entradas: URL_SITIO, APP_VERSION (SHA de 40), ESPERA_MINUTOS (por defecto 20), CONFIRMAR_S (300).
# Para las pruebas (probar_esperar_salud.sh): ESPERA_SEGUNDOS y PAUSA_S.
set -euo pipefail

: "${URL_SITIO:?}"
: "${APP_VERSION:?Falta APP_VERSION: sin ella no sé qué versión esperar}"
minutos="${ESPERA_MINUTOS:-20}"
espera_s="${ESPERA_SEGUNDOS:-$((minutos * 60))}"
pausa_s="${PAUSA_S:-15}"
confirmar_s="${CONFIRMAR_S:-300}"
version_esperada="${APP_VERSION:0:12}"
cuerpo="$(mktemp)"
trap 'rm -f "$cuerpo"' EXIT

salud() {
  curl -sS --max-time 20 -o /dev/null "${URL_SITIO}/web/login" 2>/dev/null || true
  : >"$cuerpo"
  curl -sS --max-time 20 -o "$cuerpo" -w '%{http_code}' "${URL_SITIO}/__edge/health" 2>/dev/null || true
}

# «version al_dia» del detalle de /__edge/health («-» si no viene: imagen anterior a este control).
leer_detalle() {
  python3 - "$cuerpo" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding='utf-8') as archivo:
        detalle = json.loads(json.load(archivo).get('detalle') or '{}')
except (ValueError, OSError, AttributeError):
    detalle = {}
if not isinstance(detalle, dict):
    detalle = {}
al_dia = {True: 'si', False: 'no'}.get(detalle.get('base_al_dia'), '-')
print(detalle.get('version') or '-', al_dia)
PY
}

# 0 si responde la versión desplegada con la base al día; si no, explica qué responde.
version_nueva_y_al_dia() {
  local codigo version al_dia
  codigo="$(salud)"
  if [[ "$codigo" != "200" ]]; then
    echo "Todavía no (HTTP ${codigo:-sin respuesta}): $(head -c 1500 "$cuerpo" 2>/dev/null || true)"
    return 1
  fi
  read -r version al_dia <<<"$(leer_detalle)"
  if [[ "$version" != "$version_esperada" ]]; then
    echo "Responde la versión ${version} y espero ${version_esperada}: sigue la instancia anterior o Cloudflare aún no cambia la imagen."
    return 1
  fi
  if [[ "$al_dia" != "si" ]]; then
    echo "Responde la versión ${version}, pero la base no está al día con su código (base_al_dia=${al_dia})."
    return 1
  fi
  return 0
}

limite=$(($(date +%s) + espera_s))
while true; do
  if version_nueva_y_al_dia; then
    echo "El sitio está sano con la versión ${version_esperada} y la base al día:"
    cat "$cuerpo"
    echo
    break
  fi
  if (($(date +%s) >= limite)); then
    echo "::error::En ${espera_s} s ${URL_SITIO} no quedó sano con la versión ${version_esperada} y la base al día."
    echo "Mira los logs (docs/OPERACION.md → «Dónde ver los logs») y, si hace falta, vuelve atrás"
    echo "(docs/OPERACION.md → «Volver atrás un despliegue»)."
    exit 1
  fi
  sleep "$pausa_s"
done

if ((confirmar_s > 0)); then
  echo "Confirmo en ${confirmar_s} s que sigue la versión nueva (Cloudflare podría volver a la imagen anterior)."
  sleep "$confirmar_s"
  if ! version_nueva_y_al_dia; then
    echo "::error::A los ${confirmar_s} s ${URL_SITIO} ya no responde la versión ${version_esperada} con la base al día."
    echo "Cloudflare pudo volver a la imagen anterior: revisa los logs del contenedor antes de reintentar."
    exit 1
  fi
  echo "Confirmado: sigue la versión ${version_esperada} con la base al día."
fi
