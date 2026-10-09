# Imagen del puente de WhatsApp (Baileys). La construye wrangler y la empuja al registro de
# Cloudflare: por eso el token de despliegue necesita el permiso «Cloudflare Images: Edit»
# (sin él el despliegue muere al subir la imagen, con un error que no menciona Images).
#
# Node 22: es el piso que exige wrangler y no vale correr el contenedor en una versión
# que se está retirando.
#
# Dos etapas a propósito: las dependencias se instalan (y se comprueban) en una, y a la
# imagen final solo viaja `node_modules` ya listo: menos superficie y menos disco, que en
# Containers se factura por GB-segundo las 24 horas.
#
# Baileys 7 trae `libsignal` desde el registro de npm (6.x); el CRM de origen necesitaba
# `git` porque entonces lo traía de GitHub por SSH («npm error enoent … git error» sin
# nombrar a git). Si alguna vez vuelve esa dependencia, el build lo dirá en la etapa 1.

# ── Etapa 1: instalar dependencias ─────────────────────────────────────────
FROM node:22-bookworm-slim AS dependencias

WORKDIR /app
COPY package.json package-lock.json ./
# `npm ci` instala EXACTAMENTE lo del package-lock.json (build reproducible). La segunda
# línea hace fallar el build —no el arranque en producción— si Baileys no carga.
RUN npm ci --omit=dev --no-audit --no-fund \
 && node -e "import('@whiskeysockets/baileys').then(() => console.log('Baileys carga bien.'))"

# ── Etapa 2: lo que de verdad corre ────────────────────────────────────────
FROM node:22-bookworm-slim

ENV NODE_ENV=production
WORKDIR /app
COPY --from=dependencias /app/node_modules ./node_modules
COPY package.json servidor.mjs nucleo.mjs ./
COPY lib ./lib

# Sin root: el proceso solo necesita leer /app y escribir en /tmp.
RUN chown -R node:node /app
USER node

# El Worker habla con este puerto vía el Durable Object (defaultPort = 8080).
EXPOSE 8080

# Sin capa de init: si el proceso de Node se cae, queremos que el contenedor muera y que el
# Worker lo note y lo levante. Un supervisor adentro escondería exactamente el fallo que
# la vigilancia busca.
CMD ["node", "servidor.mjs"]
