#!/usr/bin/env bash
# Borra las copias temporales de la imagen que GitHub guarda en cada despliegue (artefactos «imagen-odoo-…», ~420 MB
# cada uno). Cuando se acumulan, GitHub llena su espacio de artefactos y deja de guardar nuevos: el siguiente despliegue
# falla al subir la imagen («Artifact storage quota has been hit»). El espacio se recalcula cada 6 a 12 horas.
#
# Qué toca y qué NO:
#   - SOLO artefactos de GitHub Actions cuyo nombre empieza con PREFIJO (por defecto «imagen-odoo-»), que no hayan
#     expirado y tengan al menos HORAS_MINIMAS horas (por defecto 24; nunca menos de 1: una ejecución en curso no
#     pierde la imagen que va a desplegar).
#   - NO toca R2, ni la base de datos, ni las fotos, ni nada del repositorio. La imagen que corre en Cloudflare vive en
#     su registro; esta copia solo era el transporte desde la prueba hasta el despliegue.
#
# Uso:
#   BORRAR=false (por defecto)  solo lista lo que borraría (ensayo).
#   BORRAR=true                 borra de verdad.
#   limpiar_artefactos.sh --seleccionar   lee por stdin objetos JSON de artefactos (uno por línea, como los devuelve
#                                         `gh api … --jq '.artifacts[]'`) y escribe los que se borrarían (para pruebas).
# Variables: PREFIJO, HORAS_MINIMAS, BORRAR, AHORA (segundos desde 1970; solo para pruebas), GITHUB_REPOSITORY y GH_TOKEN.
set -euo pipefail

PREFIJO="${PREFIJO-imagen-odoo-}"
HORAS_MINIMAS="${HORAS_MINIMAS:-24}"
BORRAR="${BORRAR:-false}"
AHORA="${AHORA:-$(date +%s)}"

if [[ -z "$PREFIJO" ]]; then
  echo "::error::PREFIJO no puede estar vacío: borraría todos los artefactos." >&2
  exit 2
fi
if ! [[ "$HORAS_MINIMAS" =~ ^[0-9]+$ ]] || ((HORAS_MINIMAS < 1)); then
  echo "::error::HORAS_MINIMAS debe ser un número entero de 1 o más (recibido «$HORAS_MINIMAS»)." >&2
  exit 2
fi
if [[ "$BORRAR" != "true" && "$BORRAR" != "false" ]]; then
  echo "::error::BORRAR debe ser true o false (recibido «$BORRAR»)." >&2
  exit 2
fi

# stdin: objetos JSON de artefactos → TSV (id, nombre, bytes, creado) de los que se borrarían.
seleccionar() {
  jq -r --arg prefijo "$PREFIJO" --argjson horas "$HORAS_MINIMAS" --argjson ahora "$AHORA" '
    select(.expired == false)
    | select(.name | startswith($prefijo))
    | select(($ahora - (.created_at | fromdateiso8601)) >= ($horas * 3600))
    | [.id, .name, .size_in_bytes, .created_at] | @tsv'
}

if [[ "${1:-}" == "--seleccionar" ]]; then
  seleccionar
  exit 0
fi

: "${GITHUB_REPOSITORY:?falta GITHUB_REPOSITORY (dueño/repositorio)}"

lista="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/actions/artifacts?per_page=100" --jq '.artifacts[]' | seleccionar)"

cantidad=0
total_bytes=0
resumen="${GITHUB_STEP_SUMMARY:-/dev/null}"
{
  if [[ "$BORRAR" == "true" ]]; then
    echo "### Copias temporales borradas (más de ${HORAS_MINIMAS} h, nombre «${PREFIJO}…»)"
  else
    echo "### ENSAYO: copias temporales que se borrarían (más de ${HORAS_MINIMAS} h, nombre «${PREFIJO}…»). No se borró nada."
  fi
  echo
  echo "| Archivo | MB | Creado |"
  echo "|---|---:|---|"
} >>"$resumen"

while IFS=$'\t' read -r id nombre bytes creado; do
  [[ -z "$id" ]] && continue
  cantidad=$((cantidad + 1))
  total_bytes=$((total_bytes + bytes))
  mb=$((bytes / 1048576))
  echo "${nombre}  ${mb} MB  ${creado}"
  echo "| ${nombre} | ${mb} | ${creado} |" >>"$resumen"
  if [[ "$BORRAR" == "true" ]]; then
    gh api -X DELETE "repos/${GITHUB_REPOSITORY}/actions/artifacts/${id}" --silent
  fi
done <<<"$lista"

total_mb=$((total_bytes / 1048576))
if [[ "$BORRAR" == "true" ]]; then
  mensaje="Borradas ${cantidad} copias (${total_mb} MB). GitHub recalcula el espacio en 6 a 12 horas."
else
  mensaje="Ensayo: se borrarían ${cantidad} copias (${total_mb} MB). Para borrar de verdad, lanzar de nuevo con borrar = true."
fi
echo "$mensaje"
{ echo; echo "**${mensaje}**"; } >>"$resumen"
