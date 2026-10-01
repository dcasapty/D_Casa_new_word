#!/usr/bin/env bash
# Simulacro de muerte del contenedor y restauración desde «R2» (Fase 1, opción A).
#
# Sin Docker ni Cloudflare: levanta un S3 local (moto detrás de stunnel, porque pgBackRest
# exige HTTPS) en un puerto libre 9120-9129 y un PostgreSQL 16 efímero con EXACTAMENTE la
# configuración de la imagen (usa las funciones de docker/pg.sh, las mismas que el
# entrypoint, y scripts/respaldo.sh). Ciclos:
#   1. base nueva → datos de referencia → respaldo completo → carga continua →
#      kill -9 de todo PostgreSQL (y pgBackRest y el vigilante) → borrado del disco →
#      restauración → verificación.
#   2. igual, pero arrancando desde la base RESTAURADA: es donde r3-datos midió el
#      archivado mudo hasta 5 min tras la promoción (docs/auditoria/ronda3/datos.md §2.3).
#   3. respaldo «auto» (debe hacer incr por cambio de línea de tiempo + volcado lógico).
#   4. apagado ORDENADO (lo que hace el SIGTERM del contenedor) → borrado → restauración:
#      0 pérdidas.
#   5. el volcado lógico de R2 se descarga, descifra y restaura en otra base.
#   6. DCASA_RESTAURAR_HASTA: vuelta a una hora concreta; un segundo arranque con la
#      variable aún puesta NO vuelve a aplicarla.
# Verifica en cada restauración: filas corruptas, huecos, md5 de la tabla de referencia,
# pg_amcheck (heap + índices; la base usa data checksums), RPO y RTO.
#
# Sale con código ≠ 0 si el RPO supera SIMULACRO_RPO_MAX_S (90 s), si se pierde algo en el
# apagado ordenado, si la vuelta a una hora no cuadra o si hay cualquier corrupción.
#
# Requisitos: PostgreSQL 16 (servidor y cliente en PG_BIN), pgbackrest, stunnel4, openssl,
# curl, python3; moto (moto_server en el PATH, SIMULACRO_MOTO=ruta, o lo instala con pip).
# Si se ejecuta como root, se relanza como el usuario SIMULACRO_USUARIO (postgres).
#
# Variables: SIMULACRO_CARGA_S="150 105 30"  segundos de carga de los ciclos 1, 2 y 4 (no múltiplos de 60: así la muerte no coincide con un corte de segmento)
#            SIMULACRO_FILAS=200000           filas de la tabla de referencia (~50 MB)
#            SIMULACRO_INTERVALO=0.5          segundos entre asientos
#            SIMULACRO_RPO_MAX_S=90
#            SIMULACRO_DIR                    directorio de trabajo; si se da, se conservan
#                                             ahí los registros (resumen.txt, postgresql.log,
#                                             pgBackRest) y se borran solo los datos
#            SIMULACRO_CONSERVAR=1            no borra nada
set -euo pipefail

if ((EUID == 0)); then
  usuario="${SIMULACRO_USUARIO:-postgres}"
  echo "▶ Soy root: me relanzo como $usuario (PostgreSQL no corre como root)"
  exec runuser -u "$usuario" -- "$(readlink -f "$0")" "$@"
fi

ROOT="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
read -r -a CARGAS <<<"${SIMULACRO_CARGA_S:-150 105 30}"
FILAS="${SIMULACRO_FILAS:-200000}"
INTERVALO="${SIMULACRO_INTERVALO:-0.5}"
RPO_MAX="${SIMULACRO_RPO_MAX_S:-90}"
DIR_PROPIO=0
if [[ -z "${SIMULACRO_DIR:-}" ]]; then
  SIMULACRO_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dcasa-simulacro.XXXXXX")"
  DIR_PROPIO=1
fi
mkdir -p "$SIMULACRO_DIR"
SIM_DIR="$(cd "$SIMULACRO_DIR" && pwd)"
BASE_SIM="simdb"

