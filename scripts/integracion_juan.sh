#!/usr/bin/env bash
# Prueba de integración REAL de Juan: el Odoo de verdad (dcasa_conversaciones) y el Worker `juan` de verdad
# (sus handlers reales corriendo en Node), hablándose por HTTP. Nada de dobles entre los dos.
#
#   scripts/integracion_juan.sh
#
# Qué hace: crea una base nueva (dcasa_integra_<pid>), instala dcasa_conversaciones, carga productos de prueba, arranca
# Odoo en un puerto libre con JUAN_ODOO_TOKEN y JUAN_WORKER_TOKEN GENERADOS AHORA (solo viven en el entorno de los
# procesos de esta ejecución: no se escriben en ningún archivo ni en pantalla) y corre juan/test/integracion/*.test.ts.
# Al terminar, pase lo que pase, apaga Odoo y borra la base y los archivos temporales.
#
# Variables: PYTHON, ODOO_DIR (por defecto vendor/odoo), DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME,
#            ODOO_PORT / JUAN_PORT (por defecto, puertos libres), CONSERVAR=1 (no borrar la base ni los registros).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-odoo}"
DB_NAME="${DB_NAME:-dcasa_integra_$$}"
INICIO=$SECONDS

# Odoo: vendor/odoo; en un git worktree el submódulo suele estar vacío y vive en el árbol principal.
ODOO_DIR="${ODOO_DIR:-$ROOT/vendor/odoo}"
if [[ ! -f "$ODOO_DIR/odoo-bin" ]]; then
  PRINCIPAL="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  [[ -n "$PRINCIPAL" && -f "$PRINCIPAL/../vendor/odoo/odoo-bin" ]] && ODOO_DIR="$(cd "$PRINCIPAL/.." && pwd)/vendor/odoo"
fi
if [[ ! -f "$ODOO_DIR/odoo-bin" ]]; then
  echo "✖ No encuentro Odoo en $ODOO_DIR (git submodule update --init vendor/odoo, o define ODOO_DIR)." >&2
  exit 2
fi

puerto_libre() {
  "$PYTHON" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}
secreto() {
  "$PYTHON" -c 'import secrets; print(secrets.token_hex(24))'
}

ODOO_PORT="${ODOO_PORT:-$(puerto_libre)}"
JUAN_PORT="${JUAN_PORT:-$(puerto_libre)}"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/integracion_juan.XXXXXX")"
export PGPASSWORD="$DB_PASSWORD"
ODOO_PID=""

limpiar() {
  local rc=$?
  set +e
  if [[ -n "$ODOO_PID" ]] && kill -0 "$ODOO_PID" 2>/dev/null; then
    kill "$ODOO_PID" 2>/dev/null
    for _ in $(seq 1 50); do kill -0 "$ODOO_PID" 2>/dev/null || break; sleep 0.2; done
    kill -9 "$ODOO_PID" 2>/dev/null
  fi
  if [[ "${CONSERVAR:-0}" == "1" ]]; then
    echo "ℹ CONSERVAR=1: queda la base $DB_NAME y los registros en $TMP"
  else
    dropdb --if-exists -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" >/dev/null 2>&1
    rm -rf "$TMP"
  fi
  echo "⏱ Integración de Juan: $((SECONDS - INICIO)) s en total (exit $rc)."
  exit "$rc"
}
trap limpiar EXIT
trap 'exit 130' INT TERM

# Los secretos de esta ejecución: se generan aquí y solo existen en el entorno de los procesos hijos.
JUAN_ODOO_TOKEN="$(secreto)"
JUAN_WORKER_TOKEN="$(secreto)"
INTEGRACION_CLAVE_ADMIN="$(secreto)"
INTEGRACION_CLAVE_VENDEDORA="$(secreto)"
DCASA_PIN_PEPPER="$(secreto)"
export JUAN_ODOO_TOKEN JUAN_WORKER_TOKEN INTEGRACION_CLAVE_ADMIN INTEGRACION_CLAVE_VENDEDORA DCASA_PIN_PEPPER

pg_isready -q -h "$DB_HOST" -p "$DB_PORT" || { echo "✖ PostgreSQL no responde en $DB_HOST:$DB_PORT (service postgresql start)." >&2; exit 2; }
if [[ ! -d "$ROOT/juan/node_modules" ]]; then
  echo "▶ npm ci en juan/"
  (cd "$ROOT/juan" && npm ci --no-audit --no-fund >/dev/null)
fi
if [[ ! -d "$ROOT/edge/node_modules" ]]; then
  echo "▶ npm ci en edge/ (la entrada JuanEntrada se prueba con el código real)"
  (cd "$ROOT/edge" && npm ci --no-audit --no-fund >/dev/null)
fi

