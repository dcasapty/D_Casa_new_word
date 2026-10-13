#!/usr/bin/env bash
# Regenera A PROPÓSITO las capturas de referencia del contrato visual (cabecera en todas las
# páginas y hero de la portada, a 1440 y 390 px): addons/website_dcasa/tests/referencia/*.webp.
#
# Úsalo solo cuando el cambio de cabecera o de hero es intencional y la dueña lo aprobó; las
# referencias nuevas van en el MISMO commit que el cambio (ver docs/OPERACION.md, «Contrato visual»).
# El test de estilos computados corre igual: si el contrato (vidrio líquido, hero sin placa) se
# rompió, el script falla y no reescribe nada.
#
# Uso: scripts/actualizar_referencias_visuales.sh
# Variables: las de scripts/test.sh (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, HTTP_PORT, PYTHON, ODOO_DIR).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REFERENCIAS="$ROOT/addons/website_dcasa/tests/referencia"

export DCASA_REFERENCIAS_VISUALES=regenerar
export TEST_TAGS="/website_dcasa:TestContratoVisual"
export DB_NAME="${DB_NAME:-dcasa_referencias}"

"$ROOT/scripts/test.sh" website_dcasa

echo
echo "Referencias en $REFERENCIAS:"
ls -la "$REFERENCIAS"/*.webp
echo
echo "Cambios respecto al último commit:"
git -C "$ROOT" status --short -- "$REFERENCIAS" || true
echo
echo "Revisa las capturas con tus ojos (son lo que verá la dueña) y súbelas en el mismo commit"
echo "que el cambio de cabecera o hero: git add addons/website_dcasa/tests/referencia"
