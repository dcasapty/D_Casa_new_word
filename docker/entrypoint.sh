#!/usr/bin/env bash
# Arranque del contenedor de D'CASA: PostgreSQL 16 local + Odoo 19 (Fase 1, opción A).
#
# 0. PostgreSQL local (docker/pg.sh): si R2 tiene respaldos, restaura el último + WAL,
#    promueve y hace CHECKPOINT (sin él el archivado queda mudo hasta 5 min tras
#    restaurar: docs/auditoria/ronda3/datos.md §2.3); si R2 está vacío, initdb + respaldo.
#    Archivado continuo de WAL a R2 (archive_timeout 60 s ⇒ RPO ≈ 1 min) y un vigilante
#    que fuerza pg_switch_wal(), alerta si el archivado se atrasa y lanza los respaldos.
#    Si R2 no responde o la restauración falla, el contenedor sale con código ≠ 0:
#    nunca se crea una base vacía cuando R2 tiene respaldos.
# 1. Genera odoo.conf a partir de variables de entorno (sin secretos en la imagen).
# 2. Base nueva  -> instala los módulos de D'CASA con español (+ respaldo completo).
#    Base existente con otra versión de la imagen -> actualiza los módulos de D'CASA.
# 3. Saneo del usuario admin (idempotente, en CADA arranque hasta que quede hecho):
#    si admin sigue con la clave «admin», se cambia antes de abrir el puerto.
# 4. web.base.url = https://CANONICAL_HOST, congelada.
# 5. Desinstala los módulos de Odoo que D'CASA no usa (idempotente, una vez por versión).
# 6. Arranca Odoo en modo multihilo (un solo puerto: HTTP + websocket). El puerto 8069
#    solo se abre con la base ya restaurada (edge/CONTRATO_CONTENEDOR.md).
# 7. SIGTERM: para Odoo → CHECKPOINT → pg_switch_wal() → espera el último WAL en R2
#    (tope PG_APAGADO_ARCHIVO_S) → pg_ctl stop -m fast. Si Odoo muere solo, se relanza
#    sin tocar PostgreSQL; si PostgreSQL muere, recuperación local y sigue.
#
# Variables:
#   ADMIN_PASSWORD        clave del usuario admin de Odoo (obligatoria). Se fija solo
#                         si admin aún tiene la clave «admin» (base nueva o arranque
#                         interrumpido); nunca pisa una clave que el dueño ya cambió.
#   R2_ENDPOINT, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, PGBACKREST_CIPHER_PASS
#                         repositorio de respaldos en R2 (obligatorias en modo local; las
#                         opcionales R2_* / RESPALDO_* / PG_* están en docker/pg.sh).
#   CANONICAL_HOST        dominio público (dcasapty.com): fija web.base.url.
#   DB_NAME               nombre de la base (por defecto dcasa).
#   DB_MODO               «local» (por defecto si no hay DB_HOST) o «externo»: PostgreSQL
#                         ajeno en DB_HOST/DB_USER/DB_PASSWORD (CI y vista previa).
#   ADMIN_USER_PASSWORD   (opcional) reemplaza a ADMIN_PASSWORD para el usuario admin.
#   ODOO_MASTER_PASSWORD  (opcional) contraseña maestra (admin_passwd), distinta de la
#                         de admin. Si falta, se genera una aleatoria en cada arranque
#                         y no se muestra: el gestor de bases está cerrado
#                         (list_db = False y bloqueado en el borde), así que no hace falta.
#   ODOO_DB_MAXCONN       conexiones a PostgreSQL del proceso de Odoo (por defecto 48;
#                         ver docs/DESPLIEGUE.md → «Conexiones a PostgreSQL»).
#   ODOO_LIMIT_MEMORY_SOFT / ODOO_LIMIT_MEMORY_HARD  bytes de memoria VIRTUAL (ver odoo.conf).
#   DB_REINTENTOS         intentos de conexión a PostgreSQL al arrancar (por defecto 20, cada 3 s).
#   ODOO_DESINSTALAR_SOBRANTES  0 para no desinstalar los módulos sobrantes.
set -euo pipefail