ADDONS="$ODOO_DIR/addons,$ODOO_DIR/odoo/addons,$ROOT/addons"
OPCIONES=("--addons-path=$ADDONS" "--db_host=$DB_HOST" "--db_port=$DB_PORT" "--db_user=$DB_USER"
          "--db_password=$DB_PASSWORD" "-d" "$DB_NAME" "--data-dir=${DATA_DIR:-$TMP/datos}")
ODOO=("$PYTHON" "$ODOO_DIR/odoo-bin")

INSTALAR=1
if [[ "${REUSAR_BASE:-0}" == "1" ]]; then
  # Solo para desarrollar la prueba: la base no se borra entre corridas (instalar tarda minutos). Si ya existe, se reutiliza.
  CONSERVAR=1
  DATA_DIR="${TMPDIR:-/tmp}/integracion_juan_datos_$DB_NAME"   # el filestore (fotos) tiene que sobrevivir a la corrida
  OPCIONES[${#OPCIONES[@]}-1]="--data-dir=$DATA_DIR"
  if [[ "$(psql -tAq -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'")" == "1" ]]; then
    INSTALAR=0
  fi
fi

if [[ $INSTALAR -eq 1 ]]; then
  dropdb --if-exists -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"
  echo "▶ Instalando dcasa_conversaciones en $DB_NAME"
  if ! "${ODOO[@]}" "${OPCIONES[@]}" -i dcasa_conversaciones --without-demo=all --stop-after-init \
        --http-port="$ODOO_PORT" --max-cron-threads=0 --logfile="$TMP/instalar.log"; then
    echo "✖ Falló la instalación. Últimas líneas:" >&2
    tail -n 40 "$TMP/instalar.log" >&2
    exit 1
  fi
  if grep -qE ' (ERROR|CRITICAL) ' "$TMP/instalar.log"; then
    echo "✖ La instalación dejó errores:" >&2
    grep -E ' (ERROR|CRITICAL) ' "$TMP/instalar.log" | head -20 >&2
    exit 1
  fi
fi

echo "▶ Cargando los datos de prueba"
if ! "${ODOO[@]}" shell "${OPCIONES[@]}" --http-port="$ODOO_PORT" --max-cron-threads=0 --logfile="$TMP/datos.log" \
      <"$ROOT/scripts/integracion_juan_datos.py" >"$TMP/datos.out" 2>&1; then
  echo "✖ Fallaron los datos de prueba:" >&2
  tail -n 30 "$TMP/datos.out" >&2
  exit 1
fi

# Odoo: sin crons automáticos (la prueba los dispara a mano), con JUAN_URL apuntando al Worker local.
JUAN_URL="http://127.0.0.1:$JUAN_PORT"
export JUAN_URL
echo "▶ Arrancando Odoo en el puerto $ODOO_PORT (el Worker local de la prueba usará el $JUAN_PORT)"
"${ODOO[@]}" "${OPCIONES[@]}" --workers=0 --max-cron-threads=0 --http-interface=127.0.0.1 --http-port="$ODOO_PORT" \
  --db-filter="^${DB_NAME}\$" --logfile="$TMP/odoo.log" >/dev/null 2>&1 &
ODOO_PID=$!
for _ in $(seq 1 120); do
  curl -fsS "http://127.0.0.1:$ODOO_PORT/web/health" >/dev/null 2>&1 && break
  kill -0 "$ODOO_PID" 2>/dev/null || { echo "✖ Odoo se cerró al arrancar:" >&2; tail -n 30 "$TMP/odoo.log" >&2; exit 1; }
  sleep 1
done
curl -fsS "http://127.0.0.1:$ODOO_PORT/web/health" >/dev/null || { echo "✖ Odoo no arrancó a tiempo." >&2; exit 1; }

echo "▶ Corriendo juan/test/integracion"
set +e
(
  cd "$ROOT/juan"
  ODOO_INTEGRACION_URL="http://127.0.0.1:$ODOO_PORT" ODOO_INTEGRACION_DB="$DB_NAME" \
  JUAN_INTEGRACION_PUERTO="$JUAN_PORT" \
  npx vitest run test/integracion
)
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  echo "✖ La integración falló. Registro de Odoo (errores y avisos):" >&2
  grep -E ' (ERROR|CRITICAL|WARNING) ' "$TMP/odoo.log" | tail -n 30 >&2 || true
  exit "$RC"
fi
if grep -E ' (ERROR|CRITICAL) ' "$TMP/odoo.log" >"$TMP/errores.log"; then
  echo "✖ Pasaron las pruebas, pero Odoo registró errores inesperados:" >&2
  head -n 20 "$TMP/errores.log" >&2
  exit 1
fi
echo "✔ Integración de Juan OK"
