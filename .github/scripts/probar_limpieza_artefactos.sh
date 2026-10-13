#!/usr/bin/env bash
# Prueba la selección de .github/scripts/limpiar_artefactos.sh con artefactos de muestra (sin llamar a GitHub):
# solo se borra lo que debe, y los argumentos peligrosos se rechazan.
set -euo pipefail

cd "$(dirname "$0")"
SCRIPT=./limpiar_artefactos.sh
AHORA=$(date -d '2026-10-13T12:00:00Z' +%s)
export AHORA

# Uno por línea, como los entrega `gh api … --jq '.artifacts[]'`.
muestra() {
  cat <<'JSON'
{"id":1,"name":"imagen-odoo-vieja","size_in_bytes":418000000,"expired":false,"created_at":"2026-10-11T07:15:49Z"}
{"id":2,"name":"imagen-odoo-reciente","size_in_bytes":418000000,"expired":false,"created_at":"2026-10-13T10:00:00Z"}
{"id":3,"name":"imagen-odoo-expirada","size_in_bytes":418000000,"expired":true,"created_at":"2026-10-08T07:15:49Z"}
{"id":4,"name":"simulacro-restauracion","size_in_bytes":29574,"expired":false,"created_at":"2026-10-11T07:13:59Z"}
{"id":5,"name":"dcasapty~D_Casa_new_word~Q9S8T7.dockerbuild","size_in_bytes":43918,"expired":false,"created_at":"2026-10-11T07:15:50Z"}
{"id":6,"name":"odoo-test-log","size_in_bytes":1000,"expired":false,"created_at":"2026-10-01T07:15:50Z"}
{"id":7,"name":"imagen-odoo-justo-24h","size_in_bytes":418000000,"expired":false,"created_at":"2026-10-12T12:00:00Z"}
JSON
}

fallos=0
verificar() { # descripción, esperado, obtenido
  if [[ "$2" == "$3" ]]; then
    echo "ok   $1"
  else
    echo "FALLA $1"
    echo "  esperado: $2"
    echo "  obtenido: $3"
    fallos=$((fallos + 1))
  fi
}

ids() { cut -f1 | paste -sd, -; }

verificar "por defecto (24 h) solo borra las «imagen-odoo-» viejas y sin expirar" \
  "1,7" "$(muestra | "$SCRIPT" --seleccionar | ids)"

verificar "con 1 h entra también la reciente, pero nunca las que no son imágenes ni las expiradas" \
  "1,2,7" "$(muestra | HORAS_MINIMAS=1 "$SCRIPT" --seleccionar | ids)"

verificar "con 72 h no queda ninguna" \
  "" "$(muestra | HORAS_MINIMAS=72 "$SCRIPT" --seleccionar | ids)"

verificar "otro prefijo: solo ese" \
  "4" "$(muestra | PREFIJO=simulacro- "$SCRIPT" --seleccionar | ids)"

verificar "la salida trae id, nombre, bytes y fecha" \
  $'1\timagen-odoo-vieja\t418000000\t2026-10-11T07:15:49Z' "$(muestra | "$SCRIPT" --seleccionar | head -n1)"

rechaza() { # descripción, variables...
  local descripcion="$1"
  shift
  if muestra | env "$@" "$SCRIPT" --seleccionar >/dev/null 2>&1; then
    echo "FALLA $descripcion (debió rechazarlo)"
    fallos=$((fallos + 1))
  else
    echo "ok   $descripcion"
  fi
}

rechaza "rechaza un prefijo vacío (borraría todo)" PREFIJO=
rechaza "rechaza 0 horas (borraría la imagen de un despliegue en curso)" HORAS_MINIMAS=0
rechaza "rechaza horas que no son un entero" HORAS_MINIMAS=abc
rechaza "rechaza horas negativas" HORAS_MINIMAS=-5
rechaza "rechaza BORRAR con otro valor" BORRAR=quizas

if ((fallos > 0)); then
  echo "${fallos} prueba(s) fallaron." >&2
  exit 1
fi
echo "Limpieza de artefactos: todo bien."
