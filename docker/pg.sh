# shellcheck shell=bash
# PostgreSQL 16 local + archivado continuo de WAL a R2 (pgBackRest) para D'CASA.
#
# Fase 1, opción A (docs/auditoria/DECISION_Y_PLAN.md): Odoo y PostgreSQL viven en el
# mismo Container «basic» con disco EFÍMERO. La durabilidad la da R2: cada segmento de
# WAL se sube al cerrarse (archive_timeout = 60 s ⇒ RPO ≈ 1 min) y cada arranque
# restaura el último respaldo + WAL. Mediciones y hallazgos: docs/auditoria/ronda3/datos.md.
#
# Biblioteca: solo define funciones. La usan, sin duplicar lógica:
#   docker/entrypoint.sh                  arranque del contenedor
#   scripts/respaldo.sh                   respaldos (pgBackRest y pg_dump) bajo demanda o por cron
#   scripts/simulacro_restauracion.sh     simulacro de muerte + restauración (CI)
#
# Variables (todas con valor por defecto salvo las de R2):
#   R2_ENDPOINT            https://<cuenta>.r2.cloudflarestorage.com (admite :puerto)
#   R2_BUCKET              bucket de R2
#   R2_ACCESS_KEY_ID       credenciales S3 de R2 (token con lectura/escritura del bucket)
#   R2_SECRET_ACCESS_KEY
#   PGBACKREST_CIPHER_PASS clave de cifrado del repositorio (aes-256-cbc). NO se puede
#                          cambiar ni perder: sin ella los respaldos no se pueden leer.
#   R2_REGION              «auto» (R2)            R2_VERIFY_TLS   y | n (n solo en pruebas)
#   R2_RUTA_PG             /pgbackrest            ruta del repositorio pgBackRest en el bucket
#   R2_RUTA_DUMP           pg_dump                ruta de los volcados lógicos (red de seguridad)
#   RESPALDO_DUMP_PASS     clave del cifrado de los volcados (por defecto PGBACKREST_CIPHER_PASS)
#   PG_BASE                /var/lib/odoo/pg       todo lo de PostgreSQL vive aquí (disco efímero)
#   PG_PORT                5432 (solo socket unix: no hay TCP)
#   PG_SHARED_BUFFERS      128MB                  PG_MAX_CONNECTIONS  ODOO_DB_MAXCONN + 16
#   PG_VIGILANTE_S         60                     PG_ALERTA_ARCHIVO_S 120
#   PG_APAGADO_ARCHIVO_S   300 (tope de espera del último WAL al apagar; gracia oficial 15 min)
#   RESPALDO_RETENCION_DIAS 7    RESPALDO_FULL_HORAS 24    RESPALDO_INCR_HORAS 6
#   RESPALDO_DUMP_HORAS    24    RESPALDO_DUMP_DIAS  30    RESPALDO_REVISAR_S  3600
#   DCASA_RESTAURAR_HASTA  «2026-10-01 10:42:00-05»: al arrancar restaura HASTA esa hora
#                          (con zona horaria) y promueve: todo lo posterior se descarta.
#                          Se aplica UNA vez (marca en R2_RUTA_CONTROL); quitarla después.

PG_BIN="${PG_BIN:-/usr/lib/postgresql/16/bin}"
PG_BASE="${PG_BASE:-/var/lib/odoo/pg}"
PG_DATA="${PG_DATA:-$PG_BASE/data}"
PG_SOCKET_DIR="${PG_SOCKET_DIR:-$PG_BASE/run}"
PG_PORT="${PG_PORT:-5432}"
PG_STANZA="${PG_STANZA:-dcasa}"
PG_SUPERUSER="postgres"
PG_APP_USER="${PG_APP_USER:-dcasa}"
PGBR_CONF="${PGBR_CONF:-$PG_BASE/pgbackrest.conf}"
PG_ENV_ARCHIVO="${PG_ENV_ARCHIVO:-$PG_BASE/r2.env}"
PG_ALERTA_ARCHIVO="${PG_ALERTA_ARCHIVO:-$PG_BASE/ALERTA_ARCHIVADO}"
# Archivo de log de PostgreSQL. Vacío (por defecto) = la salida estándar de error del contenedor.
# Nunca la ruta del dispositivo stderr: pg_ctl la reabre y en Cloudflare Containers stderr es
# un socket, que no se puede reabrir (ENXIO) y PostgreSQL no arranca. Lo vigila el CI (lint).
PG_LOG="${PG_LOG:-}"
# Lo fija pg_arrancar y lo leen el entrypoint y el simulacro: local | restaurado | nuevo.
PG_ORIGEN=""
export PG_ORIGEN

