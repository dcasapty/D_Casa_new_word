# syntax=docker/dockerfile:1.7
# Imagen de producción de D'CASA: Odoo 19 (desde el submódulo vendor/odoo)
# + los módulos propios de addons/. Contexto de build: la raíz del repo.
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

RUN useradd --system --create-home --home-dir /var/lib/odoo --shell /usr/sbin/nologin odoo
COPY --from=builder /opt/venv /opt/venv
COPY --from=source /opt/odoo /opt/odoo
COPY addons /opt/dcasa/addons
COPY docker/entrypoint.sh /usr/local/bin/dcasa-entrypoint
RUN chmod +x /usr/local/bin/dcasa-entrypoint

USER odoo
WORKDIR /var/lib/odoo
EXPOSE 8069
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
    CMD curl -fsS http://127.0.0.1:8069/web/health || exit 1
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/dcasa-entrypoint"]
