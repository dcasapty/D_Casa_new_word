#!/usr/bin/env bash
# Arranque de Odoo para D'CASA.
#
# 1. Genera odoo.conf a partir de variables de entorno (sin secretos en la imagen).
# 2. Espera a PostgreSQL. Si la base no responde, el arranque FALLA (nunca se
#    confunde «no pude consultar» con «base nueva»).
# 3. Base nueva  -> instala los módulos de D'CASA con español.
#    Base existente con otra versión de la imagen -> actualiza los módulos de D'CASA.
# 4. Saneo del usuario admin (idempotente, en CADA arranque hasta que quede hecho):
#    si admin sigue con la clave «admin», se cambia antes de abrir el puerto.
# 5. Desinstala los módulos de Odoo que D'CASA no usa (idempotente, una vez por versión).
# 6. Arranca Odoo en modo multihilo (un solo puerto: HTTP + websocket), que es
#    lo que expone el contenedor de Cloudflare.
#
# Variables:
#   ADMIN_PASSWORD        clave del usuario admin de Odoo (obligatoria). Se fija solo
#                         si admin aún tiene la clave «admin» (base nueva o arranque
#                         interrumpido); nunca pisa una clave que el dueño ya cambió.
#   ADMIN_USER_PASSWORD   (opcional) reemplaza a ADMIN_PASSWORD para el usuario admin.
#   ODOO_MASTER_PASSWORD  (opcional) contraseña maestra (admin_passwd), distinta de la
#                         de admin. Si falta, se genera una aleatoria en cada arranque
#                         y no se muestra: el gestor de bases está cerrado
#                         (list_db = False y bloqueado en el borde), así que no hace falta.
#   ODOO_DB_MAXCONN       conexiones a PostgreSQL del proceso de Odoo (por defecto 48;
#                         ver docs/DESPLIEGUE.md → «Conexiones a PostgreSQL»).
#   DB_REINTENTOS         intentos de conexión a PostgreSQL al arrancar (por defecto 20, cada 3 s).
#   ODOO_DESINSTALAR_SOBRANTES  0 para no desinstalar los módulos sobrantes.
set -euo pipefail

: "${DB_HOST:?Falta DB_HOST}"
: "${DB_USER:?Falta DB_USER}"
: "${DB_PASSWORD:?Falta DB_PASSWORD}"
: "${ADMIN_PASSWORD:?Falta ADMIN_PASSWORD (clave del usuario admin de Odoo)}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-dcasa}"
DB_SSLMODE="${DB_SSLMODE:-prefer}"
DB_REINTENTOS="${DB_REINTENTOS:-20}"
ODOO_MODULES="${ODOO_MODULES:-dcasa_base,dcasa_invoice,dcasa_socios,website_dcasa,dcasa_catalogo,dcasa_interfaz,dcasa_contabilidad,dcasa_brian}"
ODOO_LANG="${ODOO_LANG:-es_419}"
APP_VERSION="${APP_VERSION:-dev}"
CONF="${ODOO_RC:-/var/lib/odoo/odoo.conf}"
ODOO_BIN="${ODOO_BIN:-/opt/odoo/odoo-bin}"
ODOO_ADDONS_PATH="${ODOO_ADDONS_PATH:-/opt/odoo/addons,/opt/odoo/odoo/addons,/opt/dcasa/addons}"
ODOO_DATA_DIR="${ODOO_DATA_DIR:-/var/lib/odoo/data}"
ODOO_HTTP_PORT="${ODOO_HTTP_PORT:-8069}"
ADMIN_USER_PASSWORD="${ADMIN_USER_PASSWORD:-$ADMIN_PASSWORD}"

# Módulos de Odoo que D'CASA no usa (decisión del dueño; docs/auditoria/BITACORA.md
# «el CRM se queda»). Patrones de shell. Los puentes automáticos que dependen de
# ellos (p. ej. website_sale_stock_wishlist) se van con ellos.
DCASA_SOBRANTES="sms *_sms snailmail* iap* crm_iap_* iap_crm partner_autocomplete
  account_edi_ubl_cii purchase_edi_ubl_bis3 sale_edi_ubl spreadsheet_dashboard*
  spreadsheet_account website_sale_wishlist website_sale_comparison* base_import_module"
