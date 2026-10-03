#!/usr/bin/env bash
# Originales pesados de fuentes/ → R2 (prefijo fuentes/), sin perder la trazabilidad.
#
# Política (docs/OPERACION.md › «Cómo subir fotos» › «Originales pesados»):
#   · Lo que la dueña sube a «up media/» lo mueve scripts/procesar_up_media.py a fuentes/<pedido>/.
#     Esos originales (PNG de varios MB) no hacen falta para que el sitio funcione: la web usa las
#     fotos optimizadas de addons/dcasa_catalogo/static/img/productos/.
#   · Cuando fuentes/ pesa demasiado para el repositorio, los originales se SUBEN a R2 con la misma
#     ruta como clave (fuentes/LTSC-07/908K….jpg) en el bucket de respaldos de producción
#     (R2_BUCKET), se verifican y se anotan en fuentes/ARCHIVADO.tsv (ruta, sha256, bytes, fecha).
#     Después se PODAN del repositorio (git rm) y cada carpeta deja constancia en su LEEME.md.
#   · scripts/importar_catalogo.py sigue contando esos archivos como fuente (por nombre, desde el
#     índice); si tiene que volver a leerlos (regenerar una foto), avisa que hay que TRAERLOS.
#   · Nunca se borra nada en R2 desde aquí. El prefijo fuentes/ no lleva reglas de ciclo de vida
#     (igual que adjuntos/). Lo que ya está en la historia de git no se achica con esto: la política
#     vale para lo que entra desde ahora.
#
# Uso:  scripts/archivar_fuentes.sh listar [--minimo-mb N]   candidatos (sin red)
#       scripts/archivar_fuentes.sh subir  [--minimo-mb N] [--simular]   sube y verifica; anota el índice
#       scripts/archivar_fuentes.sh podar  [--simular]      git rm de lo que YA está verificado en R2
#       scripts/archivar_fuentes.sh traer  [--simular]      baja lo que falta en disco (verifica sha256)
# Variables: R2_ENDPOINT R2_BUCKET R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY (las de docs/OPERACION.md)
#            R2_REGION (auto) R2_VERIFY_TLS (y) R2_PREFIJO (fuentes: la carpeta misma, no se cambia sin motivo)
# Solo imágenes (.png .jpg .jpeg .webp): los Excel y los LEEME se quedan siempre en el repositorio.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
FUENTES="$RAIZ/fuentes"
INDICE="$FUENTES/ARCHIVADO.tsv"
R2_REGION="${R2_REGION:-auto}"
R2_VERIFY_TLS="${R2_VERIFY_TLS:-y}"
R2_PREFIJO="${R2_PREFIJO:-fuentes}"
MINIMO_MB=0
SIMULAR=0

ayuda() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; }

msg() { printf '%s\n' "$*" >&2; }

orden="${1:-}"
[[ -n "$orden" ]] || { ayuda; exit 1; }
shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --minimo-mb) MINIMO_MB="$2"; shift 2 ;;
    --simular) SIMULAR=1; shift ;;
    -h|--help) ayuda; exit 0 ;;
    *) msg "✖ Opción desconocida: $1"; ayuda; exit 1 ;;
  esac
done

hoy() { TZ=America/Panama date +%F; }

sha256() { sha256sum "$1" | cut -d' ' -f1; }

bytes() { stat -c %s "$1"; }

# Ruta relativa a la raíz → clave de R2 codificada para la URL (espacios, «×», «–»…).
clave_url() {
  python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1"
}

