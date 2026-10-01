#!/usr/bin/env bash
# Uso: run.sh <etiqueta> <url> <dir_salida> [n]
set -u
export CHROME_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome
cd "${LH_DIR:-$(dirname "$0")}"  # carpeta con lighthouse instalado (npm i lighthouse@12)
tag=$1; url=$2; out=$3; n=${4:-3}; mkdir -p "$out"
for i in $(seq 1 $n); do
  npx lighthouse "$url" --quiet --output=json --output-path="$out/$tag-$i.json" \
    --only-categories=performance,accessibility,best-practices,seo \
    --chrome-flags="--headless=new --no-sandbox --proxy-server=http://127.0.0.1:42667 --proxy-bypass-list=localhost;127.0.0.1 --ignore-certificate-errors-spki-list=KnP1OnzHv/y42eRQmbGwoYTHcSJF448m6CU5mdngwKk=" \
    >/dev/null 2>"$out/$tag-$i.err" || echo "FALLO $tag $i"
done
