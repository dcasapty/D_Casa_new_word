#!/usr/bin/env bash
# Regenera A PROPÓSITO las capturas de referencia del contrato visual de la pantalla de Conversaciones de Juan
# (la lista, un hilo abierto y Conexiones, a 1440 y 390 px):
# addons/dcasa_conversaciones/tests/referencia/panel-*.webp.
#
# Úsalo solo cuando el cambio de la pantalla es intencional y la dueña lo aprobó; las referencias nuevas van en el
# MISMO commit que el cambio (ver docs/OPERACION.md, «Contrato visual de la pantalla de Conversaciones»).
# El test de estilos computados (sistema plano, amarillo solo sobre azul marino, contraste, foco visible) corre igual:
# si el contrato se rompió, el script falla y no reescribe nada.
#
# Uso: scripts/actualizar_referencias_visuales_juan.sh
# Variables: las de scripts/test.sh (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, HTTP_PORT, PYTHON, ODOO_DIR).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REFERENCIAS="$ROOT/addons/dcasa_conversaciones/tests/referencia"

export DCASA_REFERENCIAS_VISUALES=regenerar
export TEST_TAGS="/dcasa_conversaciones:TestContratoVisualJuan"
export DB_NAME="${DB_NAME:-dcasa_referencias_juan}"

"$ROOT/scripts/test.sh" dcasa_conversaciones

echo
echo "Referencias en $REFERENCIAS:"
ls -la "$REFERENCIAS"/*.webp
echo
echo "Cambios respecto al último commit:"
git -C "$ROOT" status --short -- "$REFERENCIAS" || true
echo
echo "Revisa las capturas con tus ojos (son lo que verá la dueña) y súbelas en el mismo commit"
echo "que el cambio de la pantalla: git add addons/dcasa_conversaciones/tests/referencia"
