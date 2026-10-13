# Arquitectura

Estado al 2026-10-12. Reemplaza la primera versión (Odoo con una base PostgreSQL gestionada en Neon):
esa opción se descartó por costo y hoy la base vive **dentro del contenedor**, protegida por respaldos
continuos en R2. La decisión y sus mediciones están en
[auditoria/DECISION_Y_PLAN.md](auditoria/DECISION_Y_PLAN.md).

```
                                   Cloudflare
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                                                                                        │
 │  Clientes ───►  Worker «dcasa» (edge/)  ───►  Contenedor de Odoo (docker/)             │
 │                  · cabeceras de seguridad       Odoo 19 + PostgreSQL 16 en el          │
 │                  · caché de páginas anónimas    MISMO contenedor (una sola instancia)  │
 │                    (Workers KV «TIENDA»)                  │                            │
 │  Equipo ───►     · puerta del equipo                      │ WAL continuo + pg_dump     │
 │  /master         (Cloudflare Access)                      ▼ diario (cifrados)          │
 │                  · frena bots y rutas peligrosas        R2: pgbackrest/ pg_dump/       │
 │                  · cron: despertar y respaldar               adjuntos/ (fotos y PDF)   │
 │                         ▲                                                              │
 │                         │ service binding (única entrada a /dcasa/juan/**)             │
 │  WhatsApp (QR) ──► Puente «dcasa-puente-wa» ──► Worker «dcasa-juan» (juan/)            │
 │  Telegram, Meta ─────────────────────────────►  Durable Objects con SQLite propio      │
 │                                                  (una conversación = un objeto)        │
 └────────────────────────────────────────────────────────────────────────────────────────┘
              Proveedores de IA externos (los elige la dueña en Ajustes): Brian y Juan
```

## Las piezas

| Pieza | Dónde | Qué hace |
|---|---|---|
| **Worker `dcasa`** | `edge/` | Punto de entrada público. La lógica que se prueba está en `src/routing.ts` y `src/handler.ts`, sin depender de Cloudflare. Pone cabeceras de seguridad y `X-Forwarded-*`, bloquea el gestor de bases y las rutas de API por internet, frena escáneres y limita intentos (`bots.ts`), guarda y sirve la caché de páginas anónimas (`tienda/`), verifica la puerta del equipo (`puerta.ts`), responde una página «estamos abriendo» mientras Odoo arranca (`arranque.ts`) y corre dos crons: despertar a Odoo cada hora y el respaldo diario. |
| **Contenedor de Odoo** | `docker/` | Una imagen con Odoo 19, los módulos de `addons/` y PostgreSQL 16. Producción: `standard-1` encendido 24/7; staging: `basic`, se duerme solo tras 1 h sin visitas. Contrato con el Worker: [`edge/CONTRATO_CONTENEDOR.md`](../edge/CONTRATO_CONTENEDOR.md). |
| **R2** | Cloudflare | Un bucket por entorno (`dcasa-respaldos`, `dcasa-respaldos-staging`): `pgbackrest/` (WAL y respaldos cifrados), `pg_dump/` (respaldo lógico diario), `adjuntos/` (fotos y PDF; ver `dcasa_adjuntos_r2`) y, opcional, `fuentes/` (originales pesados del catálogo). |
| **Workers KV `TIENDA`** | Cloudflare | Caché del HTML que dibuja Odoo para visitantes anónimos. En producción está apagada (`TIENDA_ESTATICA=off`) hasta que la dueña la apruebe en staging. |
| **Worker `dcasa-juan`** | `juan/` | **Juan**, el asistente de los clientes: junta ráfagas de mensajes, corre el bucle de IA con herramientas, contesta y hace seguimiento. Un Durable Object por conversación (más uno global para el gasto de IA y la salud), con almacenamiento SQLite propio; sin D1 ni Vectorize. Workers AI solo transcribe notas de voz, lee imágenes y, si Gerencia lo enciende, calcula la búsqueda por significado. Habla con Odoo solo por service binding. |
| **Puente `dcasa-puente-wa`** | `puente-wa/` | Worker + Container (Baileys) que mantiene la sesión de WhatsApp por QR las 24 horas. Una sola instancia: WhatsApp admite una conexión por dispositivo. Separado de `juan` a propósito: si el puente falla, Juan sigue contestando por los demás canales. |
| **Cloudflare Access** | Cloudflare | La puerta del equipo: un PIN al correo en la ruta de entrada (`/master`). Guía en [SEGURIDAD_ACCESO.md](SEGURIDAD_ACCESO.md) §8. |

## Quién guarda qué (una sola verdad)

- **Odoo** guarda todo lo permanente: facturas, inventario, clientes, conversaciones, oportunidades,
  catálogo y el libro de puntos de Socios. Juan solo guarda memoria de trabajo.
- **Los adjuntos** (fotos, PDF, assets compilados) van a R2, no a la base. El contenedor no tiene disco
  permanente. Nunca se borran objetos de R2 al desvincular un adjunto: un cron lo hace a los 45 días,
  para que una restauración a un momento anterior encuentre sus archivos.
- **Las sesiones** de Odoo viven en PostgreSQL (`dcasa_sesiones`), no en disco.
- **Los secretos** (la pimienta de los PIN de Socios, la clave que cifra los respaldos, las llaves de
  R2) viven en el Worker y se pasan al contenedor al arrancar; nunca en la imagen ni en el repositorio.

## Respaldo y recuperación

