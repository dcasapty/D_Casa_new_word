#!/usr/bin/env bash
L=$(dirname "$0"); O=$L/proto
$L/run.sh proto-home http://localhost:8191/ $O
$L/run.sh proto-shop http://localhost:8191/shop/ $O
$L/run.sh proto-ficha http://localhost:8191/shop/xht022-t-w-cama-de-felpa-twin-blanca-con-cabecero-curvo/ $O
$L/run.sh proto-ficha2 http://localhost:8191/shop/alj021439-mueble-zapatera-tono-nogal-con-3-compartimentos-abatibles/ $O
$L/run.sh proto-visitanos http://localhost:8191/visitanos $O
node $L/resumen.js $O > $O/tabla.md
echo HECHO
