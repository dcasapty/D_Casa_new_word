#!/usr/bin/env bash
# Instala los módulos de D'CASA en una base limpia y corre sus tests.
# Uso: scripts/test.sh [modulo1,modulo2]   (por defecto: todos los de addons/)
# Variables: DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME PYTHON
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
DB_NAME="${DB_NAME:-dcasa_test}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-odoo}"
LOG="${LOG:-$ROOT/.test.log}"

if [[ $# -gt 0 ]]; then
  MODULES="$1"
else
  MODULES="$(find "$ROOT/addons" -mindepth 2 -maxdepth 2 -name __manifest__.py -printf '%h\n' | xargs -n1 basename | sort | paste -sd, -)"
fi
TEST_TAGS="$(tr ',' '\n' <<<"$MODULES" | sed 's#^#/#' | paste -sd, -)"

export PGPASSWORD="$DB_PASSWORD"
dropdb --if-exists -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"

echo "▶ Instalando y probando: $MODULES"
set +e
"$PYTHON" "$ROOT/vendor/odoo/odoo-bin" \
  --addons-path="$ROOT/vendor/odoo/addons,$ROOT/vendor/odoo/odoo/addons,$ROOT/addons" \
  --db_host="$DB_HOST" --db_port="$DB_PORT" --db_user="$DB_USER" --db_password="$DB_PASSWORD" \
  -d "$DB_NAME" -i "$MODULES" \
  --test-enable --test-tags="$TEST_TAGS" \
  --stop-after-init --log-level=test --http-port=8169 \
  2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
set -e

# odoo-bin no siempre devuelve != 0 ante un test fallido: se revisa el log.
if [[ $rc -ne 0 ]] || grep -qE '^[0-9-]+ [0-9:,]+ [0-9]+ (ERROR|CRITICAL) ' "$LOG"; then
  echo "✖ Fallaron la instalación o los tests. Detalle:"
  grep -E ' (ERROR|CRITICAL) ' "$LOG" | head -50 || true
  exit 1
fi
echo "✔ Tests OK ($MODULES)"