# Nunca se desinstalan, aunque coincidan con un patrón o dependan de un sobrante.
DCASA_PROTEGIDOS="base web crm sale_crm calendar auth_totp* base_import dcasa_* website_dcasa ${ODOO_MODULES//,/ }"

if [[ -z "${DCASA_PIN_PEPPER:-}" ]]; then
  echo "⚠ Falta DCASA_PIN_PEPPER: la app de socios (/socios) no dejará registrarse ni entrar." >&2
fi
if [[ "$ADMIN_USER_PASSWORD" == "admin" ]]; then
  echo "⚠ La clave del usuario admin es «admin»: solo aceptable en desarrollo local." >&2
fi

# Contraseña maestra: propia y distinta de la del usuario admin (S-04).
MASTER_PASSWORD="${ODOO_MASTER_PASSWORD:-}"
if [[ -n "$MASTER_PASSWORD" && "$MASTER_PASSWORD" == "$ADMIN_USER_PASSWORD" ]]; then
  echo "⚠ ODOO_MASTER_PASSWORD es igual a la clave de admin: se ignora y se usa una aleatoria." >&2
  MASTER_PASSWORD=""
fi
if [[ -z "$MASTER_PASSWORD" ]]; then
  MASTER_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi

cat > "$CONF" <<CONF
[options]
addons_path = ${ODOO_ADDONS_PATH}
data_dir = ${ODOO_DATA_DIR}
db_host = ${DB_HOST}
db_port = ${DB_PORT}
db_user = ${DB_USER}
db_password = ${DB_PASSWORD}
db_name = ${DB_NAME}
db_sslmode = ${DB_SSLMODE}
dbfilter = ^${DB_NAME}\$
list_db = False
admin_passwd = ${MASTER_PASSWORD}
proxy_mode = True
http_interface = 0.0.0.0
http_port = ${ODOO_HTTP_PORT}
workers = 0
max_cron_threads = ${ODOO_CRON_THREADS:-1}
# Con workers = 0 todas las peticiones simultáneas comparten este pool: con 16 se
# medía ~75 % de errores 500 (PoolError) a 20-50 peticiones a la vez. Debe quedar
# por debajo de max_connections de PostgreSQL (ver docs/DESPLIEGUE.md).
db_maxconn = ${ODOO_DB_MAXCONN:-48}
limit_time_real = ${ODOO_LIMIT_TIME_REAL:-300}
log_level = ${ODOO_LOG_LEVEL:-info}
# Búsquedas sin importar tildes: «sofa» encuentra «Sofá», «colchon» encuentra «Colchón».
unaccent = True
CONF
chmod 600 "$CONF"
unset MASTER_PASSWORD

odoo() { python3 "$ODOO_BIN" -c "$CONF" "$@"; }

# odoo-bin shell con un script por stdin. El script debe imprimir «$1» al terminar
# bien: así un fallo (excepción, base caída) nunca pasa por éxito.
odoo_shell() {
  local salida
  salida="$(python3 "$ODOO_BIN" shell -c "$CONF" -d "$DB_NAME" --log-level=warn)" || return 1
  printf '%s\n' "$salida" | grep -vx "$1" || true
  grep -qx "$1" <<<"$salida"
}

export PGPASSWORD="$DB_PASSWORD" PGSSLMODE="$DB_SSLMODE" PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-10}"