PostgreSQL manda cada cambio (WAL) a R2 con pgBackRest; además hay un `pg_dump` cifrado cada día a las
03:17 de Panamá. Si el contenedor se reinicia o cambia de máquina, **al arrancar restaura la base desde
R2** antes de abrir el puerto. Se acepta perder como máximo ≈ 1 minuto de datos (medido: 8 a 52 s). El
tiempo de volver con R2 real todavía no se midió (con almacenamiento local, ≈ 46 s). Cada ejecución de
CI corre un simulacro: mata PostgreSQL, borra el disco, restaura y compara. Procedimiento y qué hacer
si el sitio cae: [OPERACION.md](OPERACION.md).

## Entornos

| | Producción | Staging |
|---|---|---|
| Worker | `dcasa`; el dominio `dcasapty.com` se activa en `edge/wrangler.jsonc` (rutas hoy comentadas) cuando se mueva el DNS | `dcasa-staging` (`workers.dev`) |
| Contenedor | `standard-1`, 24/7 | `basic`, se duerme tras 1 h |
| Despliegue | solo a mano: *Run workflow* con `desplegar_en = produccion`, **desde `main`** y con todo en verde | a mano: *Run workflow* con `desplegar_en = staging`, desde cualquier rama |

Un merge a `main` solo corre las pruebas: **nunca despliega** (GitHub no ofrece «Required reviewers» en un
repositorio privado de estos planes; la aprobación es el clic de quien lanza el despliegue, ver
[DESPLIEGUE.md](DESPLIEGUE.md) §3).

A 2026-10-13 **producción todavía no existe**: en la cuenta de Cloudflare solo están los Workers de staging
(`dcasa-staging`, `dcasa-juan-staging`) y el despliegue a producción nunca ha corrido (el intento del 2026-10-02 se
omitió por falta de secretos). Los secretos obligatorios de `production` ya están cargados en GitHub; falta lanzarlo.
Hoy el negocio sigue operando en el Odoo anterior de dcasapty.com. Ver [PLAN.md](PLAN.md).

## Arranque del contenedor

`docker/entrypoint.sh`: genera `odoo.conf` desde variables de entorno, restaura la base desde R2 (o crea una
nueva si R2 está vacío), y si la versión de la imagen cambió (`APP_VERSION` = commit) actualiza los módulos
una sola vez; los reinicios normales no actualizan. La lista de módulos que instala está en la variable
`ODOO_MODULES` del mismo archivo.

## Módulos propios (`addons/`)

Todos con prefijo `dcasa_` (o `website_dcasa`); `vendor/odoo` nunca se modifica.

| Área | Módulos |
|---|---|
| Base y marca | `dcasa_base` (empresa, Panamá, ITBMS, RUC con DV), `dcasa_invoice` (factura con la marca), `dcasa_interfaz` (la cara del panel: inicio, íconos, favicon, sin avisos de pago) |
| Ventas y clientes | `dcasa_socios` (puntos y referidos), `dcasa_contactos` (una persona, una ficha), `dcasa_conversaciones` (bandeja y API de Juan, CRM automático) |
| Tienda y catálogo | `website_dcasa` (sitio y tienda), `dcasa_catalogo` (productos y fotos reales), `dcasa_tienda_borde` (avisa al Worker qué páginas cambiaron) |
| Inventario | `dcasa_barras` (Escáner, conteo y etiquetas numeradas) |
| Contabilidad y personal | `dcasa_contabilidad`, `dcasa_consolidacion`, `dcasa_nomina`, `dcasa_equipo`, `dcasa_fe_pa` (factura electrónica, apagada) |
| Asistente | `dcasa_brian` (chat, Telegram y MCP) |
| Seguridad y operación | `dcasa_seguridad` (doble factor, bloqueos, puerta del equipo), `dcasa_sesiones` (sesiones en PostgreSQL y `/dcasa/salud`), `dcasa_adjuntos_r2` (adjuntos en R2) |

Dependencias principales entre módulos propios (resumen de cada `__manifest__.py`; `dcasa_base` no depende de ninguno; `dcasa_contabilidad` depende también de `dcasa_interfaz`):

```
dcasa_base ─┬─► dcasa_invoice ─┬─► dcasa_socios ─┬─► website_dcasa ─► dcasa_catalogo ─► dcasa_interfaz
            │                  │                 └─► dcasa_contactos      │                   │
            │                  ├─► dcasa_contabilidad ─► dcasa_consolidacion                   ├─► dcasa_barras
            │                  └─► dcasa_fe_pa                           └─► dcasa_tienda_borde
            ├─► dcasa_nomina (también de dcasa_contabilidad)
            └─► dcasa_equipo
dcasa_brian (de interfaz, contabilidad, catálogo y socios) ─► dcasa_conversaciones (también de contactos)
dcasa_seguridad · dcasa_sesiones · dcasa_adjuntos_r2: sin dependencias propias
```

## Dónde seguir leyendo

| Tema | Documento |
|---|---|
| Despliegue y secretos | [DESPLIEGUE.md](DESPLIEGUE.md) · [OPERACION.md](OPERACION.md) (para la dueña) |
| Seguridad y acceso | [SEGURIDAD_ACCESO.md](SEGURIDAD_ACCESO.md) |
| Juan | [JUAN.md](JUAN.md) · [JUAN_WORKER.md](JUAN_WORKER.md) · [JUAN_ODOO.md](JUAN_ODOO.md) · [JUAN_PANEL.md](JUAN_PANEL.md) · [JUAN_PUENTE.md](JUAN_PUENTE.md) · [JUAN_PLAN_B.md](JUAN_PLAN_B.md) |
| Brian | [BRIAN.md](BRIAN.md) |
| Lo demás | [README.md](README.md) (índice de toda la documentación) |