exigir_r2() {
  local v faltan=()
  for v in R2_ENDPOINT R2_BUCKET R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
    [[ -n "${!v:-}" ]] || faltan+=("$v")
  done
  if [[ ${#faltan[@]} -gt 0 ]]; then
    msg "✖ Faltan variables de R2: ${faltan[*]} (docs/OPERACION.md › «Crear los tokens de R2»)."
    exit 2
  fi
}

# r2 METODO clave [opciones de curl…]  (misma firma SigV4 que docker/pg.sh → r2_curl)
r2() {
  local metodo="$1" clave="$2" tls=()
  shift 2
  [[ "$R2_VERIFY_TLS" == "n" ]] && tls=(-k)
  [[ "$metodo" == HEAD ]] && tls+=(-I)
  curl -sS --fail-with-body --retry 3 --retry-delay 2 --connect-timeout 20 --max-time 1800 \
    "${tls[@]}" -K <(printf 'user = "%s:%s"\n' "$R2_ACCESS_KEY_ID" "$R2_SECRET_ACCESS_KEY") \
    --aws-sigv4 "aws:amz:${R2_REGION}:s3" -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
    -X "$metodo" "${R2_ENDPOINT%/}/$R2_BUCKET/$(clave_url "$clave")" "$@"
}

# Tamaño que R2 reporta para una clave (vacío si no existe).
bytes_en_r2() {
  r2 HEAD "$1" 2>/dev/null | tr -d '\r' | awk 'tolower($1)=="content-length:" {print $2}' | head -1
}

en_indice() { [[ -f "$INDICE" ]] && grep -qF -- "$(printf '%s\t' "$1")" "$INDICE"; }

# Imágenes de fuentes/ con al menos MINIMO_MB que todavía no están en el índice (rutas relativas).
candidatos() {
  [[ -d "$FUENTES" ]] || return 0
  local minimo=$((MINIMO_MB * 1024 * 1024)) ruta
  while IFS= read -r -d '' f; do
    ruta="${f#"$RAIZ/"}"
    [[ $(bytes "$f") -ge $minimo ]] || continue
    en_indice "$ruta" && continue
    printf '%s\n' "$ruta"
  done < <(find "$FUENTES" -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) -print0 | sort -z)
}

# Filas del índice: ruta<TAB>sha256<TAB>bytes<TAB>fecha (sin cabecera ni comentarios).
indice() { [[ -f "$INDICE" ]] && grep -v '^#' "$INDICE" | grep -v '^$' || true; }

anotar() {   # ruta sha bytes
  if [[ ! -f "$INDICE" ]]; then
    printf '# Originales archivados en R2 (%s/<ruta>) por scripts/archivar_fuentes.sh. No editar a mano.\n' "$R2_BUCKET" > "$INDICE"
    printf '# ruta\tsha256\tbytes\tfecha\n' >> "$INDICE"
  fi
  printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$(hoy)" >> "$INDICE"
}

listar() {
  local total=0 n=0
  while IFS= read -r ruta; do
    [[ -n "$ruta" ]] || continue
    b=$(bytes "$RAIZ/$ruta")
    printf '%8.1f MB  %s\n' "$(awk -v b="$b" 'BEGIN{print b/1048576}')" "$ruta"
    total=$((total + b)); n=$((n + 1))
  done < <(candidatos)
  msg "$n archivos, $(awk -v b="$total" 'BEGIN{printf "%.1f", b/1048576}') MB sin archivar (mínimo ${MINIMO_MB} MB)."
  [[ -f "$INDICE" ]] && msg "Ya en R2 según $INDICE: $(indice | wc -l)."
}

subir() {
  exigir_r2
  local ruta sha b remoto
  while IFS= read -r ruta; do
    [[ -n "$ruta" ]] || continue
    sha=$(sha256 "$RAIZ/$ruta"); b=$(bytes "$RAIZ/$ruta")
    if [[ "$SIMULAR" == 1 ]]; then msg "· subiría $ruta ($b bytes)"; continue; fi
    remoto=$(bytes_en_r2 "$ruta")
    if [[ "$remoto" == "$b" ]]; then
      msg "· ya estaba en R2: $ruta"
    else
      r2 PUT "$ruta" -T "$RAIZ/$ruta" -H "x-amz-meta-sha256: $sha" >/dev/null
      remoto=$(bytes_en_r2 "$ruta")
      [[ "$remoto" == "$b" ]] || { msg "✖ $ruta: R2 reporta ${remoto:-nada}, local $b bytes. No se anota."; exit 1; }
      msg "✔ subido $ruta ($b bytes)"
    fi
    anotar "$ruta" "$sha" "$b"
  done < <(candidatos)
  msg "Índice: $INDICE. Siguiente paso: revisar y, cuando convenga, «podar»."
}

podar() {
  exigir_r2
  local ruta sha b fecha remoto carpeta n=0
  declare -A por_carpeta=()
  while IFS=$'\t' read -r ruta sha b fecha; do
    [[ -n "$ruta" && -f "$RAIZ/$ruta" ]] || continue
    [[ "$(sha256 "$RAIZ/$ruta")" == "$sha" ]] || { msg "✖ $ruta cambió desde que se archivó (sha256 distinto): no se poda."; continue; }
    remoto=$(bytes_en_r2 "$ruta")
    [[ "$remoto" == "$b" ]] || { msg "✖ $ruta no está íntegro en R2 (${remoto:-nada} vs $b): no se poda."; continue; }
    if [[ "$SIMULAR" == 1 ]]; then msg "· podaría $ruta"; continue; fi
    git -C "$RAIZ" rm -q -- "$ruta"
    carpeta="$(dirname "$ruta")"
    por_carpeta["$carpeta"]+="- \`$(basename "$ruta")\` ($b bytes, sha256 \`${sha:0:12}…\`, subido el $fecha)."$'\n'
    n=$((n + 1))
  done < <(indice)
  for carpeta in "${!por_carpeta[@]}"; do
    # shellcheck disable=SC2016  # los acentos graves son Markdown, no sustitución de órdenes
    {
      printf '\n## Archivados en R2 el %s\n\n' "$(hoy)"
      printf 'Ya no están en el repositorio: están en R2 (`%s/<ruta>`, índice `fuentes/ARCHIVADO.tsv`). ' "$R2_BUCKET"
      printf 'Para volver a leerlos: `scripts/archivar_fuentes.sh traer`.\n\n%s' "${por_carpeta[$carpeta]}"
    } >> "$RAIZ/$carpeta/LEEME.md"
    git -C "$RAIZ" add -- "$carpeta/LEEME.md"
  done
  [[ -f "$INDICE" ]] && git -C "$RAIZ" add -- "$INDICE"
  msg "$n archivos podados (quedan preparados en el índice; revisa y haz commit)."
}

traer() {
  exigir_r2
  local ruta sha b fecha n=0
  while IFS=$'\t' read -r ruta sha b fecha; do
    [[ -n "$ruta" && ! -f "$RAIZ/$ruta" ]] || continue
    if [[ "$SIMULAR" == 1 ]]; then msg "· traería $ruta"; continue; fi
    mkdir -p "$RAIZ/$(dirname "$ruta")"
    r2 GET "$ruta" -o "$RAIZ/$ruta.parte"
    if [[ "$(sha256 "$RAIZ/$ruta.parte")" != "$sha" ]]; then
      rm -f "$RAIZ/$ruta.parte"; msg "✖ $ruta: el sha256 no coincide con el índice ($fecha). Se descarta la descarga."; exit 1
    fi
    mv "$RAIZ/$ruta.parte" "$RAIZ/$ruta"
    n=$((n + 1))
  done < <(indice)
  msg "$n archivos traídos. Son copias de trabajo: no los agregues de nuevo al repositorio (git los verá como nuevos)."
}

case "$orden" in
  listar) listar ;;
  subir) subir ;;
  podar) podar ;;
  traer) traer ;;
  -h|--help) ayuda ;;
  *) msg "✖ Orden desconocida: $orden"; ayuda; exit 1 ;;
esac