: "${ADMIN_PASSWORD:?Falta ADMIN_PASSWORD (clave del usuario admin de Odoo)}"
DB_NAME="${DB_NAME:-dcasa}"
if [[ -z "${DB_MODO:-}" ]]; then
  DB_MODO="local"
  [[ -n "${DB_HOST:-}" ]] && DB_MODO="externo"
fi
ENTRYPOINT_T0=$SECONDS
ODOO_PID=""
VIG_PID=""
APAGANDO=0
INSTALADA=0

if [[ "$DB_MODO" == "local" ]]; then
  for lib in "${DCASA_PG_LIB:-}" /usr/local/lib/dcasa/pg.sh "$(dirname "$(readlink -f "$0")")/pg.sh"; do
    if [[ -n "$lib" && -r "$lib" ]]; then
      # shellcheck source=docker/pg.sh
      source "$lib"
      break
    fi
  done
  declare -F pg_arrancar >/dev/null || { echo "✖ No encuentro docker/pg.sh" >&2; exit 1; }
  if [[ -z "${PG_RESPALDO_CMD:-}" ]]; then
    PG_RESPALDO_CMD="$(command -v dcasa-respaldo || true)"
    PG_RESPALDO_CMD="${PG_RESPALDO_CMD:-$(dirname "$(readlink -f "$0")")/../scripts/respaldo.sh}"
  fi
  export DB_NAME PG_RESPALDO_CMD

  # Apagado ordenado: Odoo primero (deja de escribir), luego PostgreSQL con el último
  # WAL ya en R2. Se usa en SIGTERM, en errores del arranque y si todo se cae.
  apagar() {
    ((APAGANDO)) && return 0
    APAGANDO=1
    trap - TERM INT
    if [[ -n "$ODOO_PID" ]] && kill -0 "$ODOO_PID" 2>/dev/null; then
      echo "▶ Deteniendo Odoo"
      kill -TERM "$ODOO_PID" 2>/dev/null || true
      local i
      for ((i = 0; i < ${ODOO_PARADA_S:-60} * 5; i++)); do
        kill -0 "$ODOO_PID" 2>/dev/null || break
        sleep 0.2
      done
      kill -KILL "$ODOO_PID" 2>/dev/null || true
    fi
    if [[ -n "$VIG_PID" ]]; then
      kill -TERM "$VIG_PID" 2>/dev/null || true
      wait "$VIG_PID" 2>/dev/null || true
    fi
    pg_apagar_ordenado
  }
  trap 'echo "▶ SIGTERM: apagado ordenado"; apagar; exit 143' TERM INT
  trap 'rc=$?; apagar; exit $rc' EXIT

  echo "▶ PostgreSQL local (${DCASA_ENTORNO:-produccion}); respaldos en R2: ${R2_BUCKET:-?}${R2_RUTA_PG:-/pgbackrest}"
  pg_configurar_repo
  if ! pg_arrancar; then
    echo "✖ PostgreSQL no arrancó (restauración o R2): el contenedor sale con error." >&2
    exit 1
  fi
  pg_preparar_base "$DB_NAME"
  echo "✔ PostgreSQL listo ($PG_ORIGEN) en $((SECONDS - ENTRYPOINT_T0)) s"
  # Odoo no hereda nada de R2: las credenciales quedan solo en archivos 600 de PG_BASE.
  unset R2_ENDPOINT R2_BUCKET R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY PGBACKREST_CIPHER_PASS RESPALDO_DUMP_PASS
  DB_HOST="$PG_SOCKET_DIR"
  DB_PORT="$PG_PORT"
  DB_USER="$PG_APP_USER"
  DB_PASSWORD=""
  DB_SSLMODE="disable"
else
  : "${DB_HOST:?Falta DB_HOST}"
  : "${DB_USER:?Falta DB_USER}"
  : "${DB_PASSWORD:?Falta DB_PASSWORD}"
fi

