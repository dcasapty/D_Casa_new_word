#!/usr/bin/env bash
# Respaldo base con repo1-bundle=y (agrupa archivos pequeños): objetos, bytes, tiempo y PUT;
# luego un ensayo de muerte/restauración para medir el RTO y los GET con ese respaldo.
set -uo pipefail; source "$(dirname "$0")/env.sh"; D="$(cd "$(dirname "$0")" && pwd)"
OUT=$D/salidas/bundle-$(date +%Y%m%d-%H%M%S).txt
grep -q "^repo1-bundle=y" $PGBR_CONF || sed -i 's/^repo1-retention-full=2/repo1-retention-full=2\nrepo1-bundle=y/' $PGBR_CONF
{
o0=$(grep -c "/dcasa-pg" $R3/moto.log); t0=$(date +%s.%N)
asp "pgbackrest --config=$PGBR_CONF --stanza=$STANZA --type=full --log-level-console=warn backup"
t1=$(date +%s.%N); o1=$(grep -c "/dcasa-pg" $R3/moto.log)
echo "respaldo completo con bundle: $(echo "$t1-$t0"|bc) s, peticiones S3 $((o1-o0))"
asp "pgbackrest --config=$PGBR_CONF --stanza=$STANZA info" | grep -E "full backup|backup set size|database size" | tail -3
} | tee $OUT
MITIGAR=1 bash $D/03_ensayo_muerte.sh 60 1 | sed -n 1,6p | tee -a $OUT