# Memoria (contenedor basic: 1 GiB, sin swap). Medido en docs/auditoria/ronda3/odoo-medicion.md:
# PostgreSQL con shared_buffers=128MB usa 46-66 MiB (PSS) en reposo/caliente y 150-170 MiB
# bajo 50 peticiones concurrentes; la base pesa ~211 MB (91 MB sin adjuntos), así que 128 MB
# guardan la parte caliente. Odoo: RSS 169 reposo · 216 caliente · 373 tras regenerar
# bundles. Suma de picos ≈ 400 MiB + respaldo (~50) ⇒ queda margen en 1 GiB.
PG_SHARED_BUFFERS="${PG_SHARED_BUFFERS:-128MB}"
# Coherente con db_maxconn de Odoo (48, Fase 0): 48 + 3 reservadas al superusuario + margen
# para pgBackRest, pg_dump, el vigilante y psql del arranque (docs/DESPLIEGUE.md).
PG_MAX_CONNECTIONS="${PG_MAX_CONNECTIONS:-$((${ODOO_DB_MAXCONN:-48} + 16))}"

PG_VIGILANTE_S="${PG_VIGILANTE_S:-60}"
PG_ALERTA_ARCHIVO_S="${PG_ALERTA_ARCHIVO_S:-120}"
PG_APAGADO_ARCHIVO_S="${PG_APAGADO_ARCHIVO_S:-300}"
PG_RESTAURAR_MAX_S="${PG_RESTAURAR_MAX_S:-3600}"
# Mitigación del hallazgo crítico de r3-datos (§2.3): tras promover, el archivado puede
# quedar mudo hasta checkpoint_timeout (5 min). CHECKPOINT inmediato + vigilante.
# Solo se ponen a 0 para demostrar el fallo en el simulacro; nunca en producción.
PG_CHECKPOINT_TRAS_PROMOVER="${PG_CHECKPOINT_TRAS_PROMOVER:-1}"
PG_VIGILANTE_SWITCH="${PG_VIGILANTE_SWITCH:-1}"

RESPALDO_RETENCION_DIAS="${RESPALDO_RETENCION_DIAS:-7}"
RESPALDO_FULL_HORAS="${RESPALDO_FULL_HORAS:-24}"
RESPALDO_INCR_HORAS="${RESPALDO_INCR_HORAS:-6}"
RESPALDO_DUMP_HORAS="${RESPALDO_DUMP_HORAS:-24}"
RESPALDO_DUMP_DIAS="${RESPALDO_DUMP_DIAS:-30}"
RESPALDO_REVISAR_S="${RESPALDO_REVISAR_S:-3600}"
R2_REGION="${R2_REGION:-auto}"
# CI pasa PGBACKREST_REPO1_STORAGE_VERIFY_TLS=n (pgBackRest la lee del entorno); curl la respeta igual.
R2_VERIFY_TLS="${R2_VERIFY_TLS:-${PGBACKREST_REPO1_STORAGE_VERIFY_TLS:-y}}"
R2_RUTA_PG="${R2_RUTA_PG:-/pgbackrest}"
R2_RUTA_DUMP="${R2_RUTA_DUMP:-pg_dump}"
R2_RUTA_CONTROL="${R2_RUTA_CONTROL:-dcasa-control}"
# Restauración a un punto en el tiempo (ver pg_arrancar). Vacía = lo último.
PG_RESTAURAR_HASTA="${DCASA_RESTAURAR_HASTA:-}"