DB_PORT="${DB_PORT:-5432}"
DB_SSLMODE="${DB_SSLMODE:-prefer}"
DB_REINTENTOS="${DB_REINTENTOS:-20}"
ODOO_MODULES="${ODOO_MODULES:-dcasa_base,dcasa_invoice,dcasa_socios,website_dcasa,dcasa_catalogo,dcasa_interfaz,dcasa_contabilidad,dcasa_brian,dcasa_sesiones}"
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
${DB_PASSWORD:+db_password = ${DB_PASSWORD}}
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
# Sesiones HTTP en la base (dcasa_sesiones): el disco del contenedor es efímero.
server_wide_modules = base,web,dcasa_sesiones
limit_time_real = ${ODOO_LIMIT_TIME_REAL:-300}
# En modo hilos Odoo compara limit_memory_soft con la memoria VIRTUAL del proceso
# (odoo/tools/osutil.py: vms), no con la RSS. Medido (odoo-medicion y BITACORA): VmSize
# 368 MiB caliente y ~790 MiB con 50 peticiones simultáneas, con RSS de solo 229-273 MiB;
# al 45 % de 1 GiB (460 MiB) Odoo se reiniciaba en bucle. Soft 1,5 GiB ≈ 2× el pico
# medido: reinicio limpio (al terminar la petición) solo ante una fuga real. Hard 2 GiB
# (RLIMIT_AS) corta un desborde antes de que el OOM del contenedor alcance a PostgreSQL;
# además Odoo corre con oom_score_adj 500 para que el kernel lo elija a él primero.
limit_memory_soft = ${ODOO_LIMIT_MEMORY_SOFT:-1610612736}
limit_memory_hard = ${ODOO_LIMIT_MEMORY_HARD:-2147483648}
log_level = ${ODOO_LOG_LEVEL:-info}
# Sin una línea por petición (werkzeug a WARNING): cada línea es un evento de Workers Logs
# (20 M/mes incluidos) y el Worker ya registra cada invocación con su estado. Los errores
# de Odoo (500, excepciones) salen por odoo.http a ERROR con su traza: no se pierden.
# Para depurar: ODOO_LOG_HANDLER=werkzeug:INFO.
log_handler = ${ODOO_LOG_HANDLER:-werkzeug:WARNING}
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

# --- ¿Qué hay en la base? ----------------------------------------------------
# «sin_base»: la base no existe (Odoo la crea); «vacia»: existe sin tablas de Odoo;
# si no, el estado de dcasa_base («installed», «ausente», «to install»…).
# Dos consultas: en una sola, PostgreSQL resuelve ir_module_module al planificar y falla
# con la base vacía que crea el modo local (antes Odoo creaba la base: «sin_base»).
rc=0
estado="$(sql "SELECT CASE WHEN to_regclass('public.ir_module_module') IS NULL THEN 'vacia' ELSE 'odoo' END")" || rc=$?
if ((rc == 10)); then
  estado="sin_base"
elif ((rc != 0)); then
  exit "$rc"
elif [[ "$estado" == "odoo" ]]; then
  estado="$(sql "SELECT COALESCE((SELECT state FROM ir_module_module WHERE name = 'dcasa_base'), 'ausente')")"
fi

if [[ "$estado" != "sin_base" ]]; then
  # Extensión para buscar sin tildes (unaccent = True). Si no hay permiso, Odoo busca con tildes.
  sql "CREATE EXTENSION IF NOT EXISTS unaccent" >/dev/null \
    || echo "⚠ No pude crear la extensión unaccent: las búsquedas distinguirán tildes." >&2
fi

# --- 2. Instalar o actualizar ------------------------------------------------
if [[ "$estado" != "installed" ]]; then
  echo "▶ Base nueva ($estado): instalando $ODOO_MODULES ($ODOO_LANG)"
  odoo -d "$DB_NAME" -i "$ODOO_MODULES" --load-language="$ODOO_LANG" --stop-after-init
  set_param dcasa.deployed_version "$APP_VERSION"
  INSTALADA=1
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

# --- 3. Saneo del usuario admin (S-04) ----------------------------------------
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

