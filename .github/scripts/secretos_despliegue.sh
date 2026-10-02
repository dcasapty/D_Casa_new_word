#!/usr/bin/env bash
# Arma el archivo de secretos que `wrangler deploy --secrets-file` sube JUNTO con el
# despliegue (los secretos quedan antes de que arranque la versión nueva, no después; I-11).
#
# Entradas (variables de entorno):
#   CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, WORKER   para consultar el Worker
#   SALIDA                                                ruta del JSON a escribir (modo 600)
#   ODOO_ADMIN_PASSWORD (→ ADMIN_PASSWORD), ODOO_MASTER_PASSWORD, R2_ACCESS_KEY_ID,
#   R2_SECRET_ACCESS_KEY, RESPALDO_TOKEN, BRIAN_API_KEY   se suben en cada despliegue
#   R2_ENDPOINT   opcional; por defecto https://<CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com
#   TELEGRAM_BOT_TOKEN, BRIAN_TELEGRAM_SECRETO            opcionales: solo si existen
#   TIENDA_FEED_TOKEN   opcional: tienda estática (feed de Odoo + aviso de regeneración, ≥ 32)
#   TURNSTILE_SECRET    opcional: Cloudflare Turnstile (docs/SEGURIDAD_ACCESO.md)
#   DCASA_PIN_PEPPER, PGBACKREST_CIPHER_PASS              se suben UNA vez (ver abajo)
#
# Nombres y obligatoriedad: edge/CONTRATO_CONTENEDOR.md §3.
#
# Salida (GITHUB_OUTPUT): worker_existe=true|false
#
# DCASA_PIN_PEPPER y PGBACKREST_CIPHER_PASS no se rotan jamás: cambiar la pimienta rompe el
# PIN de todos los socios; cambiar la clave de cifrado de pgBackRest deja ilegibles los
# respaldos ya guardados en R2 y corta el archivado de WAL. Por eso solo se suben si el
# Worker todavía NO los tiene. Si la consulta a Cloudflare falla (token, red, 5xx) no se
# puede concluir que faltan: se aborta sin escribir nada (S-03). Solo un 404 del Worker
# (no existe todavía: primer despliegue) o un listado válido sin el secreto permiten subirlo.
set -euo pipefail

: "${CLOUDFLARE_API_TOKEN:?}" "${CLOUDFLARE_ACCOUNT_ID:?}" "${WORKER:?}" "${SALIDA:?}"

respuesta="$(mktemp)"
trap 'rm -f "$respuesta"' EXIT

codigo="$(curl -sS -o "$respuesta" -w '%{http_code}' --retry 3 --retry-all-errors \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/workers/scripts/${WORKER}/secrets" \
  || echo "000")"

case "$codigo" in
  200)
    if ! jq -e '.success == true and (.result | type == "array")' "$respuesta" >/dev/null; then
      echo "::error::El listado de secretos de «${WORKER}» no es el esperado: no toco nada. Reintenta el job."
      exit 1
    fi
    worker_existe=true
    mapfile -t existentes < <(jq -r '.result[].name' "$respuesta")
    ;;
  404)
    worker_existe=false
    existentes=()
    echo "El Worker «${WORKER}» todavía no existe: primer despliegue de este entorno."
    ;;
  *)
    echo "::error::No pude consultar los secretos de «${WORKER}» (HTTP ${codigo}): no toco nada. Reintenta el job."
    jq -r '.errors[]?.message' "$respuesta" 2>/dev/null | sed 's/^/::error::/' || true
    exit 1
    ;;
esac

tiene() {
  local n
  for n in "${existentes[@]}"; do [[ "$n" == "$1" ]] && return 0; done
  return 1
}

una_vez=()
for nombre in DCASA_PIN_PEPPER PGBACKREST_CIPHER_PASS; do
  if tiene "$nombre"; then
    echo "${nombre}: ya existe en el Worker, no se toca (nunca se rota)."
  else
    una_vez+=("$nombre")
    echo "${nombre}: no existe en el Worker; se sube desde el secreto de GitHub (respaldado por el dueño)."
  fi
done

# Endpoint S3 de R2 de la cuenta (secreto por contrato: lleva el ID de la cuenta).
R2_ENDPOINT="${R2_ENDPOINT:-https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com}"
export R2_ENDPOINT

umask 077
UNA_VEZ="${una_vez[*]:-}" jq -n '
  env as $e
  | {
      ADMIN_PASSWORD: $e.ODOO_ADMIN_PASSWORD,
      ODOO_MASTER_PASSWORD: $e.ODOO_MASTER_PASSWORD,
      R2_ENDPOINT: $e.R2_ENDPOINT,
      R2_ACCESS_KEY_ID: $e.R2_ACCESS_KEY_ID,
      R2_SECRET_ACCESS_KEY: $e.R2_SECRET_ACCESS_KEY,
      RESPALDO_TOKEN: $e.RESPALDO_TOKEN,
      BRIAN_API_KEY: $e.BRIAN_API_KEY,
      TELEGRAM_BOT_TOKEN: $e.TELEGRAM_BOT_TOKEN,
      BRIAN_TELEGRAM_SECRETO: $e.BRIAN_TELEGRAM_SECRETO,
      TIENDA_FEED_TOKEN: $e.TIENDA_FEED_TOKEN,
      TURNSTILE_SECRET: $e.TURNSTILE_SECRET
    }
  + ( ($e.UNA_VEZ | split(" ") | map(select(. != "")))
      | map({key: ., value: $e[.]}) | from_entries )
  | with_entries(select(.value != null and .value != ""))
' > "$SALIDA"

echo "Secretos a subir con el despliegue: $(jq -r 'keys | join(", ")' "$SALIDA")"
echo "worker_existe=${worker_existe}" >> "${GITHUB_OUTPUT:-/dev/null}"
