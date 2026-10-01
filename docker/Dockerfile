# syntax=docker/dockerfile:1.7
# Imagen de producción de D'CASA: Odoo 19 (desde el submódulo vendor/odoo)
# + los módulos propios de addons/ + PostgreSQL 16 con pgBackRest (respaldos en R2).
# Contexto de build: la raíz del repo.
#
#   docker build -f docker/Dockerfile -t dcasa-odoo .

ARG UBUNTU_VERSION=24.04

# --- 1. Dependencias Python (con compiladores; no llegan a la imagen final) ---
FROM ubuntu:${UBUNTU_VERSION} AS builder
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential python3-dev python3-venv \
        libpq-dev libldap2-dev libsasl2-dev libjpeg-dev zlib1g-dev libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*
COPY vendor/odoo/requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip wheel \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# --- 2. Código de Odoo, sin traducciones que no usamos ----------------------
FROM ubuntu:${UBUNTU_VERSION} AS source
COPY vendor/odoo /opt/odoo
# Solo español (es, es_419): reduce la imagen ~40%. Si algún día hace falta
# otro idioma, basta con quitar esta línea.
RUN find /opt/odoo -path '*/i18n/*.po' ! -name 'es.po' ! -name 'es_419.po' -delete \
    && rm -rf /opt/odoo/.git /opt/odoo/.github /opt/odoo/doc

# --- 3. Imagen final --------------------------------------------------------
FROM ubuntu:${UBUNTU_VERSION}
ARG WKHTMLTOPDF_VERSION=0.12.6.1-3
ARG APP_VERSION=dev
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    APP_VERSION=${APP_VERSION}

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 ca-certificates curl tini postgresql-client \
        libpq5 libldap2 libsasl2-2 libjpeg-turbo8 libxml2 libxslt1.1 \
        fontconfig fonts-dejavu-core fonts-noto-core xfonts-75dpi xfonts-base libxrender1 libxext6 \
    && ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/wkhtmltox.deb \
        "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}.jammy_${ARCH}.deb" \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -rf /tmp/wkhtmltox.deb /var/lib/apt/lists/*

# PostgreSQL 16 (servidor) + pgBackRest 2.50 (Fase 1, opción A: la base vive en este
# contenedor y se respalda continuamente en R2; docker/pg.sh). Sin el clúster «main» del
# paquete: el entrypoint crea o restaura el suyo en /var/lib/odoo/pg como usuario odoo.
RUN mkdir -p /etc/postgresql-common/createcluster.d \
    && echo "create_main_cluster = false" > /etc/postgresql-common/createcluster.d/dcasa.conf \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-16 pgbackrest openssl \
    && rm -rf /var/lib/postgresql/16/main /etc/postgresql/16/main /var/lib/apt/lists/* \
    && /usr/lib/postgresql/16/bin/postgres --version && pgbackrest version

RUN useradd --system --create-home --home-dir /var/lib/odoo --shell /usr/sbin/nologin odoo
COPY --from=builder /opt/venv /opt/venv
COPY --from=source /opt/odoo /opt/odoo
COPY addons /opt/dcasa/addons
COPY docker/pg.sh /usr/local/lib/dcasa/pg.sh
COPY docker/entrypoint.sh /usr/local/bin/dcasa-entrypoint
# El Worker lo ejecuta con ctx.container.exec() (edge/CONTRATO_CONTENEDOR.md).
COPY scripts/respaldo.sh /usr/local/bin/dcasa-respaldo
RUN chmod 755 /usr/local/bin/dcasa-entrypoint /usr/local/bin/dcasa-respaldo \
    && chmod 644 /usr/local/lib/dcasa/pg.sh

# Tamaño estimado por capas (sin daemon de Docker para medirlo; tamaños instalados de
# apt-cache y du sobre el mismo contenido, 2026-10-01). Límite: disco de basic = 4 GB,
# que además debe alojar la base (~0,2 GB), el WAL (max_wal_size 256 MB) y los volcados.
#   ubuntu:24.04 base ............................................. ~0,08 GB
#   apt de Odoo (python3, libs, fuentes: ~0,18 GB) + wkhtmltopdf (0,14 GB) ~0,32 GB
#   PostgreSQL 16 + pgBackRest + openssl (NUEVA: servidor 43 MB,
#     libllvm17 118 MB que exige el paquete por JIT, locales 17 MB) ~0,18 GB
#   /opt/venv (requirements de Odoo 19; medido con Python 3.12) .. ~0,22 GB
#   /opt/odoo sin .po salvo es/es_419 (1,24 GB − 0,78 GB) ......... ~0,45 GB
#   addons/ + scripts ............................................. ~0,03 GB
#   Total ............................................ ~1,3 GB (≈ 1/3 del disco)

USER odoo
WORKDIR /var/lib/odoo
EXPOSE 8069
# start-period: restaurar desde R2 + arrancar Odoo (contrato del borde: ≤ 180 s).
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s \
    CMD curl -fsS http://127.0.0.1:8069/web/health || exit 1
# tini es PID 1 y entrega el SIGTERM al entrypoint, que apaga Odoo y luego PostgreSQL
# con el último WAL en R2 (Cloudflare da hasta 15 min antes del SIGKILL).
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/dcasa-entrypoint"]
