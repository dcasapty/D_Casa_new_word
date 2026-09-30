#!/usr/bin/env bash
# Demo completa, sin red: verifica el dorado contra el Excel real, puntúa 4 corridas SIMULADAS y compara dos.
set -u
cd "$(dirname "$0")"
python3 evaluador.py --verificar
python3 simular_salidas.py >/dev/null
for n in oraculo sonnet_v1 sonnet_v2_cache haiku_v1; do
  echo; python3 evaluador.py --salidas "salidas_demo/$n.json" --informe "resultados/$n.json" --detalle \
    --umbral exactitud=0.9 alucinacion=0.02 criticos=0 || true
done
echo; python3 evaluador.py --comparar resultados/sonnet_v1.json resultados/sonnet_v2_cache.json --fallar-si-regresa || true
