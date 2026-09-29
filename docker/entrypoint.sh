#!/usr/bin/env bash
# Arranque de Odoo para D'CASA.
#
# 1. Genera odoo.conf a partir de variables de entorno (sin secretos en la imagen).
# 2. Base nueva  -> instala los módulos de D'CASA con español.
#    Base existente con otra versión de la imagen -> actualiza los módulos de D'CASA.
# 3. Arranca Odoo en modo multihilo (un solo puerto: HTTP + websocket), que es
#    lo que expone el contenedor de Cloudflare.
set -euo pipefail

: "${DB_HOST:?Falta DB_HOST}"
: "${DB_USER:?Falta DB_USER}"
: "${DB_PASSWORD:?Falta DB_PASSWORD}"
: "${ADMIN_PASSWORD:?Falta ADMIN_PASSWORD (contraseña maestra de Odoo)}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-dcasa}"
DB_SSLMODE="${DB_SSLMODE:-prefer}"
ODOO_MODULES="${ODOO_MODULES:-dcasa_base,dcasa_invoice,dcasa_referral,website_dcasa}"
ODOO_LANG="${ODOO_LANG:-es_419}"
APP_VERSION="${APP_VERSION:-dev}"
CONF="${ODOO_RC:-/var/lib/odoo/odoo.conf}"

cat > "$CONF" <<CONF
[options]
addons_path = /opt/odoo/addons,/opt/odoo/odoo/addons,/opt/dcasa/addons
data_dir = /var/lib/odoo/data
db_host = ${DB_HOST}
db_port = ${DB_PORT}
db_user = ${DB_USER}
db_password = ${DB_PASSWORD}
db_name = ${DB_NAME}
db_sslmode = ${DB_SSLMODE}
dbfilter = ^${DB_NAME}\$
list_db = False
admin_passwd = ${ADMIN_PASSWORD}
proxy_mode = True
http_interface = 0.0.0.0
http_port = 8069
workers = 0
max_cron_threads = ${ODOO_CRON_THREADS:-1}
db_maxconn = ${ODOO_DB_MAXCONN:-16}
limit_time_real = ${ODOO_LIMIT_TIME_REAL:-300}
log_level = ${ODOO_LOG_LEVEL:-info}
CONF
chmod 600 "$CONF"

odoo() { python3 /opt/odoo/odoo-bin -c "$CONF" "$@"; }

export PGPASSWORD="$DB_PASSWORD" PGSSLMODE="$DB_SSLMODE"
sql() {
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAq -v ON_ERROR_STOP=1 -c "$1" 2>/dev/null || true
}

installed="$(sql "SELECT state FROM ir_module_module WHERE name = 'dcasa_base'")"
if [[ "$installed" != "installed" ]]; then
  echo "▶ Base nueva: instalando $ODOO_MODULES ($ODOO_LANG)"
  odoo -d "$DB_NAME" -i "$ODOO_MODULES" --load-language="$ODOO_LANG" --stop-after-init
  # Nunca dejar admin/admin en una base expuesta a internet.
  ADMIN_USER_PASSWORD="${ADMIN_USER_PASSWORD:-$ADMIN_PASSWORD}" \
    python3 /opt/odoo/odoo-bin shell -c "$CONF" -d "$DB_NAME" --log-level=warn >/dev/null <<'PY'
import os
env.ref('base.user_admin').password = os.environ['ADMIN_USER_PASSWORD']
env.cr.commit()
PY
  sql "INSERT INTO ir_config_parameter (key, value, create_date, write_date)
       VALUES ('dcasa.deployed_version', '$APP_VERSION', now(), now())
       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = now()" >/dev/null
else
  deployed="$(sql "SELECT value FROM ir_config_parameter WHERE key = 'dcasa.deployed_version'")"
  if [[ "$deployed" != "$APP_VERSION" ]]; then
    echo "▶ Nueva versión ($deployed → $APP_VERSION): actualizando $ODOO_MODULES"
    odoo -d "$DB_NAME" -u "$ODOO_MODULES" --stop-after-init
    sql "INSERT INTO ir_config_parameter (key, value, create_date, write_date)
         VALUES ('dcasa.deployed_version', '$APP_VERSION', now(), now())
         ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = now()" >/dev/null
  fi
fi

echo "▶ Iniciando Odoo ($APP_VERSION)"
exec python3 /opt/odoo/odoo-bin -c "$CONF" "$@"
