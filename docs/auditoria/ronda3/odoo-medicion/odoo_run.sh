#!/usr/bin/env bash
# Arranca Odoo 19 (vendor/odoo + addons/) contra el clúster propio, en segundo plano.
# Uso: odoo_run.sh <http_port> [workers] [max_cron_threads] [db_maxconn] [extra odoo args...]
# Variables: DB (r3_med_base), PGPORT (5441), LIMSOFT/LIMHARD (bytes, solo prefork), TAG (nombre del log)
# Imprime el PID del proceso principal. Config equivalente a docker/entrypoint.sh (proxy_mode,
# unaccent, list_db=False, dbfilter) salvo las rutas.
set -euo pipefail
ROOT=/home/user/D_Casa_new_word
PORT="$1"; WORKERS="${2:-0}"; CRON="${3:-1}"; MAXCONN="${4:-16}"; shift $(( $# < 4 ? $# : 4 ))
DB="${DB:-r3_med_base}"; PGPORT="${PGPORT:-5441}"; TAG="${TAG:-odoo_$PORT}"
W=/tmp/r3_med_odoo; mkdir -p "$W/data"
CONF="$W/$TAG.conf"; LOG="$W/$TAG.log"
cat > "$CONF" <<CONF
[options]
addons_path = $ROOT/vendor/odoo/addons,$ROOT/vendor/odoo/odoo/addons,$ROOT/addons
data_dir = $W/data
db_host = localhost
db_port = $PGPORT
db_user = odoo
db_password = odoo
db_name = $DB
dbfilter = ^$DB\$
list_db = False
proxy_mode = True
http_interface = 127.0.0.1
http_port = $PORT
gevent_port = $((PORT+5))
workers = $WORKERS
max_cron_threads = $CRON
db_maxconn = $MAXCONN
limit_time_real = 300
limit_memory_soft = ${LIMSOFT:-2147483648}
limit_memory_hard = ${LIMHARD:-2684354560}
log_level = info
unaccent = True
CONF
nohup python3 "$ROOT/vendor/odoo/odoo-bin" -c "$CONF" "$@" >"$LOG" 2>&1 &
echo $!