pg_msg() { printf '%s [pg] %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
pg_alerta() { printf '%s [pg] DCASA_ALERTA %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

# Consulta como superusuario por el socket. pg_sql "SQL" [base]
pg_sql() {
  PGOPTIONS="-c client_min_messages=warning" "$PG_BIN/psql" -X -tAq -v ON_ERROR_STOP=1 -h "$PG_SOCKET_DIR" -p "$PG_PORT" \
    -U "$PG_SUPERUSER" -d "${2:-postgres}" -c "$1"
}

pgbr() { pgbackrest --config="$PGBR_CONF" --stanza="$PG_STANZA" "$@"; }
# pgBackRest con la raíz del bucket como repositorio: solo para listar los volcados
# lógicos (repo-ls no sale de repo1-path) con su cliente S3 ya probado contra R2.
pgbr_raiz() { pgbr --repo1-path=/ "$@"; }

pg_postmaster_pid() {
  local pid
  [[ -f "$PG_DATA/postmaster.pid" ]] || return 1
  pid="$(head -n1 "$PG_DATA/postmaster.pid" 2>/dev/null)"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null && printf '%s' "$pid"
}

pg_vivo() { pg_postmaster_pid >/dev/null; }

# --- Configuración ---------------------------------------------------------------

# Valida las variables de R2 y escribe pgbackrest.conf y r2.env (ambos 600). Las
# variables con secretos se borran del entorno después: ni PostgreSQL ni Odoo las heredan.
pg_configurar_repo() {
  local falta=() v
  for v in R2_ENDPOINT R2_BUCKET R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY PGBACKREST_CIPHER_PASS; do
    [[ -n "${!v:-}" ]] || falta+=("$v")
  done
  if ((${#falta[@]})); then
    pg_msg "✖ Faltan variables de R2: ${falta[*]}"
    return 1
  fi
  local hostport="${R2_ENDPOINT#https://}"
  hostport="${hostport#http://}"
  hostport="${hostport%%/*}"
  local host="${hostport%%:*}" puerto=""
  [[ "$hostport" == *:* ]] && puerto="${hostport##*:}"

  mkdir -p "$PG_BASE"/{log,lock,spool,tmp} "$PG_SOCKET_DIR"
  chmod 700 "$PG_BASE" "$PG_SOCKET_DIR"
  umask 077
  cat > "$PGBR_CONF" <<CONF
[global]
repo1-type=s3
repo1-s3-endpoint=${host}
${puerto:+repo1-storage-port=${puerto}}
repo1-storage-verify-tls=${R2_VERIFY_TLS}
repo1-s3-uri-style=path
repo1-s3-bucket=${R2_BUCKET}
repo1-s3-region=${R2_REGION}
repo1-s3-key=${R2_ACCESS_KEY_ID}
repo1-s3-key-secret=${R2_SECRET_ACCESS_KEY}
repo1-path=${R2_RUTA_PG}
repo1-cipher-type=aes-256-cbc
repo1-cipher-pass=${PGBACKREST_CIPHER_PASS}
# Agrupa archivos pequeños en pocos objetos: menos operaciones Clase A/B en R2.
repo1-bundle=y
repo1-retention-full-type=time
repo1-retention-full=${RESPALDO_RETENCION_DIAS}
compress-type=zst
compress-level=3
# 1/4 de vCPU: un proceso; el arranque restaura con 2 (Odoo aún no corre).
process-max=1
start-fast=y
log-path=${PG_BASE}/log
lock-path=${PG_BASE}/lock
spool-path=${PG_BASE}/spool
log-level-console=warn
log-level-stderr=warn
log-level-file=info

[global:restore]
process-max=2

# archive-get asíncrono = precarga en paralelo durante la restauración (RTO). El
# archive-push es SÍNCRONO a propósito: «archivado» significa «ya está en R2».
[global:archive-get]
archive-async=y
process-max=2

[${PG_STANZA}]
pg1-path=${PG_DATA}
pg1-port=${PG_PORT}
pg1-socket-path=${PG_SOCKET_DIR}
pg1-user=${PG_SUPERUSER}
CONF
  {
    printf 'export %s=%q\n' R2_ENDPOINT "$R2_ENDPOINT" R2_BUCKET "$R2_BUCKET" \
      R2_ACCESS_KEY_ID "$R2_ACCESS_KEY_ID" R2_SECRET_ACCESS_KEY "$R2_SECRET_ACCESS_KEY" \
      R2_REGION "$R2_REGION" R2_VERIFY_TLS "$R2_VERIFY_TLS" R2_RUTA_PG "$R2_RUTA_PG" \
      R2_RUTA_DUMP "$R2_RUTA_DUMP" \
      RESPALDO_DUMP_PASS "${RESPALDO_DUMP_PASS:-$PGBACKREST_CIPHER_PASS}"
  } > "$PG_ENV_ARCHIVO"
  umask 022
  # pgBackRest lee las variables PGBACKREST_*: que no compitan con el archivo.
  # (El entrypoint borra el resto de secretos de R2 antes de arrancar Odoo.)
  unset PGBACKREST_CIPHER_PASS
}

# Carga r2.env (lo escribe pg_configurar_repo en el arranque) para los scripts.
pg_cargar_repo() {
  [[ -r "$PG_ENV_ARCHIVO" && -r "$PGBR_CONF" ]] || {
    pg_msg "✖ No existe $PG_ENV_ARCHIVO: el contenedor no arrancó con R2 configurado"
    return 1
  }
  # shellcheck source=/dev/null
  source "$PG_ENV_ARCHIVO"
  # El Worker lanza dcasa-respaldo con el entorno del contenedor: pgBackRest leería
  # PGBACKREST_CIPHER_PASS como opción. La configuración ya está en pgbackrest.conf.
  unset PGBACKREST_CIPHER_PASS
}

# postgresql.conf de D'CASA. Se REESCRIBE en cada arranque (también tras restaurar,
# porque la copia restaurada trae el de la imagen anterior) y se incluye al final de
# postgresql.conf. restore_command lo pone pgBackRest en postgresql.auto.conf.
pg_escribir_conf() {
  local usuario
  usuario="$(id -un)"
  cat > "$PG_DATA/dcasa.conf" <<CONF
# Generado por docker/pg.sh en cada arranque: no editar a mano.
listen_addresses = ''
port = ${PG_PORT}
unix_socket_directories = '${PG_SOCKET_DIR}'
unix_socket_permissions = 0700
max_connections = ${PG_MAX_CONNECTIONS}
superuser_reserved_connections = 3
shared_buffers = ${PG_SHARED_BUFFERS}
huge_pages = off
effective_cache_size = 384MB
work_mem = 4MB
maintenance_work_mem = 32MB
autovacuum_max_workers = 2
jit = off
wal_level = replica
max_wal_senders = 0
wal_compression = zstd
# Segmentos nuevos llenos de ceros: los que cierra archive_timeout casi vacíos se
# comprimen a casi nada en R2 (prototipo r3-datos).
wal_recycle = off
wal_init_zero = on
max_wal_size = 256MB
min_wal_size = 64MB
checkpoint_timeout = 5min
archive_mode = on
archive_command = 'pgbackrest --config=${PGBR_CONF} --stanza=${PG_STANZA} archive-push %p'
archive_timeout = 60
hot_standby = on
logging_collector = off
log_destination = 'stderr'
log_line_prefix = '%m [%p] pg: '
log_checkpoints = on
log_min_duration_statement = 5000
CONF
  grep -qx "include 'dcasa.conf'" "$PG_DATA/postgresql.conf" \
    || printf "\ninclude 'dcasa.conf'\n" >> "$PG_DATA/postgresql.conf"
  # Solo socket unix y solo el usuario del contenedor: peer con mapa a los dos roles.
  printf 'local all all peer map=dcasa\n' > "$PG_DATA/pg_hba.conf"
  printf 'dcasa %s %s\ndcasa %s %s\n' "$usuario" "$PG_SUPERUSER" "$usuario" "$PG_APP_USER" \
    > "$PG_DATA/pg_ident.conf"
}

pg_iniciar() {
  mkdir -p "$PG_SOCKET_DIR"
  chmod 700 "$PG_SOCKET_DIR"
  pg_escribir_conf
  if [[ -n "$PG_LOG" ]]; then
    "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$PG_LOG" -w -t "$PG_RESTAURAR_MAX_S" start >/dev/null
  else
    # Sin -l, pg_ctl lanza postgres con "2>&1" sobre su propia salida estándar: se manda a
    # stderr (heredando el descriptor, sin reabrir ninguna ruta).
    "$PG_BIN/pg_ctl" -D "$PG_DATA" -w -t "$PG_RESTAURAR_MAX_S" start >&2
  fi
}

pg_esperar_promocion() {
  local t0=$SECONDS
  until [[ "$(pg_sql 'SELECT pg_is_in_recovery()' 2>/dev/null)" == "f" ]]; do
    if ((SECONDS - t0 > PG_RESTAURAR_MAX_S)); then
      pg_msg "✖ PostgreSQL no terminó la recuperación en ${PG_RESTAURAR_MAX_S} s"
      return 1
    fi
    pg_vivo || { pg_msg "✖ PostgreSQL murió durante la recuperación"; return 1; }
    sleep 0.2
  done
}

# Estado del repositorio en R2: «con_respaldo», «sin_respaldo» (stanza sin respaldos
# válidos) o «sin_stanza». Si R2 no responde devuelve error: NUNCA se interpreta un
# fallo de red como «base nueva».
# io-timeout corto: si R2 no responde, el arranque falla en ~1 min en vez de reintentar varios.
pg_estado_repo() {
  local json rc=0
  json="$(timeout 90 pgbackrest --config="$PGBR_CONF" --stanza="$PG_STANZA" --io-timeout=20 --output=json info 2>&1)" || rc=$?
  if ((rc != 0)); then
    pg_msg "✖ pgbackrest info falló ($rc): $(tail -n3 <<<"$json")"
    return 1
  fi
  python3 -c '
import json, sys
datos = json.loads(sys.stdin.read())
cod = datos[0]["status"]["code"] if datos else 1
print({0: "con_respaldo", 1: "sin_stanza", 2: "sin_respaldo"}.get(cod, "error:%s %s" % (cod, datos[0]["status"]["message"])))
' <<<"$json"
}

# ¿Hay volcados lógicos en R2? Segunda llave para declarar «base nueva».
pg_hay_dumps() {
  local salida
  salida="$(pgbr_raiz --io-timeout=20 repo-ls "${R2_RUTA_DUMP#/}" 2>&1)" || {
    pg_msg "✖ No pude listar /${R2_RUTA_DUMP#/} en R2: $salida"
    return 2
  }
  [[ -n "$salida" ]]
}

# --- Arranque: restaurar, recuperar o crear ---------------------------------------
# Deja PostgreSQL arrancado, promovido y con el archivado vivo. PG_ORIGEN queda en
# «local» (el directorio de datos sobrevivió: recuperación de choque normal),
# «restaurado» (desde R2), «restaurado_hasta» (a DCASA_RESTAURAR_HASTA) o «nuevo»
# (initdb: R2 vacío).
pg_arrancar() {
  local estado hasta="" marca="" rc
  mkdir -p "$PG_BASE"
  if [[ -f "$PG_BASE/RESTAURANDO" || -f "$PG_BASE/INICIALIZANDO" ]]; then
    pg_msg "⚠ Un arranque anterior quedó a medias: se descarta el directorio de datos"
    rm -rf "$PG_DATA"
  fi

  if [[ -n "$PG_RESTAURAR_HASTA" ]]; then
    hasta="$(pg_normalizar_hasta "$PG_RESTAURAR_HASTA")" || return 1
    marca="$(pg_marca_hasta "$hasta")"
    rc=0
    r2_existe "$marca" || rc=$?
    if ((rc == 0)); then
      pg_msg "⚠ DCASA_RESTAURAR_HASTA=$hasta ya se aplicó antes: se ignora (quita la variable)."
      hasta=""
    elif ((rc == 1)); then
      pg_msg "▶ DCASA_RESTAURAR_HASTA=$hasta: se descarta todo lo posterior a esa hora"
      rm -rf "$PG_DATA"
    else
      pg_msg "✖ No pude consultar R2 para DCASA_RESTAURAR_HASTA"
      return 1
    fi
  fi

  if [[ -f "$PG_DATA/PG_VERSION" ]]; then
    # El disco sobrevivió (reinicio del proceso, no del contenedor). Puede tener WAL que
    # aún no llegó a R2: restaurar desde R2 lo perdería. Recuperación de choque local.
    pg_msg "▶ Directorio de datos presente: arranque con recuperación local"
    pg_iniciar
    pg_esperar_promocion
    PG_ORIGEN="local"
  else
    estado="$(pg_estado_repo)" || return 1
    case "$estado" in
      con_respaldo) pg_restaurar "$hasta" || return 1 ;;
      sin_stanza | sin_respaldo)
        local rc=0
        pg_hay_dumps || rc=$?
        if ((rc == 0)); then
          pg_msg "✖ R2 tiene volcados en /$R2_RUTA_DUMP pero el repositorio pgBackRest está vacío ($estado)."
          pg_msg "  No creo una base nueva encima: revisa R2_RUTA_PG / R2_BUCKET o restaura a mano."
          return 1
        elif ((rc == 2)); then
          return 1
        fi
        if [[ -n "$hasta" ]]; then
          pg_msg "✖ DCASA_RESTAURAR_HASTA pedida pero R2 no tiene respaldos"
          return 1
        fi
        pg_crear_nueva "$estado" || return 1
        ;;
      *)
        pg_msg "✖ Estado del repositorio inesperado: $estado"
        return 1
        ;;
    esac
  fi
  pg_tras_promover
}

# pg_restaurar [HASTA]: sin argumento, último respaldo + todo el WAL (línea de tiempo
# más reciente); con HASTA, recuperación a esa hora (--type=time) y promoción.
pg_restaurar() {
  local t0=$SECONDS objetivo=()
  if [[ -n "${1:-}" ]]; then
    objetivo=(--type=time "--target=$1" --target-action=promote)
    pg_msg "▶ Restaurando desde R2 hasta $1"
  else
    pg_msg "▶ Restaurando desde R2 (último respaldo + WAL)"
  fi
  touch "$PG_BASE/RESTAURANDO"
  rm -rf "$PG_DATA"
  mkdir -p "$PG_DATA"
  chmod 700 "$PG_DATA"
  pgbr --log-level-console=warn "${objetivo[@]}" restore || return 1
  pg_msg "  copia base restaurada en $((SECONDS - t0)) s; aplicando WAL"
  pg_iniciar || return 1
  pg_esperar_promocion || return 1
  rm -f "$PG_BASE/RESTAURANDO"
  PG_ORIGEN="restaurado"
  if [[ -n "${1:-}" ]]; then
    # Marca en R2: un reinicio con la variable aún puesta no vuelve a borrar lo nuevo.
    printf 'aplicada %s\n' "$(date -u +%FT%TZ)" \
      | r2_curl PUT "$(pg_marca_hasta "$1")" --data-binary @- >/dev/null \
      || { pg_msg "✖ No pude guardar la marca de DCASA_RESTAURAR_HASTA en R2"; return 1; }
    PG_ORIGEN="restaurado_hasta"
  fi
  pg_msg "✔ Restaurado y promovido en $((SECONDS - t0)) s"
}

pg_crear_nueva() {
  pg_msg "▶ R2 sin respaldos ($1): base NUEVA (initdb)"
  touch "$PG_BASE/INICIALIZANDO"
  if [[ "$1" == "sin_respaldo" ]]; then
    # stanza creada por un arranque que murió antes del primer respaldo: se rehace
    # (el system-identifier del initdb nuevo no coincidiría).
    pgbr stop || true
    pgbr stanza-delete --force || return 1
    pgbr start || return 1
  fi
  rm -rf "$PG_DATA"
  "$PG_BIN/initdb" -D "$PG_DATA" --data-checksums -E UTF8 --locale=C.UTF-8 \
    -U "$PG_SUPERUSER" --auth-local=peer --auth-host=reject >/dev/null || return 1
  pg_iniciar || return 1
  pgbr --log-level-console=warn stanza-create || return 1
  # check fuerza un cambio de segmento y verifica que llegó a R2 (credenciales, cifrado).
  pgbr --log-level-console=warn check || return 1
  pgbr --log-level-console=warn --type=full backup || return 1
  rm -f "$PG_BASE/INICIALIZANDO"
  PG_ORIGEN="nuevo"
}

pg_tras_promover() {
  if [[ "$PG_CHECKPOINT_TRAS_PROMOVER" == "1" ]]; then
    # Hallazgo crítico r3-datos §2.3: sin esto el archivado queda mudo hasta 5 min.
    pg_sql "CHECKPOINT" >/dev/null || return 1
  fi
  rm -f "$PG_ALERTA_ARCHIVO"
}

# Rol de Odoo (sin superusuario), base y extensiones (lo que Odoo haría si fuera superusuario).
pg_preparar_base() {
  local base="$1"
  pg_sql "DO \$\$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$PG_APP_USER') THEN
        CREATE ROLE \"$PG_APP_USER\" LOGIN;
      END IF;
    END \$\$" >/dev/null || return 1
  if [[ -z "$(pg_sql "SELECT 1 FROM pg_database WHERE datname = '$base'")" ]]; then
    pg_sql "CREATE DATABASE \"$base\" OWNER \"$PG_APP_USER\" ENCODING 'UTF8' LC_COLLATE 'C' TEMPLATE template0" \
      >/dev/null || return 1
  fi
  pg_sql "CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE EXTENSION IF NOT EXISTS unaccent;
          ALTER FUNCTION unaccent(text) IMMUTABLE" "$base" >/dev/null
}

# --- Vigilante del archivado (+ planificador de respaldos) -------------------------
# Cada PG_VIGILANTE_S: si el LSN avanzó desde el último corte, pg_switch_wal() (cierra el
# segmento y lo manda a R2 aunque archive_timeout esté «dormido»). Alerta si hay un
# segmento cerrado sin subir hace más de PG_ALERTA_ARCHIVO_S o si sube failed_count.
# Cada RESPALDO_REVISAR_S lanza «respaldo auto» en segundo plano.
pg_vigilante() {
  local ultimo_lsn="" lsn seg pend_seg="" pend_desde=0 fallos_previos="" fila
  local ultimo_archivado edad fallos ultimo_fallo proxima_revision=$((SECONDS + 120)) resp_pid=""
  local espera=""
  # «sleep & wait»: así el TERM del apagado se atiende al instante, no al acabar el sleep.
  trap '[[ -n "$espera" ]] && kill "$espera" 2>/dev/null; exit 0' TERM INT
  while true; do
    sleep "$PG_VIGILANTE_S" &
    espera=$!
    wait "$espera" || true
    espera=""
    pg_vivo || continue
    fila="$(pg_sql "SELECT pg_current_wal_lsn(), coalesce(last_archived_wal,''),
        coalesce(extract(epoch FROM now() - last_archived_time)::int, -1), failed_count,
        coalesce(last_failed_wal,'') FROM pg_stat_archiver" 2>/dev/null)" || continue
    IFS='|' read -r lsn ultimo_archivado edad fallos ultimo_fallo <<<"$fila"

    if [[ "$PG_VIGILANTE_SWITCH" == "1" && -n "$ultimo_lsn" && "$lsn" != "$ultimo_lsn" ]]; then
      seg="$(pg_sql "SELECT pg_walfile_name(pg_switch_wal())" 2>/dev/null)" || seg=""
      lsn="$(pg_sql "SELECT pg_current_wal_lsn()" 2>/dev/null)" || lsn=""
      if [[ -n "$seg" && -z "$pend_seg" ]]; then
        pend_seg="$seg"
        pend_desde=$SECONDS
      fi
    fi
    ultimo_lsn="$lsn"

    if [[ -n "$pend_seg" && ! "$ultimo_archivado" < "$pend_seg" ]]; then
      pend_seg=""
      rm -f "$PG_ALERTA_ARCHIVO"
    elif [[ -n "$pend_seg" ]] && ((SECONDS - pend_desde > PG_ALERTA_ARCHIVO_S)); then
      pg_alerta "archivado atrasado: $pend_seg sin subir a R2 hace $((SECONDS - pend_desde)) s" \
        "(último archivado $ultimo_archivado hace ${edad} s; fallos $fallos, último $ultimo_fallo)"
      printf '%s pendiente=%s ultimo=%s edad_s=%s fallos=%s\n' "$(date -u +%FT%TZ)" \
        "$pend_seg" "$ultimo_archivado" "$edad" "$fallos" > "$PG_ALERTA_ARCHIVO"
    fi
    if [[ -n "$fallos_previos" && "$fallos" != "$fallos_previos" ]]; then
      pg_alerta "archive-push falló ($fallos fallos acumulados, último $ultimo_fallo)"
    fi
    fallos_previos="$fallos"

    if [[ -n "${PG_RESPALDO_CMD:-}" ]] && ((SECONDS >= proxima_revision)); then
      if [[ -z "$resp_pid" ]] || ! kill -0 "$resp_pid" 2>/dev/null; then
        # shellcheck disable=SC2086
        nice -n 10 $PG_RESPALDO_CMD auto &
        resp_pid=$!
      fi
      proxima_revision=$((SECONDS + RESPALDO_REVISAR_S))
    fi
  done
}

# --- Apagado ordenado (SIGTERM) ----------------------------------------------------
# CHECKPOINT (acorta el apagado) → pg_switch_wal() → espera a que el segmento esté en R2
# (con tope) → pg_ctl stop -m fast. Medido en el prototipo: 0,36 s y 0 commits perdidos.
pg_apagar_ordenado() {
  local seg t0=$SECONDS
  pg_vivo || return 0
  pg_msg "▶ Apagado ordenado de PostgreSQL"
  pg_sql "CHECKPOINT" >/dev/null 2>&1 || true
  seg="$(pg_sql "SELECT pg_walfile_name(pg_switch_wal())" 2>/dev/null)" || seg=""
  if [[ -n "$seg" ]]; then
    until [[ "$(pg_sql "SELECT coalesce(last_archived_wal, '') >= '$seg' FROM pg_stat_archiver" 2>/dev/null)" == "t" ]]; do
      if ((SECONDS - t0 > PG_APAGADO_ARCHIVO_S)); then
        pg_alerta "apagado: $seg no llegó a R2 en ${PG_APAGADO_ARCHIVO_S} s; se apaga igual"
        break
      fi
      sleep 0.2
    done
    pg_msg "  último WAL ($seg) en R2 tras $((SECONDS - t0)) s"
  fi
  "$PG_BIN/pg_ctl" -D "$PG_DATA" -m fast -w -t 120 stop >/dev/null \
    || "$PG_BIN/pg_ctl" -D "$PG_DATA" -m immediate -w stop >/dev/null || true
  pg_msg "✔ PostgreSQL apagado en $((SECONDS - t0)) s"
}

# --- Respaldos ---------------------------------------------------------------------

# Respaldo físico pgBackRest: full | diff | incr. Expira según retención al terminar.
respaldo_fisico() {
  local tipo="$1" t0=$SECONDS
  pg_msg "▶ Respaldo pgBackRest $tipo"
  pgbr --log-level-console=warn --type="$tipo" backup || {
    pg_alerta "respaldo $tipo falló"
    return 1
  }
  pg_msg "✔ Respaldo $tipo en $((SECONDS - t0)) s"
}

# Decide qué toca: full si el último completo tiene ≥ RESPALDO_FULL_HORAS (o el 1.er
# argumento); incr si el último respaldo tiene ≥ RESPALDO_INCR_HORAS o es de otra línea de
# tiempo (tras una restauración: acorta el WAL a reproducir en la próxima). Imprime
# full|incr|nada.
respaldo_que_toca() {
  local json tl full_horas="${1:-$RESPALDO_FULL_HORAS}"
  json="$(pgbr --output=json info)" || return 1
  tl="$(pg_sql "SELECT timeline_id FROM pg_control_checkpoint()")" || return 1
  RF="$full_horas" RI="$RESPALDO_INCR_HORAS" TL="$tl" python3 -c '
import json, os, sys, time
datos = json.loads(sys.stdin.read())
respaldos = datos[0].get("backup", []) if datos else []
ahora = time.time()
completos = [b for b in respaldos if b["type"] == "full"]
if not completos or ahora - completos[-1]["timestamp"]["stop"] >= float(os.environ["RF"]) * 3600:
    print("full")
else:
    ultimo = respaldos[-1]
    tl = int(ultimo["archive"]["start"][:8], 16)
    viejo = ahora - ultimo["timestamp"]["stop"] >= float(os.environ["RI"]) * 3600
    print("incr" if viejo or tl != int(os.environ["TL"]) else "nada")
' <<<"$json"
}

# Volcado lógico independiente de pgBackRest: pg_dump -Fc con zstd, cifrado con openssl
# y subido por HTTPS firmado (SigV4) a R2_RUTA_DUMP. Borra los de más de RESPALDO_DUMP_DIAS.
# Restaurar:  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:RESPALDO_DUMP_PASS \
#               -in X.dump.enc | pg_restore -d <base> --no-owner
respaldo_dump() {
  local base="$1" sello archivo clave t0=$SECONDS
  sello="$(date -u +%Y%m%dT%H%M%SZ)"
  archivo="$PG_BASE/tmp/$base-$sello.dump.enc"
  clave="${R2_RUTA_DUMP#/}/$base-$sello.dump.enc"
  mkdir -p "$PG_BASE/tmp"
  pg_msg "▶ Volcado lógico de $base"
  if ! (
    set -o pipefail
    "$PG_BIN/pg_dump" -h "$PG_SOCKET_DIR" -p "$PG_PORT" -U "$PG_SUPERUSER" -Fc -Z zstd:3 "$base" \
      | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:RESPALDO_DUMP_PASS -out "$archivo"
  ); then
    rm -f "$archivo"
    pg_alerta "pg_dump de $base falló"
    return 1
  fi
  if ! r2_curl PUT "$clave" -T "$archivo" >/dev/null; then
    rm -f "$archivo"
    pg_alerta "no pude subir el volcado $clave a R2"
    return 1
  fi
  RESPALDO_DUMP_ULTIMO="${clave##*/} ($(du -k "$archivo" | cut -f1) KiB)"
  pg_msg "✔ Volcado $RESPALDO_DUMP_ULTIMO en $((SECONDS - t0)) s"
  rm -f "$archivo"
  respaldo_dump_podar "$base"
}

# Lista los volcados (nombre por línea, ascendente) usando el cliente S3 de pgBackRest.
respaldo_dump_listar() { pgbr_raiz repo-ls "${R2_RUTA_DUMP#/}" --filter="^$1-.*\\.dump\\.enc\$"; }

respaldo_dump_podar() {
  local corte nombre
  corte="$(date -u -d "-${RESPALDO_DUMP_DIAS} days" +%Y%m%dT%H%M%SZ)"
  while read -r nombre; do
    [[ -n "$nombre" ]] || continue
    local sello="${nombre#"$1"-}"
    sello="${sello%.dump.enc}"
    if [[ "$sello" < "$corte" ]]; then
      r2_curl DELETE "${R2_RUTA_DUMP#/}/$nombre" >/dev/null && pg_msg "  volcado viejo borrado: $nombre"
    fi
  done < <(respaldo_dump_listar "$1")
}

# ¿Toca volcado? (el último tiene ≥ RESPALDO_DUMP_HORAS o no hay ninguno)
respaldo_dump_toca() {
  local ultimo sello limite
  ultimo="$(respaldo_dump_listar "$1" | tail -n1)" || return 2
  [[ -z "$ultimo" ]] && return 0
  sello="${ultimo#"$1"-}"
  sello="${sello%.dump.enc}"
  limite="$(date -u -d "-${RESPALDO_DUMP_HORAS} hours" +%Y%m%dT%H%M%SZ)"
  [[ ! "$sello" > "$limite" ]]
}

# «2026-10-01T10:42:00-05:00» → «2026-10-01 10:42:00-05:00». Exige zona horaria (en
# Panamá -05): una hora sin zona se interpretaría en UTC sin avisar.
pg_normalizar_hasta() {
  local t="${1/T/ }"
  if [[ "$t" == *Z ]]; then
    t="${t%Z}+00"
  fi
  if [[ ! "$t" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?[+-][0-9]{2}(:?[0-9]{2})?$ ]]; then
    pg_msg "✖ DCASA_RESTAURAR_HASTA inválida («$1»): usa AAAA-MM-DD HH:MM:SS-05 (con zona horaria)"
    return 1
  fi
  printf '%s' "$t"
}

pg_marca_hasta() { printf '%s/pitr-aplicada-%s' "${R2_RUTA_CONTROL#/}" "${1//[^0-9A-Za-z]/_}"; }

# ¿Existe el objeto en R2? 0 sí · 1 no · 2 error (no se sabe).
r2_existe() {
  local codigo
  codigo="$(r2_curl HEAD "$1" --no-fail -o /dev/null -w '%{http_code}' 2>/dev/null)" || true
  case "$codigo" in
    200) return 0 ;;
    404) return 1 ;;
    *) return 2 ;;
  esac
}

