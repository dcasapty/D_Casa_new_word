#!/usr/bin/env bash
# Respaldos de la base de D'CASA en R2 (Fase 1, PostgreSQL dentro del contenedor).
#
# Uso (dentro del contenedor, como el usuario odoo; en la imagen: dcasa-respaldo):
#   respaldo.sh             (sin argumentos) respaldo DIARIO: lo lanza el Worker con
#                           `timeout --kill-after=30 840 /usr/local/bin/dcasa-respaldo`
#                           (cron 03:17 Panamá o POST /__edge/respaldo; edge/CONTRATO_CONTENEDOR.md).
#                           Volcado lógico SIEMPRE + respaldo pgBackRest: full con
#                           DCASA_RESPALDO_ORIGEN=manual (lo pide el despliegue antes de
#                           cada versión: punto de vuelta atrás) o si el último completo
#                           tiene ≥ 20 h; si no, incr. Última línea: resumen sin secretos.
#   respaldo.sh auto        lo que toque: full cada RESPALDO_FULL_HORAS (24), incr cada
#                           RESPALDO_INCR_HORAS (6) o tras una restauración, y el volcado
#                           lógico cada RESPALDO_DUMP_HORAS (24). Lo llama el vigilante de
#                           docker/entrypoint.sh cada hora (RESPALDO_REVISAR_S).
#   respaldo.sh full|diff|incr   respaldo físico pgBackRest de ese tipo, ya.
#   respaldo.sh dump        volcado lógico (pg_dump -Fc zstd, cifrado) a R2_RUTA_DUMP, ya.
#                           Sube en flujo (multipart), sin escribir el volcado entero en disco.
#   respaldo.sh info        estado del repositorio y de los volcados.
#
# Retención: pgBackRest guarda los completos de los últimos RESPALDO_RETENCION_DIAS (7)
# días (con uno diario son ~8 completos) y su WAL ⇒ se puede volver a cualquier minuto de
# esa semana. Los volcados lógicos se borran a los RESPALDO_DUMP_DIAS (30), salvo el
# primero de cada año, que se copia a R2_RUTA_ANUAL (anual/) y no se poda nunca: copia
# de cierre (ver docs/OPERACION.md «Copia anual» y las reglas de ciclo de vida de R2).
# Toda la lógica está en docker/pg.sh; este script solo la expone.
set -euo pipefail

for lib in "${DCASA_PG_LIB:-}" "$(dirname "$(readlink -f "$0")")/../docker/pg.sh" /usr/local/lib/dcasa/pg.sh; do
  if [[ -n "$lib" && -r "$lib" ]]; then
    # shellcheck source=docker/pg.sh
    source "$lib"
    break
  fi
done
declare -F pg_cargar_repo >/dev/null || { echo "✖ No encuentro docker/pg.sh" >&2; exit 1; }

DB_NAME="${DB_NAME:-dcasa}"
pg_cargar_repo
pg_vivo || { pg_msg "✖ PostgreSQL no está corriendo ($PG_DATA)"; exit 1; }

# Un respaldo a la vez. El automático del vigilante cede el paso; el diario/manual
# espera (el respaldo previo a un despliegue no puede darse por hecho sin hacerse).
exec 9>"$PG_BASE/lock/respaldo.lock"
if [[ "${1:-diario}" == "auto" ]]; then
  if ! flock -n 9; then
    pg_msg "· ya hay un respaldo en curso: no hago nada"
    exit 0
  fi
elif ! flock -w 600 9; then
  echo "respaldo FALLO: otro respaldo lleva más de 10 min en curso"
  exit 1
fi

T0=$SECONDS
resumen() { echo "respaldo $1: ${2:-} en $((SECONDS - T0)) s (origen ${DCASA_RESPALDO_ORIGEN:-local})"; }

case "${1:-diario}" in
  full | diff | incr)
    if ! respaldo_fisico "$1"; then resumen FALLO "pgBackRest $1"; exit 1; fi
    resumen ok "pgBackRest $1"
    ;;
  dump)
    if ! respaldo_dump "$DB_NAME"; then resumen FALLO "volcado lógico"; exit 1; fi
    resumen ok "volcado $RESPALDO_DUMP_ULTIMO"
    ;;
  diario)
    rc=0
    hechos=()
    if [[ "${DCASA_RESPALDO_ORIGEN:-}" == "manual" ]]; then
      tipo="full"
    else
      tipo="$(respaldo_que_toca 20)" || { resumen FALLO "no pude consultar el repositorio"; exit 1; }
      [[ "$tipo" == "full" ]] || tipo="incr"
    fi
    if respaldo_fisico "$tipo"; then hechos+=("pgBackRest $tipo"); else rc=1; hechos+=("pgBackRest $tipo FALLÓ"); fi
    if respaldo_dump "$DB_NAME"; then hechos+=("volcado $RESPALDO_DUMP_ULTIMO"); else rc=1; hechos+=("volcado FALLÓ"); fi
    if ((rc == 0)); then resumen ok "${hechos[*]}"; else resumen FALLO "${hechos[*]}"; fi
    exit "$rc"
    ;;
  auto)
    rc=0
    tipo="$(respaldo_que_toca)" || { pg_alerta "no pude consultar el repositorio de respaldos"; exit 1; }
    if [[ "$tipo" != "nada" ]]; then
      respaldo_fisico "$tipo" || rc=1
    fi
    toca=0
    respaldo_dump_toca "$DB_NAME" || toca=$?
    if ((toca == 0)); then
      respaldo_dump "$DB_NAME" || rc=1
    elif ((toca == 2)); then
      pg_alerta "no pude listar los volcados en R2"
      rc=1
    fi
    resumen "$( ((rc == 0)) && echo ok || echo FALLO)" "auto (pgBackRest: $tipo)"
    exit "$rc"
    ;;
  info)
    pgbr info
    echo "Volcados lógicos en /${R2_RUTA_DUMP#/}:"
    respaldo_dump_listar "$DB_NAME"
    echo "Copias anuales de cierre en /${R2_RUTA_ANUAL#/}:"
    pgbr_raiz repo-ls "${R2_RUTA_ANUAL#/}" --filter="^$DB_NAME-.*\\.dump\\.enc\$"
    ;;
  *)
    sed -n '2,26p' "$0"
    exit 2
    ;;
esac
