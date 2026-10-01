#!/bin/sh
# Libros guardados por Excel 365 con imágenes «en celda» (proyecto dalmartin/xlcellimage, GPL-3).
# NO se versionan (licencia); los tests que los usan se saltan si no están.
set -e
cd "$(dirname "$0")/externos"
[ -d xlcellimage ] || git clone --depth 1 https://github.com/dalmartin/xlcellimage
git -C xlcellimage log -1 --format='%H %cd'