# Petición S3 firmada (SigV4) a R2 con curl. r2_curl MÉTODO CLAVE [opciones de curl]
# Las credenciales van por un archivo de configuración de curl, no por la línea de
# comandos (no aparecen en /proc/*/cmdline).
r2_curl() {
  local metodo="$1" clave="$2" tls=() falla=(--fail-with-body)
  shift 2
  [[ "$R2_VERIFY_TLS" == "n" ]] && tls=(-k)
  if [[ "${1:-}" == "--no-fail" ]]; then
    falla=()
    shift
  fi
  if [[ -z "${R2_SECRET_ACCESS_KEY:-}" && -r "$PG_ENV_ARCHIVO" ]]; then
    # shellcheck source=/dev/null
    source "$PG_ENV_ARCHIVO"
  fi
  [[ "$metodo" == HEAD ]] && tls+=(-I)
  curl -sS "${falla[@]}" --retry 3 --retry-delay 2 --connect-timeout 20 --max-time 1800 \
    "${tls[@]}" -K <(printf 'user = "%s:%s"\n' "$R2_ACCESS_KEY_ID" "$R2_SECRET_ACCESS_KEY") \
    --aws-sigv4 "aws:amz:${R2_REGION}:s3" -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
    -X "$metodo" "${R2_ENDPOINT%/}/$R2_BUCKET/$clave" "$@"
}
