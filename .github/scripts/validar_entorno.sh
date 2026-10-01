#!/usr/bin/env bash
# Valida, ANTES de tocar Cloudflare, que los secretos y variables de un entorno de
# GitHub (staging o production) existen y no son marcadores (I-11).
#
# Uso: validar_entorno.sh NOMBRE [NOMBRE...]
#   Cada NOMBRE es una variable de entorno del paso (el workflow mapea ahí los
#   secrets.* y vars.* del environment). Sale con 1 y lista TODOS los problemas
#   (no solo el primero) si alguno falta, está vacío o tiene un marcador.
#
# Reglas adicionales (solo si la variable está entre las pedidas):
#   - PGBACKREST_CIPHER_PASS, RESPALDO_TOKEN, DCASA_PIN_PEPPER: mínimo 32 caracteres.
#   - ODOO_MASTER_PASSWORD distinta de ODOO_ADMIN_PASSWORD.
#   - URL_SITIO empieza con https:// y no termina en «/».
#   - R2_ENDPOINT (si se pide) es https://<cuenta>.r2.cloudflarestorage.com.
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "uso: $0 NOMBRE [NOMBRE...]" >&2
  exit 2
fi

# Marcadores que delatan un valor de ejemplo copiado de la documentación.
MARCADORES='CAMBIAR|PENDIENTE|REEMPLAZAR|CHANGEME|CHANGE_ME|PLACEHOLDER|<[^>]*>'

problemas=()
pedidas=" $* "

for nombre in "$@"; do
  valor="${!nombre-}"
  if [[ -z "${valor//[[:space:]]/}" ]]; then
    problemas+=("$nombre: falta o está vacío")
    continue
  fi
  if grep -qiE "$MARCADORES" <<<"$valor"; then
    problemas+=("$nombre: tiene un marcador de ejemplo (CAMBIAR, PENDIENTE, <...>)")
  fi
  if [[ "$valor" != "$(printf '%s' "$valor" | tr -d '\r\n')" ]]; then
    problemas+=("$nombre: tiene saltos de línea (¿se pegó con un Enter de más?)")
  fi
  case "$nombre" in
    PGBACKREST_CIPHER_PASS | RESPALDO_TOKEN | DCASA_PIN_PEPPER)
      if [[ ${#valor} -lt 32 ]]; then
        problemas+=("$nombre: demasiado corto (mínimo 32 caracteres; genera uno con: openssl rand -hex 32)")
      fi
      ;;
    URL_SITIO)
      if [[ "$valor" != https://* || "$valor" == */ ]]; then
        problemas+=("URL_SITIO: debe empezar con https:// y no terminar en / (p. ej. https://dcasapty.com)")
      fi
      ;;
    R2_ENDPOINT)
      if [[ "$valor" != https://* || "$valor" == */ ]]; then
        problemas+=("R2_ENDPOINT: debe ser https://<ACCOUNT_ID>.r2.cloudflarestorage.com (sin / al final)")
      fi
      ;;
  esac
done

if [[ "$pedidas" == *" ODOO_MASTER_PASSWORD "* && "$pedidas" == *" ODOO_ADMIN_PASSWORD "* \
      && -n "${ODOO_MASTER_PASSWORD-}" && "${ODOO_MASTER_PASSWORD-}" == "${ODOO_ADMIN_PASSWORD-}" ]]; then
  problemas+=("ODOO_MASTER_PASSWORD: debe ser distinta de ODOO_ADMIN_PASSWORD")
fi

if [[ ${#problemas[@]} -gt 0 ]]; then
  echo "::error::Configuración incompleta del entorno «${ENTORNO:-?}»: no se despliega nada."
  for p in "${problemas[@]}"; do
    echo "::error::$p"
  done
  echo "Revisa GitHub → Settings → Environments → ${ENTORNO:-?} (docs/DESPLIEGUE.md §3)."
  exit 1
fi
echo "Entorno «${ENTORNO:-?}»: ${#} valores presentes y sin marcadores."