# Ejecuta una consulta. Reintenta solo los fallos de CONEXIÓN (psql sale con 2);
# un error de SQL o la conexión caída tras los reintentos devuelven error (y con
# `set -e` abortan el arranque). Código 10: la base de datos no existe todavía.
sql() {
  local intento err rc salida
  err="$(mktemp)"
  for ((intento = 1; intento <= DB_REINTENTOS; intento++)); do
    rc=0
    salida="$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -X -tAq \
      -v ON_ERROR_STOP=1 -c "$1" 2>"$err")" || rc=$?
    if ((rc == 0)); then
      rm -f "$err"
      printf '%s' "$salida"
      return 0
    fi
    if ((rc == 2)) && grep -q "database \"$DB_NAME\" does not exist" "$err"; then
      rm -f "$err"
      return 10
    fi
    if ((rc != 2)); then
      echo "✖ Error de SQL: $(cat "$err")" >&2
      rm -f "$err"
      return "$rc"
    fi
    echo "… PostgreSQL no responde (intento $intento/$DB_REINTENTOS): $(head -n1 "$err")" >&2
    sleep 3
  done
  echo "✖ No hay conexión con PostgreSQL en $DB_HOST:$DB_PORT: no arranco (no asumo base nueva)." >&2
  rm -f "$err"
  return 1
}

set_param() {
  sql "INSERT INTO ir_config_parameter (key, value, create_date, write_date)
       VALUES ('$1', '$2', now(), now())
       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = now()" >/dev/null
}

# --- 2. ¿Qué hay en la base? -------------------------------------------------
# «sin_base»: la base no existe (Odoo la crea); «vacia»: existe sin tablas de Odoo;
# si no, el estado de dcasa_base («installed», «ausente», «to install»…).
rc=0
estado="$(sql "SELECT CASE WHEN to_regclass('public.ir_module_module') IS NULL THEN 'vacia'
  ELSE COALESCE((SELECT state FROM ir_module_module WHERE name = 'dcasa_base'), 'ausente') END")" || rc=$?
if ((rc == 10)); then
  estado="sin_base"
elif ((rc != 0)); then
  exit "$rc"
fi

if [[ "$estado" != "sin_base" ]]; then
  # Extensión para buscar sin tildes (unaccent = True). Si no hay permiso, Odoo busca con tildes.
  sql "CREATE EXTENSION IF NOT EXISTS unaccent" >/dev/null \
    || echo "⚠ No pude crear la extensión unaccent: las búsquedas distinguirán tildes." >&2
fi

# --- 3. Instalar o actualizar ------------------------------------------------
if [[ "$estado" != "installed" ]]; then
  echo "▶ Base nueva ($estado): instalando $ODOO_MODULES ($ODOO_LANG)"
  odoo -d "$DB_NAME" -i "$ODOO_MODULES" --load-language="$ODOO_LANG" --stop-after-init
  set_param dcasa.deployed_version "$APP_VERSION"
else
  deployed="$(sql "SELECT value FROM ir_config_parameter WHERE key = 'dcasa.deployed_version'")"
  if [[ "$deployed" != "$APP_VERSION" ]]; then
    echo "▶ Nueva versión ($deployed → $APP_VERSION): actualizando $ODOO_MODULES"
    # -i instala los módulos nuevos de la lista (p. ej. dcasa_catalogo); en los ya
    # instalados no hace nada. -u actualiza los instalados.
    odoo -d "$DB_NAME" -i "$ODOO_MODULES" -u "$ODOO_MODULES" --stop-after-init
    set_param dcasa.deployed_version "$APP_VERSION"
  fi
fi

