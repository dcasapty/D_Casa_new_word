#!/usr/bin/env bash
# Respaldo forzado antes de desplegar (I-02).
#
# Cada despliegue cambia APP_VERSION y el contenedor nuevo, al arrancar, corre la
# actualización de módulos (`odoo -u`) sobre la base viva. Si eso sale mal, la vuelta atrás
# es restaurar la base al punto de ESTE respaldo + desplegar la imagen anterior
# (docs/OPERACION.md → «Volver atrás un despliegue»).
#
# Usa el endpoint del borde (edge/CONTRATO_CONTENEDOR.md §2):
#   POST ${URL_SITIO}/__edge/respaldo  con  Authorization: Bearer <RESPALDO_TOKEN>
#   200 ok · 500 fallo · 409 ya hay uno en curso · 503 Odoo apagado · 401 token malo ·
#   404 sin RESPALDO_TOKEN en el Worker. Responde al terminar (hasta 14 min).
# El borde ejecuta /usr/local/bin/dcasa-respaldo dentro del contenedor (pg_dump cifrado a
# R2 y, según f1-imagen, un respaldo base de pgBackRest).
#
# Entradas: URL_SITIO, RESPALDO_TOKEN, ENTORNO.
#   503 (Odoo apagado): en staging se acepta (duerme tras 1 h y todo lo confirmado ya está
#   en el WAL archivado); en producción es un fallo (debería estar encendido 24/7).
set -euo pipefail

: "${URL_SITIO:?}" "${RESPALDO_TOKEN:?}"
entorno="${ENTORNO:-?}"
respuesta="$(mktemp)"
trap 'rm -f "$respuesta"' EXIT

for intento in $(seq 1 10); do
  echo "Pidiendo respaldo a ${URL_SITIO}/__edge/respaldo (intento ${intento}) ..."
  inicio=$(date +%s)
  codigo="$(curl -sS -o "$respuesta" -w '%{http_code}' --max-time 900 -X POST \
    -H "Authorization: Bearer ${RESPALDO_TOKEN}" "${URL_SITIO}/__edge/respaldo" || true)"
  duracion=$(( $(date +%s) - inicio ))
  case "$codigo" in
    200)
      echo "Respaldo listo en ${duracion} s."
      {
        echo "### Respaldo previo al despliegue"
        echo ""
        echo "Hecho el $(date -u '+%Y-%m-%d %H:%M UTC') (${duracion} s) antes de desplegar \`${GITHUB_SHA:-?}\`."
        echo "Si el despliegue sale mal, restaura a este punto (docs/OPERACION.md → «Volver atrás un despliegue»)."
      } >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
      exit 0
      ;;
    409)
      echo "Ya hay un respaldo en curso; espero 60 s y vuelvo a pedir uno."
      sleep 60
      ;;
    503)
      if [[ "$entorno" == "staging" ]]; then
        echo "::warning::Odoo de staging está apagado (dormido): no hay respaldo previo; lo confirmado ya está en el WAL de R2."
        exit 0
      fi
      echo "::error::Odoo de producción está apagado (HTTP 503): no hay respaldo previo, no se despliega."
      break
      ;;
    *)
      echo "::error::El respaldo previo falló (HTTP ${codigo:-sin respuesta}, ${duracion} s): no se despliega."
      head -c 2000 "$respuesta" || true
      echo
      break
      ;;
  esac
done

echo "Si el sitio está caído y necesitas desplegar igual (p. ej. para arreglarlo), corre"
echo "«Desplegar» a mano con respaldo_previo desmarcado: el último respaldo diario y el WAL"
echo "continuo siguen en R2 (docs/OPERACION.md → «Si el sitio se cae»)."
exit 1
