#!/usr/bin/env bash
L=$(dirname "$0"); O=$L/base
for u in / /shop /visitanos /shop/xht022-t-w-cama-de-felpa-twin-blanca-con-cabecero-curvo-4; do curl -s -o /dev/null localhost:8190$u; done
$L/run.sh odoo-home http://localhost:8190/ $O
$L/run.sh odoo-shop http://localhost:8190/shop $O
$L/run.sh odoo-ficha http://localhost:8190/shop/xht022-t-w-cama-de-felpa-twin-blanca-con-cabecero-curvo-4 $O
$L/run.sh odoo-visitanos http://localhost:8190/visitanos $O
node $L/resumen.js $O > $O/tabla.md
echo HECHO