# --- 4. URL canónica -----------------------------------------------------------
# web.base.url fija y congelada: sin freeze, Odoo la reescribe con el Host de la
# primera petición de un administrador (p. ej. la URL interna del contenedor).
if [[ -n "${CANONICAL_HOST:-}" ]]; then
  url="$CANONICAL_HOST"
  [[ "$url" == http://* || "$url" == https://* ]] || url="https://$url"
  url="${url%/}"
  if [[ "$url" =~ ^https?://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]; then
    set_param web.base.url "$url"
    set_param web.base.url.freeze True
    echo "▶ web.base.url = $url (congelada)"
  else
    echo "⚠ CANONICAL_HOST no es un dominio válido («$CANONICAL_HOST»): no toco web.base.url." >&2
  fi
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

if [[ "$DB_MODO" != "local" ]]; then
  echo "▶ Iniciando Odoo ($APP_VERSION)"
  exec python3 "$ODOO_BIN" -c "$CONF" "$@"
fi

# --- 6. Modo local: primer respaldo, vigilante y Odoo supervisado ---------------
if [[ "$INSTALADA" == "1" ]]; then
  # Base recién instalada: copia completa ya, para no depender de reproducir el WAL
  # de toda la instalación en la próxima restauración.
  respaldo_fisico full || echo "⚠ El primer respaldo completo falló: lo reintenta el vigilante." >&2
fi
pg_vigilante &
VIG_PID=$!

iniciar_odoo() {
  # oom_score_adj 500: ante falta de memoria el kernel mata a Odoo (se relanza aquí)
  # y no a PostgreSQL (eso obligaría a restaurar). Subirlo no requiere privilegios.
  (
    echo 500 >/proc/self/oom_score_adj 2>/dev/null || true
    exec python3 "$ODOO_BIN" -c "$CONF" "$@"
  ) &
  ODOO_PID=$!
}

# Memoria real (cgroup: anónima vs caché; RSS/PSS de Odoo y PostgreSQL; contadores de OOM)
# en UNA línea JSON {"evento":"memoria",...}: una vez con Odoo ya caliente tras arrancar
# y cada vez que Odoo se cae (¿fue un OOM?). El panel de Cloudflare no separa la caché.
DCASA_MEMORIA="${DCASA_MEMORIA:-/opt/dcasa/addons/dcasa_base/memoria.py}"
MEMORIA_TRAS_S="${MEMORIA_TRAS_S:-180}"
registrar_memoria() {
  [[ -r "$DCASA_MEMORIA" ]] && python3 "$DCASA_MEMORIA" "$1" 2>/dev/null || true
}

echo "▶ Iniciando Odoo ($APP_VERSION) tras $((SECONDS - ENTRYPOINT_T0)) s de arranque"
iniciar_odoo "$@"
caidas=()
memoria_en=$((SECONDS + MEMORIA_TRAS_S))
while true; do
  sleep 5 &
  wait $! || true
  if ((memoria_en > 0 && SECONDS >= memoria_en)); then
    registrar_memoria arranque
    memoria_en=0
  fi
  if ! pg_vivo; then
    pg_alerta "PostgreSQL se detuvo: recuperación local"
    if ! { pg_iniciar && pg_esperar_promocion && pg_tras_promover; }; then
      echo "✖ PostgreSQL no vuelve: el contenedor sale (el próximo arranque restaura desde R2)." >&2
      exit 1
    fi
  fi
  if ! kill -0 "$ODOO_PID" 2>/dev/null; then
    rc=0
    wait "$ODOO_PID" || rc=$?
    ahora=$SECONDS
    recientes=()
    for t in "${caidas[@]}"; do
      ((ahora - t < 600)) && recientes+=("$t")
    done
    caidas=("${recientes[@]}" "$ahora")
    if ((${#caidas[@]} > ${ODOO_REINICIOS_MAX:-5})); then
      echo "✖ Odoo terminó ${#caidas[@]} veces en 10 min (último código $rc): salgo." >&2
      exit 1
    fi
    pg_alerta "Odoo terminó (código $rc): se relanza (${#caidas[@]} en 10 min)"
    registrar_memoria odoo_caido
    iniciar_odoo "$@"
  fi
done
