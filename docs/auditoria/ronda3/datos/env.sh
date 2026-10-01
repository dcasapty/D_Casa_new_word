# Variables comunes del prototipo r3-datos (PostgreSQL efímero + WAL a S3).
# Uso: source docs/auditoria/ronda3/datos/env.sh
export R3=/tmp/r3_datos                 # datos y binarios: NUNCA en git
export PGBIN=/usr/lib/postgresql/16/bin
export PGPORT_P=5440                    # clúster del prototipo (puertos permitidos: 5440, 5442-5449)
export PGDATA_P=$R3/pg5440
export S3_PORT=9100                     # S3 local (moto) con TLS autofirmado
export S3_BUCKET=dcasa-pg
export PGBR_CONF=$R3/pgbackrest.conf
export STANZA=dcasa
# Ejecutar como el usuario postgres (PostgreSQL no corre como root)
asp() { su postgres -s /bin/bash -c "$*"; }
psqlp() { asp "$PGBIN/psql -X -h 127.0.0.1 -p $PGPORT_P -U postgres -d ${DB:-dcasa} -tA -c \"$1\""; }