libre() {  # primer puerto TCP libre en [desde, hasta]
  local p
  for ((p = $1; p <= $2; p++)); do
    if ! (exec 3<>"/dev/tcp/127.0.0.1/$p") 2>/dev/null; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

S3_TLS="$(libre 9120 9129)" || { echo "✖ No hay puerto libre 9120-9129" >&2; exit 1; }
S3_HTTP="$(libre $((S3_TLS + 1)) 9129)" || { echo "✖ No hay segundo puerto libre 9120-9129" >&2; exit 1; }

# Entorno del «contenedor», como lo pasa el Worker (edge/CONTRATO_CONTENEDOR.md §3) y
# como lo usa la prueba de humo de CI (TLS autofirmado vía PGBACKREST_REPO1_STORAGE_VERIFY_TLS).
# Se guarda aparte porque pg_configurar_repo borra PGBACKREST_CIPHER_PASS, como en la imagen.
R2_VARS=(
  "R2_ENDPOINT=https://127.0.0.1:$S3_TLS" "R2_BUCKET=dcasa-simulacro"
  "R2_ACCESS_KEY_ID=simulacro" "R2_SECRET_ACCESS_KEY=simulacro-secreto"
  "PGBACKREST_CIPHER_PASS=simulacro-clave-de-cifrado" "PGBACKREST_REPO1_STORAGE_VERIFY_TLS=n"
)
exportar_r2() { export "${R2_VARS[@]}"; }
exportar_r2

# --- PostgreSQL: misma biblioteca y configuración que la imagen ---------------------
export PG_BASE="$SIM_DIR/contenedor/pg"            # «disco efímero del contenedor»
PG_PORT="$(libre 5460 5469)" || { echo "✖ No hay puerto libre 5460-5469" >&2; exit 1; }
export PG_PORT PG_LOG="$SIM_DIR/postgresql.log" DB_NAME="$BASE_SIM"
export DCASA_PG_LIB="$ROOT/docker/pg.sh"
# shellcheck source=docker/pg.sh
source "$DCASA_PG_LIB"

MOTO="${SIMULACRO_MOTO:-$(command -v moto_server || true)}"
STUNNEL="$(command -v stunnel4 || command -v stunnel || true)"
[[ -n "$STUNNEL" ]] || { echo "✖ Falta stunnel4" >&2; exit 1; }
for b in pg_ctl initdb psql pg_dump pg_restore pg_amcheck; do
  [[ -x "$PG_BIN/$b" ]] || { echo "✖ Falta $PG_BIN/$b (PostgreSQL 16)" >&2; exit 1; }
done
command -v pgbackrest >/dev/null || { echo "✖ Falta pgbackrest" >&2; exit 1; }

PIDS_AUX=()
VIG_PID=""
# shellcheck disable=SC2317,SC2329  # se invoca desde trap EXIT (SC2317 en shellcheck < 0.10)
limpiar() {
  local rc=$?
  set +e
  [[ -n "$VIG_PID" ]] && kill "$VIG_PID" 2>/dev/null
  if pg_vivo; then "$PG_BIN/pg_ctl" -D "$PG_DATA" -m immediate -w stop >/dev/null 2>&1; fi
  [[ -f "$SIM_DIR/stunnel.pid" ]] && kill "$(cat "$SIM_DIR/stunnel.pid")" 2>/dev/null
  ((${#PIDS_AUX[@]})) && kill "${PIDS_AUX[@]}" 2>/dev/null
  wait 2>/dev/null
  if [[ "${SIMULACRO_CONSERVAR:-0}" == "1" ]]; then
    echo "· directorio conservado: $SIM_DIR"
  elif ((DIR_PROPIO)); then
    rm -rf "$SIM_DIR"
  else
    # Registros para CI; fuera los datos y las claves.
    [[ -d "$PG_BASE/log" ]] && cp -r "$PG_BASE/log" "$SIM_DIR/pgbackrest-log"
    rm -rf "$SIM_DIR/contenedor" "$SIM_DIR/dump.enc" "$SIM_DIR/s3.key"
    echo "· registros en $SIM_DIR"
  fi
  exit "$rc"
}
trap limpiar EXIT
trap 'echo "✖ Error en la línea $LINENO del simulacro" >&2' ERR

if [[ -z "$MOTO" ]]; then
  echo "▶ Instalando moto en un venv (una vez)"
  CACHE="${SIMULACRO_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/dcasa-simulacro}"
  [[ -x "$CACHE/venv/bin/moto_server" ]] || {
    python3 -m venv "$CACHE/venv"
    "$CACHE/venv/bin/pip" install -q "moto[server]>=5,<6"
  }
  MOTO="$CACHE/venv/bin/moto_server"
fi
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$SIM_DIR/s3.key" -out "$SIM_DIR/s3.crt" -days 2 \
  -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1" 2>/dev/null
"$MOTO" -H 127.0.0.1 -p "$S3_HTTP" >"$SIM_DIR/moto.log" 2>&1 &
PIDS_AUX+=($!)
cat >"$SIM_DIR/stunnel.conf" <<CONF
foreground = no
pid = $SIM_DIR/stunnel.pid
output = $SIM_DIR/stunnel.log
[s3]
accept = 127.0.0.1:$S3_TLS
connect = 127.0.0.1:$S3_HTTP
cert = $SIM_DIR/s3.crt
key = $SIM_DIR/s3.key
CONF
"$STUNNEL" "$SIM_DIR/stunnel.conf"

for _ in $(seq 1 50); do
  R2_REGION=us-east-1 r2_curl PUT "" >/dev/null 2>&1 && break  # moto crea buckets solo en us-east-1
  sleep 0.2
done
r2_curl HEAD "" >/dev/null || { echo "✖ El S3 local no responde" >&2; exit 1; }
echo "▶ S3 local en https://127.0.0.1:$S3_TLS · PostgreSQL en el socket $PG_BASE/run (puerto $PG_PORT)"

# «Arranque del contenedor»: lo mismo que hace docker/entrypoint.sh en modo local.
arrancar_contenedor() {
  exportar_r2
  pg_configurar_repo
  pg_arrancar
  pg_preparar_base "$BASE_SIM"
  pg_vigilante &
  VIG_PID=$!
}

# Muerte sin gracia: SIGKILL a PostgreSQL, sus hijos, pgBackRest y el vigilante.
# SIGSTOP al postmaster para que no cree más procesos; luego SIGKILL a él y a todos sus
# hijos (backends, archivador y los archive-push de pgBackRest) a la vez. Los hijos de
# PostgreSQL hacen setsid(): no comparten sesión, por eso se buscan por padre.
matar_contenedor() {
  local pm vig_hijos="" hijos=""
  pm="$(pg_postmaster_pid || true)"
  [[ -n "$VIG_PID" ]] && vig_hijos="$(pgrep -P "$VIG_PID" || true)"
  if [[ -n "$pm" ]]; then
    kill -STOP "$pm" 2>/dev/null || true
    hijos="$(pgrep -P "$pm" || true)"
    # shellcheck disable=SC2086
    kill -9 "$pm" $hijos 2>/dev/null || true
  fi
  pkill -9 -f -- "--config=$PGBR_CONF" 2>/dev/null || true
  # shellcheck disable=SC2086
  [[ -n "$VIG_PID" ]] && kill -9 "$VIG_PID" $vig_hijos 2>/dev/null
  wait "$VIG_PID" 2>/dev/null || true
  VIG_PID=""
  sleep 0.5
}

detener_vigilante() {
  [[ -n "$VIG_PID" ]] && kill "$VIG_PID" 2>/dev/null
  wait "$VIG_PID" 2>/dev/null || true
  VIG_PID=""
}

apagar_contenedor() {  # lo que hace el SIGTERM del entrypoint (sin Odoo)
  detener_vigilante
  pg_apagar_ordenado
}

REGISTRO="$SIM_DIR/commits.log"   # «id,epoch» de cada COMMIT confirmado al cliente
: >"$REGISTRO"
cargar() {
  local fin=$((SECONDS + $1)) i
  i="$(pg_sql "SELECT coalesce(max(id), 0) FROM sim_asiento" "$BASE_SIM")"
  while ((SECONDS < fin)); do
    i=$((i + 1))
    pg_sql "INSERT INTO sim_asiento (id, monto, glosa) VALUES ($i, round($i * 1.07, 2), md5('$i'))" \
      "$BASE_SIM" >/dev/null 2>&1 || return 0
    printf '%s,%s\n' "$i" "$(date +%s.%N)" >>"$REGISTRO"
    sleep "$INTERVALO"
  done
}

FALLAS=0
RESUMEN=()
anotar() {  # anotar "texto" OK|FALLA...
  RESUMEN+=("$1 → $2")
  [[ "$2" == OK ]] || FALLAS=$((FALLAS + 1))
  echo "  ${RESUMEN[-1]}"
}

# Integridad: corruptos huecos md5_catalogo amcheck. Deja los valores en variables globales.
integridad() {
  IFS='|' read -r V_TOTAL V_MAX V_CORRUPTOS <<<"$(pg_sql "SELECT count(*), coalesce(max(id), 0),
      count(*) FILTER (WHERE monto <> round(id * 1.07, 2) OR glosa <> md5(id::text)) FROM sim_asiento" "$BASE_SIM")"
  V_HUECOS=$((V_MAX - V_TOTAL))
  V_MD5="ok"
  [[ "$(pg_sql "SELECT md5(string_agg(md5(t::text), ',' ORDER BY id)) FROM sim_catalogo t" "$BASE_SIM")" == "$MD5_REF" ]] \
    || V_MD5="DISTINTO"
  V_AMCHECK="ok"
  "$PG_BIN/pg_amcheck" -h "$PG_SOCKET_DIR" -p "$PG_PORT" -U "$PG_SUPERUSER" --install-missing \
    --heapallindexed -d "$BASE_SIM" >"$SIM_DIR/amcheck-$1.txt" 2>&1 || V_AMCHECK="FALLA"
  ((V_CORRUPTOS == 0 && V_HUECOS == 0)) && [[ "$V_MD5" == ok && "$V_AMCHECK" == ok ]]
}

verificar() {  # verificar CICLO TIPO RTO
  local ultimo ultimo_id ultimo_ts ts_rest rpo perdidos estado="OK" sana=1
  integridad "$1" || sana=0
  ultimo="$(tail -n1 "$REGISTRO")"
  ultimo_id="${ultimo%%,*}"
  ultimo_ts="${ultimo##*,}"
  ts_rest="$(awk -F, -v m="$V_MAX" '$1 == m { t = $2 } END { print t }' "$REGISTRO")"
  if [[ -z "$ts_rest" ]] && ((V_MAX < CICLO_PRIMER_ID)); then
    ts_rest="$CICLO_T0"    # no llegó nada de este ciclo: se perdió desde el inicio de la carga
  elif ((V_MAX > ultimo_id)); then
    ts_rest="$ultimo_ts"   # el último COMMIT llegó aunque el cliente no vio la confirmación
  fi
  rpo="$(awk -v a="$ultimo_ts" -v b="${ts_rest:-0}" 'BEGIN { printf "%.1f", a - b }')"
  perdidos=$((ultimo_id > V_MAX ? ultimo_id - V_MAX : 0))
  if ((!sana || V_MAX > ultimo_id + 1)) || [[ -z "$ts_rest" ]]; then
    estado="FALLA(integridad)"
  elif awk -v r="$rpo" -v m="$RPO_MAX" 'BEGIN { exit !(r > m) }'; then
    estado="FALLA(RPO>${RPO_MAX}s)"
  elif [[ "$2" == "ordenado" ]] && ((perdidos > 0)); then
    estado="FALLA(pérdida en apagado ordenado)"
  fi
  anotar "ciclo=$1 tipo=$2 confirmados=$ultimo_id restaurados=$V_MAX perdidos=$perdidos RPO_s=$rpo RTO_s=$3 corruptos=$V_CORRUPTOS huecos=$V_HUECOS md5_ref=$V_MD5 amcheck=$V_AMCHECK" "$estado"
}

# «Reinicia» el contenedor con el disco vacío y mide el RTO (deja RTO en la global).
rearrancar_vacio() {
  local t0 t1
  rm -rf "$PG_BASE"                              # el disco efímero desaparece
  t0="$(date +%s.%N)"
  arrancar_contenedor
  t1="$(date +%s.%N)"
  RTO="$(awk -v a="$t1" -v b="$t0" 'BEGIN { printf "%.1f", a - b }')"
  echo "  origen=$PG_ORIGEN RTO (disco vacío → PostgreSQL promovido y archivando) = $RTO s"
}

# Un ciclo: carga N s, muerte (kill9) o apagado ordenado, disco borrado, restauración.
ciclo() {  # ciclo NÚMERO kill9|ordenado SEGUNDOS
  local wpid
  echo "▶ Ciclo $1 ($2): $3 s de carga (1 asiento cada $INTERVALO s)"
  CICLO_T0="$(date +%s.%N)"
  CICLO_PRIMER_ID=$(($(pg_sql "SELECT coalesce(max(id), 0) FROM sim_asiento" "$BASE_SIM") + 1))
  cargar "$3" &
  wpid=$!
  sleep "$3"
  if [[ "$2" == "kill9" ]]; then
    matar_contenedor
    wait "$wpid" 2>/dev/null || true
  else
    wait "$wpid" 2>/dev/null || true
    apagar_contenedor
  fi
  rearrancar_vacio
  verificar "$1" "$2" "$RTO"
}

# --- Ciclo 0: contenedor nuevo ---------------------------------------------------------
echo "▶ Primer arranque (R2 vacío ⇒ base nueva)"
arrancar_contenedor
[[ "$PG_ORIGEN" == "nuevo" ]] || { echo "✖ Esperaba base nueva y obtuve «$PG_ORIGEN»" >&2; exit 1; }
pg_sql "CREATE TABLE sim_catalogo AS
          SELECT g AS id, md5(g::text) AS nombre, repeat(md5((g * 7)::text), 4) AS detalle
          FROM generate_series(1, $FILAS) g;
        ALTER TABLE sim_catalogo ADD PRIMARY KEY (id);
        CREATE TABLE sim_asiento (id bigint PRIMARY KEY, ts timestamptz NOT NULL DEFAULT clock_timestamp(),
                                  monto numeric(12, 2) NOT NULL, glosa text NOT NULL)" "$BASE_SIM" >/dev/null
MD5_REF="$(pg_sql "SELECT md5(string_agg(md5(t::text), ',' ORDER BY id)) FROM sim_catalogo t" "$BASE_SIM")"
echo "  base: $(pg_sql "SELECT pg_size_pretty(pg_database_size('$BASE_SIM'))") · respaldo completo (como tras instalar Odoo)"
"$ROOT/scripts/respaldo.sh" full

ciclo 1 kill9 "${CARGAS[0]}"
ciclo 2 kill9 "${CARGAS[1]}"

echo "▶ Ciclo 3: respaldo auto (tras restaurar ⇒ incr + volcado lógico)"
N_ANTES_DUMP="$(pg_sql "SELECT count(*) FROM sim_asiento" "$BASE_SIM")"
"$ROOT/scripts/respaldo.sh" auto
ULTIMO_TIPO="$(pgbr --output=json info | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["backup"][-1]["type"])')"
DUMPS="$(respaldo_dump_listar "$BASE_SIM" | wc -l)"
if [[ "$ULTIMO_TIPO" == "incr" && "$DUMPS" -ge 1 ]]; then E=OK; else E=FALLA; fi
anotar "ciclo=3 respaldo_auto: último=$ULTIMO_TIPO volcados=$DUMPS" "$E"

echo "▶ Ciclo 3b: copia anual de cierre (una por año, fuera de la poda) y subida por partes"
sleep 1   # otro sello de tiempo para el segundo volcado
"$ROOT/scripts/respaldo.sh" dump
anuales() { pgbr_raiz repo-ls "${R2_RUTA_ANUAL#/}" --filter="^$BASE_SIM-.*\\.dump\\.enc\$" | wc -l; }
ANUALES="$(anuales)"
DUMPS_3B="$(respaldo_dump_listar "$BASE_SIM" | wc -l)"
exportar_r2
head -c $((12 * 1024 * 1024 + 123)) /dev/urandom >"$SIM_DIR/flujo.bin"
BYTES_FLUJO="$(RESPALDO_DUMP_PARTE_MB=5 r2_subir_flujo "simulacro/flujo.bin" <"$SIM_DIR/flujo.bin")"
r2_curl GET "simulacro/flujo.bin" -o "$SIM_DIR/flujo.r2"
if cmp -s "$SIM_DIR/flujo.bin" "$SIM_DIR/flujo.r2"; then FLUJO=igual; else FLUJO=DISTINTO; fi
rm -f "$SIM_DIR/flujo.bin" "$SIM_DIR/flujo.r2"
r2_curl DELETE "simulacro/flujo.bin" >/dev/null
if [[ "$ANUALES" == 1 && "$DUMPS_3B" -ge 2 && "$FLUJO" == igual ]]; then E=OK; else E=FALLA; fi
anotar "ciclo=3b copias_anuales=$ANUALES (esperada 1) volcados=$DUMPS_3B multipart=${BYTES_FLUJO}B $FLUJO" "$E"

ciclo 4 ordenado "${CARGAS[2]}"

echo "▶ Ciclo 5: el volcado lógico de R2 se restaura en otra base"
DUMP="$(respaldo_dump_listar "$BASE_SIM" | tail -n1)"
exportar_r2   # la clave del volcado (pg_configurar_repo la quitó del entorno)
r2_curl GET "${R2_RUTA_DUMP#/}/$DUMP" -o "$SIM_DIR/dump.enc"
pg_sql "CREATE DATABASE simdb_dump" >/dev/null
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:PGBACKREST_CIPHER_PASS -in "$SIM_DIR/dump.enc" \
  | "$PG_BIN/pg_restore" -h "$PG_SOCKET_DIR" -p "$PG_PORT" -U "$PG_SUPERUSER" -d simdb_dump --no-owner
MD5_DUMP="$(pg_sql "SELECT md5(string_agg(md5(t::text), ',' ORDER BY id)) FROM sim_catalogo t" simdb_dump)"
N_DUMP="$(pg_sql "SELECT count(*) FROM sim_asiento" simdb_dump)"
pg_sql "DROP DATABASE simdb_dump" >/dev/null
if [[ "$MD5_DUMP" == "$MD5_REF" && "$N_DUMP" == "$N_ANTES_DUMP" ]]; then E=OK; else E=FALLA; fi
anotar "ciclo=5 volcado $DUMP ($(du -k "$SIM_DIR/dump.enc" | cut -f1) KiB): md5_ref=$([[ "$MD5_DUMP" == "$MD5_REF" ]] && echo ok || echo DISTINTO) asientos=$N_DUMP (esperados $N_ANTES_DUMP)" "$E"

echo "▶ Ciclo 6: volver a una hora concreta (DCASA_RESTAURAR_HASTA)"
cargar 30 &
WPID=$!
sleep 15
T_EPOCH="$(date +%s)"
T_OBJ="$(date -d "@$T_EPOCH" '+%F %T%:z')"
wait "$WPID" || true
ID_T="$(awk -F, -v t="$T_EPOCH" '$2 <= t { m = $1 } END { print m + 0 }' "$REGISTRO")"
ULTIMO_ANTES="$(tail -n1 "$REGISTRO" | cut -d, -f1)"
apagar_contenedor
PG_RESTAURAR_HASTA="$T_OBJ"   # = DCASA_RESTAURAR_HASTA en el entorno del contenedor
rearrancar_vacio
integridad 6a && SANA=1 || SANA=0
if [[ "$PG_ORIGEN" == "restaurado_hasta" ]] && ((SANA && (V_MAX == ID_T || V_MAX == ID_T + 1))); then E=OK; else E=FALLA; fi
anotar "ciclo=6a hasta=«$T_OBJ» origen=$PG_ORIGEN confirmados_a_esa_hora=$ID_T (luego $ULTIMO_ANTES) restaurados=$V_MAX RTO_s=$RTO corruptos=$V_CORRUPTOS md5_ref=$V_MD5 amcheck=$V_AMCHECK" "$E"
cargar 5
ULTIMO_DESPUES="$(tail -n1 "$REGISTRO" | cut -d, -f1)"
apagar_contenedor
rearrancar_vacio                # la variable sigue puesta: NO debe volver a aplicarse
integridad 6b && SANA=1 || SANA=0
if [[ "$PG_ORIGEN" == "restaurado" ]] && ((SANA && V_MAX == ULTIMO_DESPUES)); then E=OK; else E=FALLA; fi
anotar "ciclo=6b reinicio con la variable aún puesta: origen=$PG_ORIGEN confirmados=$ULTIMO_DESPUES restaurados=$V_MAX" "$E"
PG_RESTAURAR_HASTA=""
apagar_contenedor 2>/dev/null

{
  echo "=== Resumen del simulacro ($(date -u +%FT%TZ), RPO máx. permitido ${RPO_MAX} s) ==="
  printf '%s\n' "${RESUMEN[@]}"
  if ((FALLAS > 0)); then
    echo "✖ SIMULACRO FALLIDO ($FALLAS fallas)"
  else
    echo "✔ SIMULACRO OK"
  fi
} | tee "$SIM_DIR/resumen.txt"
exit $((FALLAS > 0))
