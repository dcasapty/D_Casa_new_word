#!/usr/bin/env bash
# Espera a que el sitio recién desplegado esté sano.
#
# Usa GET ${URL_SITIO}/__edge/health (edge/CONTRATO_CONTENEDOR.md §2): 200 solo si Odoo y la
# base responden (/dcasa/salud); 503 mientras arranca (restauración desde R2 + `odoo -u`).
# Ese endpoint no despierta el contenedor, así que cada vuelta también visita la portada
# (una visita sí lo arranca; mientras tanto responde el 503 amable).
#
# Con max_instances = 1 el rollout para la instancia vieja y recién después arranca la nueva
# (CONTRATO §4): justo después de `wrangler deploy` un 200 puede venir todavía de la vieja.
# Si el Worker ya existía (WORKER_EXISTE=true), primero se espera a ver el corte (≠ 200,
# hasta 5 min) y luego el 200 de la nueva. Si el corte no se ve, se acepta con un aviso.
#
# Entradas: URL_SITIO, WORKER_EXISTE, ESPERA_MINUTOS (por defecto 20).
set -euo pipefail

: "${URL_SITIO:?}"
minutos="${ESPERA_MINUTOS:-20}"
limite=$(( $(date +%s) + minutos * 60 ))
cuerpo="$(mktemp)"
trap 'rm -f "$cuerpo"' EXIT

salud() {
  curl -sS --max-time 20 -o /dev/null "${URL_SITIO}/" 2>/dev/null || true
  curl -sS --max-time 20 -o "$cuerpo" -w '%{http_code}' "${URL_SITIO}/__edge/health" 2>/dev/null || true
}

if [[ "${WORKER_EXISTE:-false}" == "true" ]]; then
  fin_corte=$(( $(date +%s) + 300 ))
  corte=no
  while (( $(date +%s) < fin_corte )); do
    if [[ "$(salud)" != "200" ]]; then corte=si; echo "La instancia anterior ya se detuvo; arranca la nueva."; break; fi
    sleep 10
  done
  if [[ "$corte" == "no" ]]; then
    echo "::warning::En 5 min no vi el cambio de instancia: el 200 podría ser de la versión anterior. Revisa los logs (arranque_listo con APP_VERSION=${APP_VERSION:-?})."
  fi
fi

while (( $(date +%s) < limite )); do
  codigo="$(salud)"
  if [[ "$codigo" == "200" ]]; then
    echo "El sitio está sano:"
    cat "$cuerpo"; echo
    exit 0
  fi
  echo "Todavía no (HTTP ${codigo:-sin respuesta}): $(head -c 300 "$cuerpo" 2>/dev/null || true)"
  sleep 15
done

echo "::error::${URL_SITIO}/__edge/health no dio 200 en ${minutos} min tras el despliegue."
echo "Mira los logs (docs/OPERACION.md → «Dónde ver los logs») y, si hace falta, vuelve atrás"
echo "(docs/OPERACION.md → «Volver atrás un despliegue»)."
exit 1
