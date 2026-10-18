# Replicar el sistema para otro negocio

Paso a paso para instalar este sistema (Odoo 19 + sitio + Socios + Juan + Brian, en Cloudflare) para **otro negocio**,
de punta a punta. Está escrito para que una sesión de Claude lo siga con solo el link del repositorio, sin adivinar.
Verificado contra el código el **2026-10-18**. Si algo de aquí no coincide con el código, manda el código: dilo y
corrige este documento.

Antes de empezar, lee [ARQUITECTURA.md](ARQUITECTURA.md) (las piezas) y [MODULOS.md](MODULOS.md) (qué hace cada módulo).

## 0. Reglas para quien instala

- **Nunca pidas un secreto por el chat.** Di *dónde* se pega (GitHub › Environments o el panel de Cloudflare) y confirma
  que quedó cargado sin ver su valor.
- **Nunca copies datos de D'CASA al negocio nuevo:** ni clientes, ni la base, ni los respaldos, ni las cifras de
  `puntos.json`, ni el catálogo (§4 y §9).
- **No inventes contenido:** precios, cifras, plazos, garantías o testimonios los pone el dueño del negocio nuevo.
- **No recortes pruebas.** Si cambias un dato que una prueba comprueba, cambias la prueba en el mismo commit
  (§4.10) y corres `scripts/test.sh` hasta que pase.
- El sistema está hecho para **Panamá** (plan contable `l10n_pa`, ITBMS, RUC con DV, nómina panameña, DGI, zona horaria
  `America/Panama`, celulares de 8 dígitos con +507). Para otro país hace falta trabajo que este documento no cubre.

Quién hace qué: **Claude** clona, cambia el código, corre pruebas y lanza los flujos; **el dueño** crea las cuentas,
paga los planes, genera y pega los secretos, y aprueba cada paso a producción.

## 1. Requisitos

| Qué | Para qué | ¿Obligatorio? |
|---|---|---|
| **Cuenta de Cloudflare con Workers Paid** | Containers solo existe en el plan de pago | Sí |
| **R2** activado en esa cuenta | Respaldos de la base y adjuntos (dos buckets) | Sí |
| **Workers KV** | Caché de páginas (lo crea wrangler) | Viene con Workers |
| **Workers AI** | Juan: notas de voz e imágenes (`TRANSCRIBIR_AUDIO`, `RECONOCER_IMAGENES` en `1`); se cobra a la cuenta | Solo si se despliega Juan con esas variables encendidas |
| **Cloudflare Zero Trust** (plan Free) | La puerta del equipo (`/master`) | No (recomendado) |
| **Cuenta de GitHub** con Actions | Pruebas y despliegue; espacio de artefactos (cada imagen ~420 MB, dura 1 día) | Sí |
| **Clave de un proveedor de IA para Brian** | El despliegue **exige** `BRIAN_API_KEY` | Sí |
| Clave de IA para Juan (Anthropic, Meta u OpenAI) | Que Juan conteste | Solo si se usa Juan |
| Resend | Correo a clientes | No |
| Bot de Telegram (@BotFather) | Brian por Telegram, alertas, pruebas de Juan | No |
| App de Meta | Messenger e Instagram para Juan ([JUAN_META.md](JUAN_META.md)) | No |
| Un número de WhatsApp para el puente | Juan por WhatsApp ([JUAN_PUENTE.md](JUAN_PUENTE.md)) | No |
| Dominio propio con DNS en Cloudflare | Dirección definitiva (mientras tanto, `workers.dev`) | No al principio |

En la máquina de quien instala: `git`, Node 22, Python 3.12, PostgreSQL 16 (para `scripts/test.sh`), `openssl`; Docker
es opcional.

## 2. Copiar el repositorio

El repositorio original es público (`https://github.com/dcasapty/D_Casa_new_word`) y **no** está marcado como
plantilla (2026-10-18). Dos caminos:

**A. Copia propia, privada o pública (recomendado).** El dueño crea un repositorio **vacío** (sin README) en su cuenta
de GitHub y luego:

```bash
git clone --recurse-submodules --shallow-submodules https://github.com/dcasapty/D_Casa_new_word.git negocio
cd negocio
git remote rename origin upstream                       # el original, para traer mejoras (§10)
git remote add origin https://github.com/<dueño>/<repo>.git
git push -u origin main
```