# --- 4. Saneo del usuario admin (S-04) ----------------------------------------
# Se comprueba en cada arranque hasta que el marcador exista: si el contenedor muere
# entre la instalación y este paso, el siguiente arranque lo repite antes de abrir
# el puerto. Solo cambia la clave si sigue siendo «admin» (o está vacía).
saneado="$(sql "SELECT value FROM ir_config_parameter WHERE key = 'dcasa.admin_saneado'")"
if [[ "$saneado" != "1" ]]; then
  echo "▶ Saneando el usuario admin"
  ADMIN_USER_PASSWORD="$ADMIN_USER_PASSWORD" odoo_shell DCASA_ADMIN_OK <<'PY' || {
import os
admin = env.ref('base.user_admin', raise_if_not_found=False)
if admin:
    env.cr.execute("SELECT COALESCE(password, '') FROM res_users WHERE id = %s", [admin.id])
    [hashed] = env.cr.fetchone()
    try:
        insegura = not hashed or env['res.users']._crypt_context().verify('admin', hashed)
    except ValueError:
        insegura = True
    if insegura:
        admin.password = os.environ['ADMIN_USER_PASSWORD']
        print('· clave de admin cambiada (tenía la de fábrica)')
    else:
        print('· admin ya tenía una clave propia: no se toca')
env['ir.config_parameter'].sudo().set_param('dcasa.admin_saneado', '1')
env.cr.commit()
print('DCASA_ADMIN_OK')
PY
    echo "✖ No pude sanear el usuario admin: no arranco Odoo con una clave por defecto." >&2
    exit 1
  }
fi

# --- 5. Módulos sobrantes -----------------------------------------------------
# Una vez por versión (también si el arranque anterior murió a mitad). Un fallo se
# registra y no impide arrancar: se reintenta en el siguiente arranque.
revisados="$(sql "SELECT value FROM ir_config_parameter WHERE key = 'dcasa.sobrantes_version'")"
if [[ "${ODOO_DESINSTALAR_SOBRANTES:-1}" != "0" && "$revisados" != "$APP_VERSION" ]]; then
  echo "▶ Revisando módulos sobrantes"
  if DCASA_SOBRANTES="$DCASA_SOBRANTES" DCASA_PROTEGIDOS="$DCASA_PROTEGIDOS" \
    odoo_shell DCASA_SOBRANTES_OK <<'PY'; then
import fnmatch
import os

sobrantes = os.environ['DCASA_SOBRANTES'].split()
protegidos = os.environ['DCASA_PROTEGIDOS'].split()


def coincide(nombre, patrones):
    return any(fnmatch.fnmatchcase(nombre, patron) for patron in patrones)


def protegido(modulo):
    return coincide(modulo.name, protegidos)


Modulo = env['ir.module.module']
instalados = Modulo.search([('state', 'in', ('installed', 'to upgrade'))])
candidatos = instalados.filtered(lambda m: coincide(m.name, sobrantes) and not protegido(m))
# Punto fijo: un sobrante se queda si algo que NO se va depende de él (un módulo
# protegido o uno instalado a propósito); los puentes automáticos se van con él.
for _vuelta in range(100):
    cambio = False
    for modulo in candidatos.sorted('name'):
        dependientes = modulo.downstream_dependencies() - candidatos
        if not dependientes:
            continue
        bloquean = dependientes.filtered(lambda d: protegido(d) or not d.auto_install)
        if bloquean:
            print(f"· se queda {modulo.name}: lo requiere {', '.join(sorted(bloquean.mapped('name')))}")
            candidatos -= modulo
        else:
            print(f"· con {modulo.name} se van: {', '.join(sorted(dependientes.mapped('name')))}")
            candidatos |= dependientes
        cambio = True
        break
    if not cambio:
        break

if candidatos:
    nombres = ', '.join(sorted(candidatos.mapped('name')))
    print(f"· desinstalando {len(candidatos)}: {nombres}")
    try:
        candidatos.button_immediate_uninstall()
    except Exception as error:  # noqa: BLE001 - se registra y se sigue
        env.cr.rollback()
        print(f"· no se pudo desinstalar ({type(error).__name__}: {error}); se reintenta en el próximo arranque")
        raise
else:
    print('· nada que desinstalar')
print('DCASA_SOBRANTES_OK')
PY
    set_param dcasa.sobrantes_version "$APP_VERSION"
  else
    echo "⚠ No se pudieron desinstalar los módulos sobrantes: Odoo arranca igual y se reintenta." >&2
  fi
fi

echo "▶ Iniciando Odoo ($APP_VERSION)"
exec python3 "$ODOO_BIN" -c "$CONF" "$@"
