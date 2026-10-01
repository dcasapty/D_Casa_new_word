#!/usr/bin/env bash
# En cada PR: comprueba que edge/wrangler.jsonc se puede desplegar con una imagen YA
# construida (I-08), sin credenciales ni Docker: genera la configuración de despliegue de
# producción y de staging con referencias de registro ficticias y la valida con
# `wrangler deploy --dry-run --containers-rollout=none` (no sube nada).
# Se corre desde la raíz del repo, con `npm ci` ya hecho en edge/.
set -euo pipefail
export WRANGLER_SEND_METRICS=false

cuenta=00000000000000000000000000000000
digest="sha256:$(printf '0%.0s' $(seq 64))"
ref_digest="registry.cloudflare.com/${cuenta}/dcasa-odoo@${digest}"
ref_tag="registry.cloudflare.com/${cuenta}/dcasa-odoo:0000000000000000000000000000000000000000"
salida="$(mktemp -d)"
trap 'rm -rf "$salida" edge/wrangler.desplegar.json' EXIT

for entorno in production staging; do
  echo "== ${entorno}"
  node .github/scripts/preparar_config.mjs edge/wrangler.jsonc edge/wrangler.desplegar.json \
    "$entorno" "$ref_digest" "$ref_tag"
  if [[ "$entorno" == "production" ]]; then destino=""; else destino="$entorno"; fi
  (
    cd edge
    CLOUDFLARE_ACCOUNT_ID="$cuenta" npx wrangler deploy --config wrangler.desplegar.json \
      --env="$destino" --dry-run --containers-rollout=none --outdir "$salida/$entorno" \
      | tee "$salida/$entorno.log"
  )
  if ! grep -q "$ref_tag\|$ref_digest" "$salida/$entorno.log"; then
    echo "::error::El dry-run de ${entorno} no muestra la imagen fijada: revisa edge/wrangler.jsonc."
    exit 1
  fi
done
echo "Configuración de despliegue válida para production y staging."