Se conserva la historia, que hace falta para traer mejoras con `git merge`. Ojo: la historia incluye `fuentes/` (casi 1
GB de originales de fotos de D'CASA); el clon pesa alrededor de 1,5 GB.

**B. Fork.** Un fork de un repositorio público queda público. En un fork, GitHub **apaga Actions** hasta que alguien lo
encienda (*Actions › I understand my workflows, go ahead and enable them*).

**El submódulo `vendor/odoo`.** Es el código de Odoo 19.0, fijado a un commit, que se baja de
`https://github.com/odoo/odoo.git` (ver `.gitmodules`). No se copia al repositorio nuevo: el repositorio solo guarda a
qué commit apunta. **No se modifica nunca**; se actualiza moviendo ese commit (§10). Si el clon se hizo sin
`--recurse-submodules`: `git submodule update --init --depth 1` (o `make setup`).

**Repositorio público o privado.** En un repositorio **público** los registros de Actions son públicos (los secretos
salen tapados con `***`) y GitHub ofrece «Required reviewers» en los environments. En uno **privado** con plan Free, Pro
o Team no lo ofrece: por eso aquí la aprobación de producción es el clic de quien lanza el despliegue, solo desde `main`.

## 3. Primero en local

```bash
cd edge && npm ci && npm test && npm run typecheck && cd ..
cd juan && npm ci && npm test && npm run typecheck && cd ..
cd puente-wa && npm ci && npm test && npm run typecheck && cd ..
make setup                                   # .venv con las dependencias de Odoo
PYTHON=.venv/bin/python scripts/test.sh      # todos los módulos; tarda (~30 min). Necesita PostgreSQL (odoo/odoo)
ruff check addons
```

Así sabes que el clon está sano **antes** de cambiar nada. Después de cada cambio del §4, vuelve a correr lo que toque.

## 4. Lo que es propio de D'CASA y hay que cambiar

Todo lo de esta sección se busca de verdad con `rg` antes de dar el trabajo por hecho. Búsquedas que cubren casi todo:

```bash
rg -n "D'CASA|D&apos;CASA|dcasapty|La Chorrera|Panamá Oeste|Libertadores" \
   --glob '!vendor/**' --glob '!fuentes/**' --glob '!up media/**' --glob '!docs/**'
rg -n -i "1340B1|FED00F|0E2A6B|Anton|Oswald" addons edge --glob '!**/tests/**'
```

Y una por cada dato de la sección «Datos reales de la empresa» de [`CLAUDE.md`](../CLAUDE.md) (RUC, teléfono, correo):
`rg -n -F '<dato>'`. En este commit, «D'CASA» aparece en unos 220 archivos fuera de pruebas y documentos; casi todo es
el nombre en manifiestos, títulos de plantillas y comentarios. Lo que **se ve** o **cambia el comportamiento** está en
las listas de abajo.

### 4.1 Nombre, RUC, dirección, teléfono y correo

| Archivo | Líneas | Qué |
|---|---|---|
| `addons/dcasa_base/data/res_company_data.xml` | 7-22 | Nombre, dirección, RUC y DV, teléfono, correo, sitio, logo, colores, lema del encabezado. `noupdate`: en una base ya instalada se cambia en *Ajustes › Empresas* |
| `addons/website_dcasa/data/website_data.xml` | 5-6, 10-11 | Nombre del sitio, WhatsApp inicial, Instagram y TikTok |
| `addons/website_dcasa/views/legal_templates.xml` | 39-40, 93, 109-110 | Quiénes somos y correo en privacidad y términos |
| `addons/website_dcasa/views/layout_templates.xml` | 115, 277-303 | Barra de anuncios y pie: lema, RUC, dirección, correo, redes |
| `addons/website_dcasa/views/homepage_templates.xml` | 135, 149, 172-186, 226, 324 | Portada y «Visítanos»: dirección, teléfono, correo, Instagram, lema |
| `addons/website_dcasa/views/paginas_templates.xml` | 50-53 | Dirección y correo |
| `addons/website_dcasa/models/website.py` | 27-30, 38-96, 403 | Coordenadas de la tienda, mensaje de WhatsApp, SEO de la portada, textos de entregas y pagos, región |
| `addons/website_dcasa/models/tienda.py` | 32 | «Retiro en tienda (…)» |
| `addons/dcasa_interfaz/views/login_templates.xml` | 6 | Nombre y lema en la pantalla de entrada |
| `addons/dcasa_invoice/models/res_company.py` | 18-31 | Textos iniciales de garantía, cambios y términos de la factura |
| `addons/dcasa_abonos/models/condiciones.py` | 15-26 | Texto inicial de las condiciones de abono |
| `addons/dcasa_correo/models/correo.py` | 34-37 | Remitente y dirección de respuesta de fábrica |
| `addons/dcasa_correo/views/res_config_settings_views.xml` | 44, 48 | Ejemplos de correo en Ajustes |
| `addons/dcasa_base/__init__.py` | 179 | Nombre del almacén |
| `addons/dcasa_contabilidad/data/analitica_data.xml` | 9 | Cuenta analítica «Tienda física (…)» |
| `addons/dcasa_conversaciones/models/tienda.py` | 27 | Provincia en la dirección que da Juan |
| `addons/dcasa_conversaciones/models/ajustes.py` | 67-69, 78-80 | Bienvenida y nombre público de Juan (también en *Ajustes de Juan*) |
| `addons/dcasa_brian/models/conversacion.py` | 800 | Instrucciones de Brian («asistente de …, tienda de muebles en …») |
| `addons/dcasa_brian/models/herramientas_usuarios.py` | 33, 108, 113 | Ejemplos de correo del equipo |
| `addons/dcasa_seguridad/views/templates.xml` | 53 | Ejemplo de correo en `/master` |
| `addons/dcasa_socios/views/vendedores_views.xml` | 467 | Dirección de los términos de vendedores |
| Mensajes de validación con el teléfono de ejemplo | `dcasa_socios/models/res_partner.py:208`, `dcasa_socios/controllers/main.py:211`, `website_dcasa/models/website.py:142,157`, `dcasa_conversaciones/models/herramientas_juan.py:301`, `dcasa_conversaciones/controllers/juan.py:104` | Cambiar por un número de ejemplo genérico |
| `edge/src/arranque.ts` | 56 (y colores en el mismo archivo) | Página «estamos abriendo»: enlace `wa.me` con el número |
| `juan/src/dcasa/prompt.ts` | 79, 253 | Quién es Juan y de qué tienda |
| `juan/src/odoo-panel-sugerir.ts` / `juan/src/odoo-panel-resumir.ts` | 107 / 80 | Ídem, para los borradores y resúmenes |
| `juan/src/dcasa/salvaguardas.ts` | 217 | Dominio de las páginas legales que Juan puede citar |
| Cada `addons/*/__manifest__.py` | `author`, `website` | Autor y sitio (opcional) |

No hace falta tocar las migraciones viejas (`addons/*/migrations/`): solo corren al actualizar una base de D'CASA, no en
una instalación nueva.

### 4.2 Colores y tipografías

- Sitio: `addons/website_dcasa/static/src/scss/primary_variables.scss` líneas 11-22 (paleta `o-color-1` a `o-color-5`)
  y 26-61 (fuentes Anton, Oswald, Inter y formas).
- Panel de Odoo: `addons/dcasa_base/static/src/scss/primary_variables.scss` líneas 4-23 y
  `addons/dcasa_interfaz/static/src/scss/tokens.scss` (escala de azules `--dc-azul-*` y `--dc-amarillo`).
- Empresa: `primary_color` y `secondary_color` en `addons/dcasa_base/data/res_company_data.xml` 18-21.
- Hay colores sueltos en otros SCSS y en los íconos SVG (`rg -l -i "1340B1|FED00F"`): reportes contables, factura,
  correo, Brian, Conversaciones, Socios, Mi cuenta, Escáner.
- Fuentes autoalojadas en `static/src/fonts` de `website_dcasa`, `dcasa_base`, `dcasa_interfaz` y `dcasa_invoice`.
- Si cambias la tipografía de los documentos, cambia también `.github/workflows/ci.yml` línea 364 (busca `Anton` en el
  PDF de prueba).

### 4.3 Logo, favicon e imágenes

| Archivo | Dónde se usa |
|---|---|
| `addons/dcasa_base/static/img/logo.png` | Empresa, sitio (logo de fábrica, `website.py` línea 18), barra lateral, correos |
| `addons/dcasa_base/static/img/favicon.svg` | Ícono |
| `addons/website_dcasa/static/src/img/logo-200.webp`, `logo-400.webp` | Cabecera del sitio (`layout_templates.xml` 145-146) |
| `addons/website_dcasa/static/src/img/favicon.png` | Pestaña del sitio |
| `addons/dcasa_interfaz/static/src/img/favicon.png`, `favicon-192.png` | Pestaña del panel y manifiesto web |
| `addons/dcasa_interfaz/static/src/img/iconos/*.svg`, `addons/*/static/description/icon.*` | Íconos de las apps (con los colores de la marca) |
| `addons/website_dcasa/static/src/img/` (`hero*`, `cat-*`, `insp-*`, `split-*`, `black_weekend/`) | Portada, categorías y campaña. Confirmar con el dueño de dónde salen y si se pueden reusar |

### 4.4 WhatsApp

El número de todos los botones del sitio se cambia en *Sitio web › Configuración › Ajustes* (campo
`dcasa_whatsapp_number`). Su valor inicial está en `addons/website_dcasa/data/website_data.xml` línea 6. Fuera de Odoo
queda fijo en `edge/src/arranque.ts` línea 56. El CTA único del sitio es «Escríbenos por WhatsApp» (regla de marca).

### 4.5 Textos del sitio, políticas y condiciones

Dónde vive cada política y cómo se cambia: [PERMISOS.md › Políticas del sitio](PERMISOS.md#políticas-del-sitio-dónde-viven-y-cómo-se-cambian).
Además de los archivos del §4.1: preguntas frecuentes y textos de la portada en `homepage_templates.xml`, la tienda en
`tienda_templates.xml`, la campaña en `black_weekend_templates.xml` y `models/black_weekend.py` (y las variables
`DCASA_BLACK_WEEKEND*`: déjalas en `0` en los dos entornos si el negocio no tiene campaña), los términos de Socios
(`dcasa_socios/views/socios_templates.xml` 430) y de vendedores (`vendedores_templates.xml` 159), y los correos
(`dcasa_correo/data/mail_templates.xml`). El sitio **se edita por código**: no uses el constructor visual.

### 4.6 `puntos.json` y otras cifras del negocio

- `addons/dcasa_socios/data/puntos.json`: **todas** las cifras de Socios y del programa de vendedores. El negocio nuevo
  pone **las suyas**; nunca se copian las de D'CASA. Lo que no esté decidido queda en `null` o `PENDIENTE` (no se
  rellena a ojo). Sube `version`. Decide `vendedores.programaActivo`; deja `externosHabilitado` y `efectivoHabilitado`
  en `false`.
- `addons/dcasa_socios/data/premios_data.xml`: los premios de fábrica.
- `addons/dcasa_nomina/data/meta_ventas_data.xml`: la meta de ventas y el % del bono de D'CASA. El negocio pone los suyos
  o quita el registro. Las tasas legales (`nomina_data.xml`) las valida su contador.
- Tope de descuento de la Vendedora: en *Ajustes de Ventas* (10 % de fábrica).

### 4.7 El catálogo (no se copia)

`dcasa_catalogo` carga al instalarse los productos de D'CASA: `data/catalogo.json`, `data/fichas.json`,
`data/inventario_anterior.csv` y las fotos de `static/img/productos/`, más los códigos de Black Weekend
(`catalogo.py`, `BLACK_WEEKEND`). Para el negocio nuevo hay que **reemplazarlos** por los suyos (con
`scripts/importar_catalogo.py` desde «up media/») o vaciarlos, y borrar `fuentes/` y el contenido de `up media/`. Varias
pruebas usan ese catálogo (`dcasa_catalogo/tests`, `dcasa_migracion/tests`, `dcasa_brian/tests`): ajústalas en el mismo
commit. **Pregunta abierta:** no se probó que la instalación funcione con el catálogo vacío; córrelo con
`scripts/test.sh` antes de seguir.

### 4.8 El conocimiento de Juan

- Lo que Juan sabe del negocio vive en Odoo: *Conversaciones › Conocimiento del bot* (`dcasa.conocimiento`). La semilla
  es `addons/dcasa_conversaciones/data/conocimiento_data.xml` (dirección, horario y Socios se arman solos con los datos
  vivos; garantía y compra vienen inactivas).
- Horario, canales, nombre público, bienvenida, palabras prohibidas y proveedor de IA: *Conversaciones › Configuración ›
  Ajustes de Juan*.
- Las instrucciones fijas (tienda, ciudad, tono) están en `juan/src/dcasa/` (`prompt.ts`, `salvaguardas.ts`,
  `textos.ts`) y en los dos archivos `juan/src/odoo-panel-*.ts` del §4.1.

### 4.9 Dominios, direcciones y nombres de Cloudflare

Los nombres de los Workers, buckets y KV se pueden **dejar tal cual**: son por cuenta de Cloudflare. Lo que hay que
cambiar es el dominio y el subdominio `workers.dev` de la cuenta:

| Archivo | Líneas | Qué |
|---|---|---|
| `edge/wrangler.jsonc` | 58, 140 | `CANONICAL_HOST` de producción y staging |
| `edge/wrangler.jsonc` | 108-112, 173 | `routes` del dominio (descomentar cuando el DNS esté en Cloudflare) |
| `edge/wrangler.jsonc` | 158 | `TIENDA_AVISO_URL` de staging (`workers.dev`) |
| `edge/wrangler.jsonc` | 65-67, 146-148 | Black Weekend: `0` y fechas propias (o pasadas) |
| `edge/wrangler.jsonc` | 87, 170 | Puerta del equipo: empieza en `"0"` en los dos entornos (§7) |
| `juan/wrangler.jsonc` | 49, 80 | `URL_SITIO` de Juan |
| `puente-wa/wrangler.jsonc` | 62, 65, 110-111 | `PUENTE_BASE_URL` y `MEDIOS_HOSTS_PERMITIDOS` |
| `.github/workflows/desplegar-puente.yml` | 159 | Subdominio `workers.dev` con el que comprueba el puente |
| `addons/dcasa_conversaciones/models/panel_calculos.py` | 12 | Dominios del puente |
| `addons/dcasa_conversaciones/migrations/19.0.1.0.1/post-migrate.py` | 16 | (solo bases viejas) |
| `scripts/integracion_juan_datos.py` | 22 | `web.base.url` de la prueba de integración |
| `edge/CONTRATO_CONTENEDOR.md` | 79 | Documentación |

Y en GitHub, la variable `URL_SITIO` de cada environment (§5b.3).

### 4.10 Pruebas que comprueban datos de D'CASA

Cambiar un dato sin cambiar su prueba deja el CI en rojo. Las que hay que revisar (búscalas con las mismas `rg` del
principio, ahora sobre `tests/` y `test/`):

- `.github/workflows/ci.yml` líneas 303 y 305 (la portada debe decir el lema; `/socios` debe decir «Tus puntos») y 364.
- `edge/test/anfitrion-canonico.test.ts` 32-33 (`CANONICAL_HOST`), `puente-wa/test/despliegue.test.ts` 70-71 y 108.
- `addons/dcasa_base/tests/test_dcasa_base.py` (RUC y dirección), `addons/website_dcasa/tests/` (`test_legal.py`,
  `test_website_dcasa.py`, `test_tienda.py`…), `addons/dcasa_invoice/tests/` (los documentos aprobados en
  `tests/aprobado/*.html` llevan los datos de la empresa: se regeneran), `addons/dcasa_contactos/tests/`,
  `addons/dcasa_fe_pa/tests/`, `juan/test/dcasa/` y las capturas de referencia visual
  (`scripts/actualizar_referencias_visuales*.sh`).

### 4.11 `CLAUDE.md`, documentos y versiones estables

- [`CLAUDE.md`](../CLAUDE.md): reescribe «Proyecto», «Reglas de marca» (colores, tipografías, CTA, voz) y «Datos reales
  de la empresa» con los del negocio nuevo. Las reglas técnicas, las de Socios y las de Vendedores se quedan (son
  invariantes del código), salvo que el dueño decida otra cosa.
- `docs/LEEME_PRIMERO.md` (bitácora), `PRIORIDADES.md`, `PENDIENTES_DUENA.md`, `ESTADO.md` y los informes de `docs/gerencia/`
  son la historia de D'CASA: en la copia, vacía la bitácora y las prioridades y empieza las del negocio nuevo.
  `CONTEXTO_AGENTICO.md` se queda: son lecciones técnicas.
- `.github/versiones_estables.json` y las opciones de `.github/workflows/volver-a-estable.yml` apuntan a imágenes del
  registro de **D'CASA**, que no existen en la cuenta nueva. La prueba de lint exige al menos una entrada, así que se
  dejan hasta tener la primera versión estable propia y entonces se **reemplazan** (no uses ese botón antes).

### 4.12 El prefijo `dcasa_`

Se puede dejar tal cual: es el nombre técnico de los módulos, campos y variables (`DCASA_*`), no lo ve el cliente.
Renombrarlo toca cientos de archivos, las pruebas y la superficie RPC, y rompe la posibilidad de traer mejoras del
original (§10). No se recomienda.

## 5. Recursos en Cloudflare

| Recurso | Nombre (puede ser el mismo) | ¿Lo crea `wrangler deploy`? | Cómo |
|---|---|---|---|
| Plan Workers Paid | — | No | *Workers & Pages › Plans* |
| Bucket R2 de producción | `dcasa-respaldos` | **No** | *R2 › Create bucket*, ubicación **ENAM**, sin acceso público, sin reglas de ciclo de vida sobre `adjuntos/` ni `fuentes/` ([OPERACION.md › Preparación](OPERACION.md)) |
| Bucket R2 de staging | `dcasa-respaldos-staging` | **No** | Ídem |
| Token de R2 por bucket | — | No | *R2 › Manage API tokens › Create Account API token*, **Object Read & Write** solo sobre ese bucket. Da `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY` |
| Token de API para GitHub | — | No | *Manage Account › Account API Tokens*: Workers (rol de administrador del producto, para crear Workers), **Containers: Edit**, **Account Settings: Read**, **Workers KV Storage: Edit**, **Cloudflare Images: Edit** (lo pide el puente al subir su imagen) y, con dominio, *Zone › Workers Routes: Edit*. Los nombres exactos cambian: si wrangler da error de autorización, el mensaje dice cuál falta |
| Workers `dcasa`, `dcasa-staging`, `dcasa-juan`, `dcasa-juan-staging`, `dcasa-puente-wa`, `dcasa-puente-wa-staging` | ídem | **Sí** | Con sus flujos (§6) |
| Durable Objects y apps de contenedores | `OdooContainer`, `Conversacion`, `Global`, `PuenteWa` | **Sí** | Migración `v1` de cada `wrangler.jsonc` |
| KV de la caché | `dcasa-tienda`, `dcasa-staging-tienda` | **Sí** (aprovisionamiento automático) | — |
| Imagen de Odoo en el registro | `dcasa-odoo:<SHA>` | La sube `desplegar.yml` (`wrangler containers push`) | — |
| Aplicación de Access (puerta del equipo) | una por entorno | No | [SEGURIDAD_ACCESO.md §8.4](SEGURIDAD_ACCESO.md) |
| Widget de Turnstile | — | No | Opcional |
| D1 | — | — | No se usa |

Anota el **Account ID** (página principal de *Workers & Pages*): va como secreto en GitHub, nunca en el repositorio.

## 5b. GitHub

### 5b.1 Environments

*Settings › Environments*: crear **`staging`** y **`production`**. En `production`, *Deployment branches and tags* →
*Selected branches* → solo `main`. Si el repositorio es público, se puede además exigir un revisor (*Required
reviewers*).

### 5b.2 Secretos de cada environment

Cada entorno lleva **sus propios** valores: staging nunca comparte bucket, token ni clave con producción. En **negrita**
los que **no se rotan nunca**: se generan una vez, se guardan en el gestor de contraseñas del dueño **antes** del primer
despliegue (Cloudflare no deja volver a leerlos) y no se cambian.

| Nombre | Obligatorio | Para qué | Cómo se genera |
|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | sí | Desplegar | Token del §5 |
| `CLOUDFLARE_ACCOUNT_ID` | sí | La cuenta | Panel de Cloudflare |
| `R2_ACCESS_KEY_ID` | sí | Respaldos y adjuntos | Token de R2 del bucket del entorno |
| `R2_SECRET_ACCESS_KEY` | sí | Ídem | Ídem (se muestra una sola vez) |
| **`PGBACKREST_CIPHER_PASS`** | sí | Cifra los respaldos. Perderla = respaldos ilegibles | `openssl rand -hex 32` |
| `RESPALDO_TOKEN` | sí | Autoriza el respaldo previo al despliegue | `openssl rand -hex 32` |
| `ODOO_ADMIN_PASSWORD` | sí | Clave inicial del usuario `admin` | Gestor de contraseñas (larga y al azar) |
| `ODOO_MASTER_PASSWORD` | sí | Contraseña maestra, **distinta** de la anterior | Gestor de contraseñas |
| **`DCASA_PIN_PEPPER`** | sí | Pimienta del PIN de los socios. Cambiarla invalida el PIN de todos | `openssl rand -hex 32` |
| `BRIAN_API_KEY` | sí | IA de Brian (en staging, una clave de pruebas con tope de gasto) | Panel del proveedor |
| `RESEND_API_KEY` | no | Correo a clientes | Resend, permiso «solo envío» ([CORREO.md](CORREO.md)) |
| `TELEGRAM_BOT_TOKEN` | no | Brian por Telegram y alertas | @BotFather |
| `BRIAN_TELEGRAM_SECRETO` | no | Ruta y encabezado del webhook de Brian | `openssl rand -hex 32` |
| `TIENDA_FEED_TOKEN` | no (sí para la caché) | Odoo y el Worker se reconocen | `openssl rand -hex 32` |
| `TURNSTILE_SECRET` | no | Turnstile | Panel de Turnstile |
| `DCASA_PUERTA_RUTA` | no (las 4 juntas) | Ruta de la puerta | `/master` |
| `DCASA_PUERTA_SECRETO` | no | Firma la cookie y las cabeceras de la puerta | `openssl rand -hex 32` |
| `DCASA_ACCESS_EQUIPO` | no | Equipo de Zero Trust | `https://<equipo>.cloudflareaccess.com` |
| `DCASA_ACCESS_AUD` | no | La aplicación de Access | Su *AUD Tag* |

### 5b.3 Variables de cada environment

| Nombre | Obligatoria | Valor |
|---|---|---|
| `URL_SITIO` | sí | `https://dcasa.<subdominio>.workers.dev` (staging: `https://dcasa-staging.<subdominio>.workers.dev`) hasta tener dominio; sin `/` final |
| `CANONICAL_HOST` | no | Vacía = el anfitrión de `URL_SITIO` (lo correcto mientras no haya dominio) |
| `R2_ENDPOINT` | no | Solo si el bucket está en otra jurisdicción |
| `BRIAN_PROVEEDOR`, `BRIAN_MODELO`, `BRIAN_BASE_URL` | no | [BRIAN.md › Configuración](BRIAN.md) |

El despliegue valida todo antes de tocar Cloudflare (`.github/scripts/validar_entorno.sh`): falta, vacío, marcador
(`CAMBIAR`, `PENDIENTE`, `<...>`), menos de 32 caracteres en las tres claves largas, maestra igual a la de `admin`.

### 5b.4 Secretos del repositorio (opcionales)

`PREVIEW_ADMIN_PASSWORD` y `BRIAN_API_KEY_PRUEBAS` para *Previsualización*; `UP_MEDIA_TOKEN` solo si `main` tiene una
protección que el `GITHUB_TOKEN` no puede saltar (*up media* hace commit a `main`).

### 5b.5 Secretos que van en el panel de Cloudflare (no en GitHub)

Se pegan en *Workers › <Worker> › Settings › Variables and Secrets* **después** de que el Worker exista. Los despliegues
no los borran.

| Worker | Secretos | Variables |
|---|---|---|
| `dcasa` / `dcasa-staging` | `JUAN_ODOO_TOKEN`, `JUAN_WORKER_TOKEN` (`openssl rand -hex 32`, el **mismo valor** que en Juan) | `JUAN_URL` (dirección del Worker de Juan), `BRIAN_TELEGRAM_CHATS`, `DCASA_ALERTA_TELEGRAM_CHAT` |
| `dcasa-juan` / `-staging` | `JUAN_ODOO_TOKEN`, `JUAN_WORKER_TOKEN`, la clave de IA elegida en Odoo (`ANTHROPIC_API_KEY`, `META_AI_API_KEY` u `OPENAI_API_KEY`), `WA_TOKEN`, `TELEGRAM_BOT_TOKEN_JUAN`, `TELEGRAM_WEBHOOK_SECRET_JUAN`, `META_*` | `URL_PUBLICA`, `ALERTA_TELEGRAM_CHAT_ID` ([JUAN_WORKER.md §5](JUAN_WORKER.md)) |
| `dcasa-puente-wa` / `-staging` | `WA_TOKEN` (el mismo que en Juan), **`WA_SESION_CLAVE`** (se genera una vez y no se cambia salvo con la rotación de [JUAN_PUENTE.md §C](JUAN_PUENTE.md)) | opcionales `TELEGRAM_BOT_TOKEN_JUAN`, `ALERTA_TELEGRAM_CHAT` |

## 6. Primer despliegue

El orden importa: un Worker no se despliega si su service binding apunta a otro que todavía no existe.

**Staging:**

1. Con el §4 hecho y las pruebas en verde, sube la rama. *Actions › CI/CD › Run workflow*, `desplegar_en = staging`.
   Corre todas las pruebas, despliega `dcasa-staging` (el primer arranque, con el bucket vacío, crea la base e instala
   los módulos: unos minutos) y después Juan staging.
2. Abre `<URL_SITIO>/__edge/health`: debe dar 200 con `version`, `base_al_dia: true` y `humo: ok`.
3. Pega los secretos del panel (§5b.5) en `dcasa-staging` y `dcasa-juan-staging`. `GET <juan>/salud` dice qué falta.
   Las variables nuevas del panel de `dcasa-staging` llegan a Odoo al reiniciar o en el siguiente despliegue.
4. Puente (si se usa WhatsApp): *Actions › Desplegar puente de WhatsApp*, `entorno = staging`, primero `dry-run`, luego
   `desplegar`. Pega `WA_TOKEN` y `WA_SESION_CLAVE`. Después descomenta el binding `PUENTE` de staging en
   `juan/wrangler.jsonc` (línea 75) y vuelve a desplegar Juan. Vincula el número con el QR ([JUAN_PUENTE.md](JUAN_PUENTE.md)),
   con un número de **prueba** en staging.

**Producción** (con el «sí» del dueño, staging revisado y el código en `main`):

1. *Actions › Desplegar › Run workflow* en `main`: `entorno = production`, el `imagen_digest` y el `app_version` (el SHA
   de la rama que construyó el CI) del resumen del despliegue de staging, `respaldo_previo = true` (en el primer
   despliegue no hay Worker y se salta solo). O bien *CI/CD* en `main` con `desplegar_en = produccion`.
2. *Actions › Desplegar Juan*, `entorno = production`, `dry_run` desmarcado.
3. Secretos del panel de `dcasa` y `dcasa-juan`; puente de producción como en staging (binding `PUENTE` en la línea 33).
4. Dominio: cuando el DNS esté en Cloudflare, descomenta `routes` en `edge/wrangler.jsonc`, cambia `URL_SITIO` y
   despliega ([DESPLIEGUE.md §6](DESPLIEGUE.md)). Los QR impresos de Socios deben apuntar al dominio, nunca a
   `workers.dev`.

## 7. Primer arranque

1. **El administrador.** Entra en `<URL_SITIO>/web/login` con el usuario `admin` y la clave `ODOO_ADMIN_PASSWORD` (el
   arranque la pone en lugar de `admin/admin`; si el dueño ya la cambió, no la toca). `admin` nace en Gerencia.
2. **Doble factor.** Con `DCASA_2FA_OBLIGATORIO = "1"` (el valor de `edge/wrangler.jsonc`), el administrador enrola la app
   de códigos al entrar. Guía y rescate si se pierde el teléfono: [SEGURIDAD_ACCESO.md §2-§4](SEGURIDAD_ACCESO.md).
3. **Usuarios.** Uno por persona (*Ajustes › Usuarios*), con su rol en la sección D'CASA (Vendedora o Gerencia) y Nómina
   si corresponde. Nunca se comparte el de `admin` ([PERMISOS.md](PERMISOS.md), [EQUIPO.md](EQUIPO.md)).
4. **Datos del negocio en Odoo:** *Ajustes › Empresas* (datos y pestaña «Documentos D'CASA»: garantía, cambios,
   condiciones de abono), *Sitio web › Configuración › Ajustes* (WhatsApp, días del apartado), *Ajustes de Ventas*
   (tope de descuento), *Brian › Ajustes* (tope de gasto de IA), *Conversaciones › Ajustes de Juan*.
5. **La puerta del equipo (`/master`)**, cuando todo lo anterior funcione: crear la aplicación de Access y los cuatro
   secretos ([SEGURIDAD_ACCESO.md §8.4](SEGURIDAD_ACCESO.md)), y encender por pasos `DCASA_PUERTA_OBLIGATORIA`: `"0"`
   (probar que abre) → `"avisar"` (unos días) → `"1"`. Nunca directo a `"1"`: en D'CASA eso dejó al equipo sin entrada.
6. Datos de un sistema anterior: *Ajustes › Cargar datos del sistema anterior* ([MIGRACION.md](MIGRACION.md)); nunca por
   el repositorio.

## 8. Lista de comprobación final

- [ ] `GET /__edge/health` en los dos entornos: 200, `version` = el commit desplegado, `base_al_dia: true`, `humo: ok`.
- [ ] Humo a mano: portada, `/shop`, una ficha, `/socios`, `/mi-cuenta`, `/privacidad`, `/terminos`; en el panel:
      Inicio, Conversaciones, una cotización, «Imprimir documentos» (factura en PDF con la marca nueva).
- [ ] Como Vendedora y como Gerencia: la vendedora no ve costos, ganancia, Nómina ni facturas de proveedor.
- [ ] Juan: `GET /salud` sin secretos faltantes; una prueba por Telegram ([JUAN_WORKER.md §6](JUAN_WORKER.md)).
- [ ] Respaldos: en el bucket aparecen `pgbackrest/` y `adjuntos/`; al día siguiente, `pg_dump/`. Respaldo a mano:
      `curl -fsS -X POST -H "Authorization: Bearer $RESPALDO_TOKEN" <URL_SITIO>/__edge/respaldo` (el token desde una
      variable de la terminal, nunca escrito en el chat).
- [ ] Simulacro: el job «Simulacro de restauración» del CI en verde, y el simulacro con R2 de verdad en staging
      ([OPERACION.md › Simulacro mensual de restauración](OPERACION.md)).
- [ ] Barandas de costo: alertas de presupuesto y reglas de ciclo de vida de R2 ([OPERACION.md](OPERACION.md)).
- [ ] Copia de `PGBACKREST_CIPHER_PASS`, `DCASA_PIN_PEPPER` y `WA_SESION_CLAVE` de cada entorno en el gestor de
      contraseñas del dueño.
- [ ] Primera versión estable propia en `.github/versiones_estables.json` y en `volver-a-estable.yml` (§4.11).

## 9. Lo que no se copia nunca

- **Datos de clientes y del equipo** de D'CASA (ni de ningún otro negocio).
- **La base de datos ni los buckets de R2** de otro negocio: cada negocio arranca con su base vacía y sus propios buckets.
- **Secretos**: ningún token, clave, pimienta ni clave de cifrado se reusa entre negocios ni entre entornos.
- **Las cifras de `puntos.json`, los premios, la meta del bono, el catálogo, las fotos** (`fuentes/`, `up media/`,
  `static/img/productos/`) y las versiones estables de D'CASA.
- **Los informes y la bitácora** de D'CASA en `docs/` (historia, no instrucciones para el negocio nuevo).

## 10. Cómo traer las mejoras del original

```bash
git fetch upstream
git switch -c traer-mejoras origin/main
git merge upstream/main          # los conflictos caen casi siempre en los archivos del §4
```

1. Resuelve los conflictos conservando los datos del negocio nuevo y el código nuevo del original. Revisa los commits
   que traen `puntos.json` o datos de D'CASA: lo de D'CASA no se acepta.
2. Si el original subió la `version` de un módulo o trae `migrations/`, lee el cambio antes: al desplegar, el arranque
   corre `odoo -u` sobre la base del negocio.
3. Si cambió el commit de `vendor/odoo`: `git submodule update --init --depth 1`.
4. Corre todas las pruebas en local, despliega a staging, revisa, y recién después a producción con la receta de
   [ARQUITECTURA.md §6.2](ARQUITECTURA.md).
5. Nunca bajes una imagen más vieja sobre una base ya actualizada sin restaurar antes la base
   ([CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md)).

Cuantos menos archivos del núcleo cambie el negocio nuevo (idealmente solo los del §4), más fácil es traer mejoras.

## 11. Preguntas abiertas

- No se probó la instalación con el catálogo vacío ni con los datos de otro negocio (§4.7): hay que comprobarlo con
  `scripts/test.sh` en la primera réplica.
- El permiso exacto del token de Cloudflare para Workers AI al desplegar Juan (no está documentado en el repositorio).
- Si las fotos de la portada y las categorías (`website_dcasa/static/src/img/`) se pueden reusar en otro negocio: el
  README dice que las de ambiente son del tema Loftspace de Odoo (LGPL-3); el origen de las demás no está escrito.
- Si `/web/signup` (crear cuenta de cliente) está abierto: no hay ajuste en el código que lo fije.
