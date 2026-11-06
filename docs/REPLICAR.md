# Cómo instalar este sistema para otra empresa

Guía completa para clonar este repositorio e instalar el sistema (Odoo 19 Community + sitio y tienda + Socios +
Juan, Brian y Sofía, en Cloudflare) para **otra empresa**, de punta a punta. Está escrita para una persona técnica (o
una sesión de Claude) que la sigue con solo el enlace del repositorio, sin adivinar.

**Verificada contra el código el 2026-11-06** (commit base `700c34a`). Cada dato lleva el archivo (y la línea cuando
ayuda) de donde sale. Si algo de aquí no coincide con el código, **manda el código**: dilo y corrige esta guía (§13).

| Archivo | Qué tiene |
|---|---|
| Este archivo | Resumen, qué incluye, el paso a paso, cómo adaptar y traer mejoras, la lista final y las trampas |
| [replicar/VALORES_DE_LA_EMPRESA.md](replicar/VALORES_DE_LA_EMPRESA.md) | **Cada** dato de D'CASA en el código y la configuración, con archivo:línea y qué poner |
| [replicar/CUENTAS_Y_SECRETOS.md](replicar/CUENTAS_Y_SECRETOS.md) | Las cuentas que hay que crear y **cada** secreto y variable por nombre, dónde va y de dónde sale |

Antes de empezar conviene leer [ARQUITECTURA.md](ARQUITECTURA.md) (las piezas), [MODULOS.md](MODULOS.md) (qué hace
cada módulo) y [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md) (lo que ya falló y por qué; las trampas que pegan en una
instalación nueva están resumidas en el §10).

## Resumen para la dueña

- **Qué es.** El mismo sistema que usa D'CASA (ventas, inventario, facturas, contabilidad, nómina, el sitio con su
  tienda, el programa de puntos y los asistentes Juan, Brian y Sofía) se puede instalar para otra empresa. Se copia el
  **programa**, no la información.
- **Qué nunca se copia.** Nada de D'CASA: ni clientes, ni ventas, ni la base de datos, ni los respaldos, ni el catálogo
  y sus fotos, ni las claves, ni las cifras del programa de puntos. La otra empresa empieza con su sistema vacío.
- **Qué pone la otra empresa.** Sus cuentas (Cloudflare, GitHub, el proveedor de inteligencia artificial y, si quiere
  WhatsApp, Meta), sus datos, su logo y sus colores, y sus reglas y cifras. Las cifras las decide quien dirige esa empresa: el
  sistema no inventa ninguna. Las políticas (privacidad, garantía, términos) las revisa su asesoría legal; los
  impuestos y la nómina, quien lleve su contabilidad.
- **Está hecho para Panamá.** Impuesto ITBMS, RUC con dígito verificador, nómina panameña, factura electrónica de la
  DGI (preparada), celulares de Panamá. Para una empresa de otro país hace falta trabajo que esta guía no cubre.
- **Quién hace qué.** Quien instala copia el programa, lo adapta, corre las pruebas y lanza las instalaciones. Quien
  dirige la otra empresa crea las cuentas, paga los planes, guarda y pega las claves (nunca por chat) y da el «sí»
  antes de abrir al público.
- **No toca a D'CASA.** Instalarlo para otra empresa no cambia nada del sistema de D'CASA.

## 0. Reglas para quien instala

- **Nunca pidas un secreto por el chat.** Di *dónde* se pega (GitHub › Environments o el panel de Cloudflare) y
  comprueba que quedó cargado sin ver su valor ([CUENTAS_Y_SECRETOS.md §9](replicar/CUENTAS_Y_SECRETOS.md)).
- **Nunca copies datos de D'CASA** al negocio nuevo (§11). Los datos de personas viven solo en Odoo: ni en el
  repositorio, ni en documentos, ni en pruebas. Este repositorio es **público**.
- **No inventes contenido:** precios, cifras, plazos, garantías o testimonios los pone la gerencia del negocio nuevo. Lo no
  decidido queda vacío, en `null` o en `PENDIENTE` (regla 1 de Socios en [`CLAUDE.md`](../CLAUDE.md)).
- **No recortes pruebas.** Si cambias un dato que una prueba comprueba, cambias la prueba en el mismo commit y corres
  `scripts/test.sh` hasta que pase ([VALORES_DE_LA_EMPRESA.md §P](replicar/VALORES_DE_LA_EMPRESA.md)).
- **`vendor/odoo` no se modifica nunca**: todo cambio de comportamiento se hereda desde un módulo de `addons/`
  (`CLAUDE.md`, «Estructura»).
- **A producción solo con el «sí» de la gerencia del negocio** y con staging revisado.

## 1. Qué incluye el sistema

### 1.1 Las piezas

| Pieza | Carpeta | Qué es |
|---|---|---|
| Odoo 19 Community | `vendor/odoo` (submódulo, `.gitmodules`) | El ERP, fijado a un commit de la rama 19.0. No se toca |
| 31 módulos propios | `addons/` | Prefijo `dcasa_` (y `website_dcasa`). El contenedor instala 30: la lista `ODOO_MODULES` de `docker/entrypoint.sh:176`; `dcasa_fe_pa` es opcional y no se instala. `make init` usa una lista más corta (`Makefile:5`) |
| Imagen de producción | `docker/` | Odoo + PostgreSQL 16 en **un** contenedor; `entrypoint.sh` restaura la base desde R2, instala o actualiza módulos y arranca |
| Worker `dcasa` | `edge/` | La puerta de entrada pública: seguridad, caché, puerta del equipo, respaldo a mano, crons, y el contenedor de Odoo |
| Worker `dcasa-juan` | `juan/` | Juan, el asistente de los clientes (Durable Objects; WhatsApp por la API oficial de Meta, Telegram, Messenger e Instagram preparados) |
| Worker `dcasa-puente-wa` | `puente-wa/` | Puente de WhatsApp por QR. Opcional; **nunca se desplegó en producción** |
| Flujos de GitHub | `.github/workflows/` | `ci.yml` (pruebas y, a mano, despliegue), `desplegar.yml`, `desplegar-juan.yml`, `desplegar-puente.yml`, `volver-a-estable.yml`, `up-media.yml`, `preview.yml`, `limpiar-artefactos.yml` ([ARQUITECTURA.md §6.1](ARQUITECTURA.md)) |
| Scripts | `scripts/` | `test.sh`, respaldo, simulacro de restauración, importar el catálogo, íconos de la marca, integración de Juan |

Los datos permanentes viven en el PostgreSQL del contenedor, respaldado sin parar en R2 (WAL cada ~60 s y volcado
diario); los adjuntos (fotos y PDF) van a R2 (`dcasa_adjuntos_r2`); Juan y el puente guardan solo memoria de trabajo
([ARQUITECTURA.md §3-§4](ARQUITECTURA.md)).

### 1.2 Los módulos, por área

Sacado de cada `addons/*/__manifest__.py` (detalle en [MODULOS.md](MODULOS.md)).

| Área | Módulo | Qué hace, en una línea |
|---|---|---|
| Base | `dcasa_base` | Empresa, Panamá (plan contable, ITBMS 7 %, RUC con DV), roles Vendedora, Caja y Gerencia, reglas contables, tope de descuento |
| Ventas y documentos | `dcasa_invoice` | Factura, cotización, compra y entrega con la marca, en español, con monto en letras; «Imprimir documentos» |
| | `dcasa_abonos` | Hoja «Condiciones de abono» (copia cliente y empresa) |
| | `dcasa_catalogo` | Carga el catálogo (Excel + fotos) **al instalar**, código público del producto, combos cama + colchón |
| | `dcasa_barras` | Lector de códigos de barras, etiquetas y panel de Bodega |
| | `dcasa_existencias` | Mermas, daños, muestras y regalos; bitácora de bodega; alertas por Telegram (apagadas) |
| | `dcasa_marketing` | Fotos del producto en grande y la app Marketing (lo que se vende, lo quieto, fotos que faltan) |
| Sitio y clientes | `website_dcasa` | Sitio y tienda con la marca, mantenidos desde el código (sin constructor visual) |
| | `dcasa_mi_cuenta` | Panel del cliente en `/mi-cuenta` (compras, abonos, entregas, puntos) |
| | `dcasa_tienda_borde` | Avisa al Worker qué páginas cambiaron (caché de páginas anónimas) |
| | `dcasa_correo` | Correo a clientes por Resend (apagado de fábrica) |
| | `dcasa_meta_catalogo` | El catálogo por URL para los anuncios de Meta |
| | `dcasa_meta_eventos` | Píxel de Meta con consentimiento y ventas pagadas a la Conversions API (todo apagado) |
| Programas | `dcasa_socios` | Socios (puntos y referidos) y programa de vendedores, con libros inmutables |
| Contabilidad y personal | `dcasa_contabilidad` | Reportes con comparativos, bancos y conciliación, cierre de mes, presupuestos, cheques |
| | `dcasa_consolidacion` | Estados financieros de varias empresas del grupo en uno |
| | `dcasa_nomina` | Planilla de Panamá, décimo tercer mes, vacaciones, liquidación, reembolsos, bono por meta |
| | `dcasa_equipo` | Ícono y visibilidad del menú Empleados |
| | `dcasa_fe_pa` | Factura electrónica de la DGI (preparación con PAC simulado; **no se instala**) |
| Contactos y CRM | `dcasa_contactos` | Una persona, una ficha: celular, correo y RUC no se repiten |
| | `dcasa_conversaciones` | Bandeja de conversaciones de Juan, CRM automático y la API para el Worker de Juan |
| | `dcasa_sofia` | Sofía: revisa el CRM con un botón y cada mañana y propone; una persona aprueba |
| Asistentes y ayuda | `dcasa_brian` | Brian, el asistente del panel (chat, Telegram y MCP) |
| | `dcasa_guia` | «¿Qué necesitas hacer hoy?»: atajos en palabras sencillas |
| | `dcasa_interfaz` | Inicio por rol, Estadísticas, íconos propios, sin avisos de pago |
| Plataforma | `dcasa_sesiones` | Sesiones en PostgreSQL (el contenedor no tiene disco) y `/dcasa/salud` |
| | `dcasa_adjuntos_r2` | Guarda fotos y PDF en R2 en lugar de la base |
| | `dcasa_seguridad` | Doble factor, bloqueos, registro de accesos, puerta del equipo, Turnstile, robots.txt |
| Migración | `dcasa_migracion` | Carga única desde el sistema anterior |

### 1.3 Lo que es de Panamá y lo que sirve tal cual

| De Panamá | Dónde |
|---|---|
| Plan contable `l10n_pa` e ITBMS 7 % que se **suma** al precio | `addons/dcasa_base/__manifest__.py` (`depends`), `addons/dcasa_base/__init__.py:9,38-` |
| RUC con dígito verificador (campo `l10n_pa_dv`) en la empresa y en los documentos | `addons/dcasa_base/data/res_company_data.xml:12-13`, `dcasa_invoice` |
| Factura electrónica de la DGI (rFE, CUFE, PAC) | `addons/dcasa_fe_pa` ([FACTURA_ELECTRONICA.md](FACTURA_ELECTRONICA.md)) |
| Planilla panameña (seguro social, seguro educativo, ISR, décimo tercer mes) | `addons/dcasa_nomina/data/nomina_data.xml` (tasas sin verificar contra la Gaceta Oficial: las valida quien lleve la contabilidad) |
| Celular de 8 dígitos con +507 como llave del cliente | `addons/dcasa_socios/models/bien_escrito.py`, `addons/dcasa_contactos/models/claves.py` |
| Zona horaria `America/Panama`, español `es_419` con números al estilo de Panamá | `addons/dcasa_base/__init__.py:7-8,217-`, `docker/entrypoint.sh:177`; crons en UTC pensados para UTC−5 |
| Formas de cobro (Yappy) y financieras locales | `addons/dcasa_base/__init__.py:12-24` |
| Privacidad según la Ley 81 de 2019 (ANTAI) | `addons/website_dcasa/views/legal_templates.xml` |
| Juan pone «+ ITBMS» a todo precio | `juan/src/dcasa/salvaguardas.ts:101-110` |

**Sirve tal cual** (con los datos y la marca del negocio nuevo): la plataforma en Cloudflare (borde, contenedor,
respaldos, adjuntos en R2, sesiones, seguridad y puerta del equipo), Brian, el motor de Juan y sus canales, Sofía, la
Guía, Contactos sin duplicados, el motor de Socios y vendedores (con **sus** cifras), CRM, Mi cuenta, Interfaz,
Barras, Existencias, Marketing, Migración, Contabilidad y Consolidación (sobre el plan contable de Panamá).

## 2. Requisitos

- **Cuentas:** la tabla completa está en [CUENTAS_Y_SECRETOS.md §1](replicar/CUENTAS_Y_SECRETOS.md). Obligatorias:
  Cloudflare con **Workers Paid** (Containers solo existe en el plan de pago) y R2, GitHub con Actions, un proveedor de
  IA para Brian (el despliegue exige `BRIAN_API_KEY`) y un gestor de contraseñas.
- **En la máquina de quien instala:** `git`, Node 22 (el de los flujos, `.github/workflows/desplegar.yml:155`), Python
  3.12, PostgreSQL 16 (para `scripts/test.sh`; usuario y clave `odoo`/`odoo` por defecto, `scripts/test.sh:10-14`),
  `openssl` y `rg`. Docker es opcional (`docker-compose.yml`).
- **Costo:** el plan Workers Paid, el contenedor de producción `standard-1` encendido 24/7 (`edge/wrangler.jsonc:22-25`;
  staging `basic`, `:132`), R2 por encima de lo gratis, Workers AI si Juan transcribe audio, y lo que gasten los
  proveedores de IA. La tabla de [OPERACION.md › Cuánto cuesta](OPERACION.md) todavía habla de `basic` en producción:
  revisar *Billing* el primer mes.

## 3. Copiar el repositorio

El original es público (`https://github.com/dcasapty/D_Casa_new_word`, ver `README.md`).

**A. Copia propia con la historia (recomendado).** La gerencia del negocio crea un repositorio **vacío** (sin README) en su cuenta de
GitHub, y quien instala:

```bash
git clone --recurse-submodules --shallow-submodules https://github.com/dcasapty/D_Casa_new_word.git negocio
cd negocio
git remote rename origin upstream                 # el original, para traer mejoras (§8)
git remote add origin https://github.com/<cuenta>/<repo>.git
git push -u origin main
```

La historia hace falta para traer mejoras con `git merge`. Pesa: la carpeta de objetos de git medía ~1,1 GB el
2026-11-06, sobre todo por las fotos originales de `fuentes/` (994 MB en el árbol). Borrar `fuentes/` en la copia
aligera el árbol, no la historia.

**B. Fork.** Un fork de un repositorio público queda público, y GitHub **apaga Actions** en el fork hasta que alguien
lo encienda (*Actions › I understand my workflows, go ahead and enable them*).

**El submódulo `vendor/odoo`** apunta a un commit de `https://github.com/odoo/odoo.git` rama 19.0 (`.gitmodules`). El
repositorio guarda solo a qué commit apunta. Si el clon se hizo sin `--recurse-submodules`:
`git submodule update --init --depth 1` (o `make setup`). Se actualiza moviendo ese commit, nunca editándolo
([DESPLIEGUE.md › Operación](DESPLIEGUE.md)).

**¿Público o privado?** En un repositorio público los registros de Actions son públicos (los secretos salen tapados con
`***`) y GitHub ofrece *Required reviewers* en los environments. En uno privado de los planes Free, Pro o Team no lo
ofrece: la aprobación de producción es el clic de quien lanza el despliegue, solo desde `main`
(`.github/workflows/desplegar.yml:74-76`).

## 4. Lo propio de D'CASA que hay que cambiar

La lista completa, con archivo:línea, está en [VALORES_DE_LA_EMPRESA.md](replicar/VALORES_DE_LA_EMPRESA.md). En orden:

1. **Datos de la empresa** (nombre, RUC y DV, dirección, teléfono, correo, redes, coordenadas): §A.
2. **Marca** (colores, tipografías autoalojadas, logo; los íconos se regeneran con `python scripts/iconos_de_la_marca.py`): §B.
3. **Textos del sitio y políticas** (privacidad con su párrafo de IA, términos, garantía, cambios, abonos), con su asesoría legal: §C.
4. **WhatsApp del sitio**: §D. **Correo** (remitente y plantillas): §E.
5. **Cifras de Socios y vendedores** (`addons/dcasa_socios/data/puntos.json`; nunca las de D'CASA; `null`/`PENDIENTE`
   no se rellena a ojo): §F. **Nómina y formas de cobro**: §G.
6. **Juan** (quién es, de qué tienda, su conocimiento), **Sofía**, **Brian** y **la Guía**: §H a §K.
7. **Dominios, subdominio `workers.dev` y nombres de Cloudflare**: §M y §N.
8. **Las pruebas que fijan esos datos**, en el mismo commit: §P.

### 4.1 El catálogo no se copia

`dcasa_catalogo` carga **al instalarse** (`post_init_hook`, `addons/dcasa_catalogo/__init__.py:6-23`) los productos,
precios, existencias y fotos de D'CASA (`data/catalogo.json`, `data/fichas.json`, `data/inventario_anterior.csv`,
`static/img/productos/`) y marca los de Black Weekend (`addons/dcasa_catalogo/catalogo.py:281`). Antes del primer
despliegue hay que **reemplazarlos** por los del negocio nuevo o vaciarlos, y borrar `fuentes/` y el contenido de
`up media/`. El importador `scripts/importar_catalogo.py` está hecho a la medida del Excel de D'CASA
([VALORES_DE_LA_EMPRESA.md §L](replicar/VALORES_DE_LA_EMPRESA.md)). Varias pruebas usan ese catálogo
(`addons/dcasa_catalogo/tests/`, `juan/test/integracion/historia.ts`): se ajustan en el mismo commit. **No está
probado** que la instalación funcione con el catálogo vacío (§12): córrelo con `scripts/test.sh` antes de seguir.

### 4.2 El prefijo `dcasa_` se queda

Es el nombre técnico de módulos, campos, parámetros y variables (`DCASA_*`); el cliente no lo ve. Renombrarlo toca
cientos de archivos, las pruebas y la superficie RPC, y rompe la posibilidad de traer mejoras del original (§8).

### 4.3 `CLAUDE.md` y la documentación

- [`CLAUDE.md`](../CLAUDE.md): reescribir «Proyecto», «Reglas de marca» y «Datos reales de la empresa» con los del
  negocio nuevo. Las reglas técnicas, las de Socios y las de vendedores se quedan: son invariantes del código.
- `docs/LEEME_PRIMERO.md` (su bitácora), `docs/PRIORIDADES.md`, `docs/historico/` y `docs/gerencia/` son la
  historia de D'CASA: en la copia se vacían y se empiezan los del negocio nuevo.
  `docs/CONTEXTO_AGENTICO.md` se queda (son lecciones técnicas).
- `.github/versiones_estables.json` y las opciones de `.github/workflows/volver-a-estable.yml:22-24` apuntan a imágenes
  del registro de **D'CASA**, que no existen en la cuenta nueva. La prueba del lint exige al menos una entrada y que
  coincidan (`.github/scripts/probar_versiones_estables.py:27-37`): se dejan hasta tener la primera versión estable
  propia y entonces se **reemplazan** ([VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md)). No uses ese botón antes.

## 5. Recursos en Cloudflare

| Recurso | Nombre (puede ser el mismo) | ¿Lo crea `wrangler deploy`? | Cómo |
|---|---|---|---|
| Plan Workers Paid | — | No | *Workers & Pages › Plans* ([OPERACION.md › Preparación](OPERACION.md)) |
| Subdominio `workers.dev` de la cuenta | `<subdominio>` | No | *Workers & Pages*: lo elige la cuenta. Cada Worker responde en `https://<worker>.<subdominio>.workers.dev` |
| Bucket R2 de producción y de staging | `dcasa-respaldos`, `dcasa-respaldos-staging` (`edge/wrangler.jsonc:68,153`) | **No** | *R2 › Create bucket*, ubicación **ENAM**, sin acceso público, sin reglas de ciclo de vida sobre `adjuntos/`, `pgbackrest/` ni `fuentes/` |
| Token de R2 por bucket | — | No | *R2 › Manage API tokens › Create Account API token*, **Object Read & Write** solo sobre ese bucket. Da `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY` |
| Token de API para GitHub | — | No | Permisos abajo |
| Workers `dcasa`, `dcasa-staging`, `dcasa-juan`, `dcasa-juan-staging` (y del puente, si se usa) | ídem | **Sí** | Con sus flujos (§6) |
| Durable Objects y apps de contenedores | `OdooContainer`, `Conversacion`, `Global`, `PuenteWa` | **Sí** | Migración `v1` de cada `wrangler.jsonc` |
| KV de la caché | `dcasa-tienda`, `dcasa-staging-tienda` | **Sí** (sin `id`: aprovisionamiento automático, `edge/wrangler.jsonc:38-42`) | — |
| Imagen de Odoo en el registro | `dcasa-odoo:<SHA>` | La sube `desplegar.yml` (`wrangler containers push`, `:169-211`) | — |
| Aplicación de Access (puerta del equipo) | una por entorno | No | §6.9 |
| Widget de Turnstile | — | No | Opcional |
| D1 | — | — | No se usa ([ARQUITECTURA.md §2.6](ARQUITECTURA.md)) |

**Permisos del token de despliegue** (`CLOUDFLARE_API_TOKEN`), de [DESPLIEGUE.md §2](DESPLIEGUE.md) y los flujos:

- **Workers** con rol de administrador del producto (crear un Worker nuevo lo exige);
- **Containers: Edit** y **Account Settings: Read**;
- **Workers KV Storage: Edit** (la caché se crea en el primer despliegue: `edge/wrangler.jsonc:39-41`);
- **Cloudflare Images: Edit**, solo para subir la imagen del puente (`.github/workflows/desplegar-puente.yml:18-19`);
- con dominio propio, **Zone › Workers Routes › Edit** sobre esa zona
  ([CONTEXTO_AGENTICO.md › Cloudflare](CONTEXTO_AGENTICO.md)).

Los nombres exactos de los permisos cambian: si wrangler da error de autorización, el mensaje dice cuál falta. El
token puede ser de cuenta (*Manage Account › Account API Tokens*) o de usuario (*My Profile › API Tokens*, el que usa
D'CASA según [TRASLADO_DOMINIO.md](historico/TRASLADO_DOMINIO.md)). El **Account ID** (página principal de *Workers & Pages*) va
como secreto en GitHub, nunca en el repositorio.

## 6. Instalación paso a paso

### 6.1 En local, antes de cambiar nada

```bash
cd edge && npm ci && npm test && npm run typecheck && cd ..
cd juan && npm ci && npm test && npm run typecheck && cd ..
cd puente-wa && npm ci && npm test && npm run typecheck && cd ..
make setup                                 # submódulo + .venv con las dependencias de Odoo (Makefile:12-15)
PYTHON=.venv/bin/python scripts/test.sh    # todos los módulos en una base limpia (PostgreSQL odoo/odoo)
ruff check addons
```

Así sabes que el clon está sano **antes** de tocar nada. Las pruebas de Odoo tardan (unos 27 minutos en CI,
[LEEME_PRIMERO.md §4](LEEME_PRIMERO.md)): para iterar, `scripts/test.sh modulo1,modulo2`. Si `python-ldap` no compila
en una máquina nueva, la receta está en [CONTEXTO_AGENTICO.md › Esta máquina](CONTEXTO_AGENTICO.md) («Contenedor
nuevo»). Alternativa con Docker: `docker compose up --build` (`admin`/`admin`, solo en local).

### 6.2 Adaptar, en una rama y con pruebas

Haz los cambios del §4 en una rama y corre las pruebas hasta que pasen. Antes del **primer** despliegue, como mínimo:

1. **Sin dominio todavía:** `"routes": []` en la raíz de `edge/wrangler.jsonc` (hoy `:110-113` apuntan a
   `dcasapty.com`; el dominio propio solo se agrega cuando su DNS está en la cuenta: [DESPLIEGUE.md §6](DESPLIEGUE.md))
   y cambiar `edge/test/fase1.test.ts:490-499`. Deja `"workers_dev": true`.
2. **Puerta del equipo apagada en los dos entornos:** `DCASA_PUERTA_OBLIGATORIA` en `"0"` (staging hoy está en `"1"`,
   `edge/wrangler.jsonc:174`). Se enciende por pasos en el §6.9.
3. **Black Weekend** en `"0"` en los dos entornos si el negocio no tiene esa campaña (`edge/wrangler.jsonc:65,150`).
4. **El catálogo** reemplazado o vacío (§4.1) y **`puntos.json`** con las cifras del negocio o en `null`.
5. **Subdominio `workers.dev`** de la cuenta nueva en `edge/wrangler.jsonc:162`, `juan/wrangler.jsonc:80` y, si se usa
   el puente, `puente-wa/wrangler.jsonc:62,65,110,111` y `.github/workflows/desplegar-puente.yml:159`.
6. **Sitio de Juan en producción** (`juan/wrangler.jsonc:49`): la dirección donde el sitio responda de verdad
   (`https://dcasa.<subdominio>.workers.dev` hasta tener dominio).
7. Las pruebas que fijan esos valores, en el mismo commit ([VALORES_DE_LA_EMPRESA.md §P](replicar/VALORES_DE_LA_EMPRESA.md)).

### 6.3 Cloudflare y GitHub (una vez)

1. Cloudflare: plan, subdominio, buckets, tokens de R2 y token de despliegue (§5).
2. Generar las claves propias **por entorno** y guardar **antes de nada** en el gestor de contraseñas las que no se
   rotan nunca: `PGBACKREST_CIPHER_PASS` y `DCASA_PIN_PEPPER`
   ([CUENTAS_Y_SECRETOS.md §7](replicar/CUENTAS_Y_SECRETOS.md)).
3. GitHub: environments `staging` y `production` (`production` solo desde `main`) con sus secretos y variables
   ([CUENTAS_Y_SECRETOS.md §2](replicar/CUENTAS_Y_SECRETOS.md)). `URL_SITIO` = la dirección `workers.dev` de cada
   entorno; `CANONICAL_HOST` vacía.

### 6.4 Primer despliegue a staging

1. Sube la rama. *Actions › CI/CD › Run workflow* en esa rama, `desplegar_en = staging` (`.github/workflows/ci.yml:23-26`).
   Corre todas las pruebas; si pasan, despliega `dcasa-staging` (`ci.yml:526-537`) y después Juan staging
   (`ci.yml:539-548`).
2. El primer arranque, con el bucket vacío, crea la base e instala `ODOO_MODULES` en `es_419`
   (`docker/entrypoint.sh:375-376`). Staging puede tardar hasta ~27 minutos en quedar sano: no canceles antes.
3. Abre `<URL_SITIO>/__edge/health`: 200 con `version`, `base_al_dia: true` y `humo: ok`
   ([DESPLIEGUE.md › Sesiones y salud](DESPLIEGUE.md)).
4. En el resumen del job «Desplegar a staging» quedan el **`imagen_digest`** y el **`app_version`**
   (`.github/workflows/desplegar.yml:319-330`): son los que se usan para producción.
5. Si el respaldo previo se frena con un 429 de R2 o un HTTP 000, no repitas todo el CI: lanza *Actions › Desplegar*
   a staging con ese mismo digest ([CONTEXTO_AGENTICO.md › Despliegue](CONTEXTO_AGENTICO.md)).

### 6.5 Primer arranque: administrador, doble factor, usuarios y datos

1. **El administrador.** `<URL_SITIO>/web/login` con el usuario `admin` y la clave `ODOO_ADMIN_PASSWORD`. El arranque
   la pone en lugar de `admin/admin` antes de abrir el puerto, una sola vez (`docker/entrypoint.sh:652-670`); si alguien
   ya la cambió, no la toca. El CI comprueba que nunca quede `admin/admin` (`.github/workflows/ci.yml:306-313`).
2. **Doble factor.** Con `DCASA_2FA_OBLIGATORIO = "1"` y alcance `admins` (`edge/wrangler.jsonc:77-78,168-169`), el
   administrador enrola la app de códigos al entrar. Escanear el QR también en un segundo aparato (Odoo no da códigos de
   respaldo) y tener **dos** administradores con 2FA. No activar la opción de Odoo «Exigir 2FA» por correo. Guía y
   rescate: [SEGURIDAD_ACCESO.md §2-§4](SEGURIDAD_ACCESO.md).
3. **Usuarios.** Uno por persona (*Ajustes › Usuarios*), con su rol en el grupo «D'CASA»: Vendedora, Caja o Gerencia
   (`addons/dcasa_base/security/dcasa_roles.xml`), y Nómina si corresponde. Nunca se comparte el de `admin`
   ([PERMISOS.md](PERMISOS.md), [EQUIPO.md](EQUIPO.md)).
4. **Datos del negocio en Odoo:** empresa y documentos, WhatsApp del sitio, tope de descuento, tope de gasto de Brian,
   Ajustes de Juan ([CUENTAS_Y_SECRETOS.md §8](replicar/CUENTAS_Y_SECRETOS.md)).
5. **Datos de un sistema anterior:** *Ajustes › Cargar datos del sistema anterior* ([MIGRACION.md](MIGRACION.md));
   nunca por el repositorio.

### 6.6 Conectar Juan con Odoo (staging primero)

1. Genera `JUAN_ODOO_TOKEN` y `JUAN_WORKER_TOKEN` y pega **el mismo valor** en `dcasa-staging` y en
   `dcasa-juan-staging` (tipo *Secret*) ([CUENTAS_Y_SECRETOS.md §6](replicar/CUENTAS_Y_SECRETOS.md)).
2. En `dcasa-staging`, variable `JUAN_URL` = `https://dcasa-juan-staging.<subdominio>.workers.dev` (o en Odoo, *Ajustes
   de Juan › Dirección del Worker de Juan*).
3. En `dcasa-juan-staging`: `URL_PUBLICA` (su propia dirección, sin `/` final), la clave de la IA elegida y, si se
   quiere, `ALERTA_TELEGRAM_CHAT_ID`.
4. Las variables del panel llegan a Odoo al reiniciar o en el siguiente despliegue: relanza *Desplegar* a staging con
   el mismo digest.
5. Comprueba `https://dcasa-juan-staging.<subdominio>.workers.dev/salud` (sin `secretos_faltantes`) y, en Odoo,
   *Conversaciones › Conexiones* («Dirección del Worker de Juan: cargada»,
   `addons/dcasa_conversaciones/static/src/xml/conexiones.xml:95`).
6. Prueba por Telegram con el bot de Juan ([JUAN.md, Parte 2 §6](JUAN.md), y §6.13).

### 6.7 Primer despliegue a producción (la receta de este repositorio)

Con el «sí» de la gerencia del negocio y staging revisado ([LEEME_PRIMERO.md §3](LEEME_PRIMERO.md)):

1. **PR a `main`** con la plantilla `.github/pull_request_template.md` (tiene su sección de Brian) y unión por
   *squash* con el título terminado en ` [skip ci]` (las pruebas ya pasaron en la rama). No subas nada a la rama entre
   el CI y la unión: se colaría a `main` sin probar.
2. **Comprueba el árbol:** el contenido de `main` tiene que ser el mismo que se probó:
   `git fetch origin && git diff --quiet <sha probado> origin/main && echo igual`.
3. *Actions › Desplegar › Run workflow* en `main` (`.github/workflows/desplegar.yml:46-64`): `entorno = production`,
   `imagen_digest` = el `sha256:…` del resumen de staging, `app_version` = **el SHA de 40 caracteres del commit que
   construyó el CI** (el de la rama, nunca el del *squash*: su imagen no existe en el registro), `respaldo_previo =
   true`. En el primer despliegue el Worker no existe y el respaldo previo se salta solo (`:264-265`); las dos claves
   que no se rotan se suben esa vez.
4. **Espera la salud estricta** (`.github/scripts/esperar_salud.sh`: la versión desplegada, la base al día y el humo,
   con vigilancia posterior) y **abre el Inicio** del panel: «sano» no es solo un 200.
5. *Actions › Desplegar Juan*, `entorno = production`, `dry_run` desmarcado (`.github/workflows/desplegar-juan.yml:21-32`).
   Juan necesita que `dcasa` exista antes (su *service binding*).
6. Secretos y variables del panel en `dcasa` y `dcasa-juan` con los valores **de producción** (§6.6) y un despliegue o
   reinicio para que Odoo los tome.

Otra vía documentada: *CI/CD* en `main` con `desplegar_en = produccion` (`.github/workflows/ci.yml:560-572`), que repite
todas las pruebas antes. Nunca inventes ni «completes» un SHA: cópialo del run o del PR.

### 6.8 Dominio propio

Cuando el negocio tenga su dominio ([TRASLADO_DOMINIO.md](historico/TRASLADO_DOMINIO.md) es el caso real de D'CASA, paso a paso):

1. Agregar el dominio a Cloudflare **copiando antes** los registros DNS que ya existen (sobre todo el correo: MX, SPF,
   DKIM, DMARC) y cambiar los *nameservers* en el registrador. Esperar a que diga **Active**.
2. Darle al token de despliegue *Zone › Workers Routes › Edit* sobre esa zona.
3. En `edge/wrangler.jsonc`: `routes` con el dominio y `www` (`custom_domain: true`), `"workers_dev": true` (si no,
   wrangler apaga `workers.dev`, donde viven webhooks y la entrada de siempre) y `"routes": []` en `env.staging` (si no,
   staging hereda el dominio). Cambiar `edge/test/fase1.test.ts:490-499` y `edge/test/anfitrion-canonico.test.ts:32-33`.
4. Borrar los registros A o CNAME de esos nombres **justo antes** del despliegue: el dominio propio no se crea si ya
   existen.
5. GitHub › `production` › `URL_SITIO` = `https://<dominio>`; `CANONICAL_HOST` vacía.
6. CI a staging **de ese commit** y *Desplegar* a producción con **su** `app_version`: Desplegar hace checkout de
   `app_version` y toma su `wrangler.jsonc` (con un commit viejo sale sin dominio). Ese día el respaldo previo no puede
   pasar (llama a `URL_SITIO`, que todavía no resuelve): con el «sí» de la gerencia, `respaldo_previo` desmarcado, o
   respaldar antes con la dirección vieja (Desplegar 29 y 30 en [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md)).
7. Después: *Brian › Telegram › Registrar webhook* otra vez; agregar el dominio a la aplicación de Access (el AUD no
   cambia), a Turnstile y a Resend; verificar el dominio en Meta; `URL_SITIO` de Juan al dominio y *Desplegar Juan*.
   El borde manda `www` al dominio canónico. Lo impreso (QR de Socios) va siempre al dominio, nunca a `workers.dev`.

### 6.9 La puerta del equipo (Cloudflare Access)

Paso a paso en [SEGURIDAD_ACCESO.md §8.4-§8.6](SEGURIDAD_ACCESO.md) y [PUERTA_MASTER.md](PUERTA_MASTER.md):

1. Zero Trust: elegir el nombre del equipo (plan Free) y **agregar** *One-time PIN* como proveedor de identidad (en
   cuentas nuevas no viene activado).
2. Una aplicación *Self-hosted* por entorno: hostname donde el sitio responde **hoy** y *Path* `master*`; política
   *Allow* con los correos del equipo; solo *One-time PIN*; sesión de 24 h. Copiar el *AUD Tag*.
3. Los cuatro secretos en el environment: `DCASA_PUERTA_RUTA`, `DCASA_PUERTA_SECRETO`, `DCASA_ACCESS_EQUIPO`,
   `DCASA_ACCESS_AUD`. Las cuatro juntas o la puerta queda apagada.
4. Encender **por pasos**: `DCASA_PUERTA_OBLIGATORIA = "0"` y probar `/master` (PIN → «Acceso del equipo» → clave →
   código) → `"avisar"` unos días (*Accesos al panel*, filtro «Sin pasar por la puerta») → `"1"`. **Nunca directo a
   `"1"`**: en D'CASA dejó al equipo sin entrada (incidente 4). `/__edge/health` trae el estado de la puerta.
5. Rescate: `"0"` y desplegar.

### 6.10 Respaldos y simulacro de restauración

1. En el bucket de cada entorno tienen que aparecer `pgbackrest/` y `adjuntos/`; al día siguiente, `pg_dump/` (cron
   `17 8 * * *` UTC, `edge/wrangler.jsonc:48`).
2. Respaldo a mano, con el token en una variable de **tu** terminal (nunca escrito en un chat):
   `curl -fsS -X POST -H "Authorization: Bearer $RESPALDO_TOKEN" "$URL_SITIO/__edge/respaldo"`.
3. Cada corrida del CI hace un simulacro con almacenamiento local (job `simulacro-restauracion`,
   `scripts/simulacro_restauracion.sh`). Una vez al mes, el simulacro **con R2 de verdad** en staging
   ([OPERACION.md › Simulacro mensual de restauración](OPERACION.md)).
4. Barandas de costo: alertas de presupuesto y reglas de ciclo de vida de R2, nunca sobre `pgbackrest/` ni `adjuntos/`
   ([OPERACION.md › Barandas de costo](OPERACION.md)).
5. Volver atrás y restaurar a un punto en el tiempo: [OPERACION.md](OPERACION.md) («Volver atrás un despliegue»,
   «Restaurar a un punto en el tiempo»).

### 6.11 WhatsApp con la API oficial de Meta (Juan)

Así atiende D'CASA desde el 2026-11-02 ([LEEME_PRIMERO.md, bitácora de esa fecha](LEEME_PRIMERO.md)); el plan completo
está en [JUAN_CANALES.md §1](JUAN_CANALES.md). Los pasos marcados ⚠ ahí se confirman en la pantalla de Meta.

1. Portafolio de **Meta Business** de la empresa nueva y **verificación del negocio** (tarda días: empezar pronto).
2. App de Meta de tipo empresa con el producto **WhatsApp**.
3. Decidir el número: uno nuevo (recomendado para empezar) o el de hoy (modo de coexistencia ⚠).
4. Un **usuario del sistema** con llave **permanente** y permisos `whatsapp_business_messaging` y
   `whatsapp_business_management`. La llave del Explorador de la API Graph vence en horas: nunca se deja puesta.
5. En `dcasa-juan-staging` primero: secretos `WHATSAPP_CLOUD_TOKEN`, `META_APP_SECRET`, `META_VERIFY_TOKEN` y variable
   `WHATSAPP_PHONE_NUMBER_ID` ([CUENTAS_Y_SECRETOS.md §4.2](replicar/CUENTAS_Y_SECRETOS.md)).
6. Webhook en Meta: `https://dcasa-juan.<subdominio>.workers.dev/webhooks/whatsapp-cloud` con el mismo token de
   verificación; suscribirse a los mensajes **solo en la tarjeta del número real** (no en la del número de prueba).
7. `/salud` de Juan: `whatsapp_cloud` con `configurado: true`. En Odoo, *Ajustes de Juan*: encender **WhatsApp (API
   oficial)** (viene apagado: `juan/src/config.ts:111-117`).
8. Probar texto, foto, PDF y nota de voz.
9. Límites: fuera de las 24 horas del último mensaje del cliente solo se puede escribir con plantillas aprobadas por
   Meta, y el envío de plantillas **todavía no está hecho** ([JUAN_CANALES.md §1](JUAN_CANALES.md)).

### 6.12 Messenger e Instagram (preparados)

Código listo (`juan/src/canales/meta.ts`); falta lo que se hace en Meta, Cloudflare y Odoo:
[JUAN_CANALES.md §3](JUAN_CANALES.md) (app, `META_PAGE_TOKEN`, webhook `/webhooks/meta`, encender en Ajustes de Juan y pedir la
revisión de la app para contestar a todos).

### 6.13 Telegram: el bot de Brian y el de Juan

- **Brian** ([BRIAN.md › Telegram](BRIAN.md)): bot nuevo en @BotFather; `TELEGRAM_BOT_TOKEN` y
  `BRIAN_TELEGRAM_SECRETO` (en GitHub o en el panel de `dcasa`, no en los dos); `BRIAN_TELEGRAM_CHATS` en el panel
  (sin ella cualquiera recibe las instrucciones para vincularse); desplegar o reiniciar; *Brian › Telegram ›
  Registrar webhook*; cada persona se vincula con `/vincular <código>`. `DCASA_ALERTA_TELEGRAM_CHAT` para el aviso de
  caída del contenedor. Sofía manda su resumen de la mañana a quien tenga Telegram vinculado.
- **Juan** ([JUAN.md, Parte 2 §6](JUAN.md)): **otro** bot (un bot tiene un solo destino);
  `TELEGRAM_BOT_TOKEN_JUAN` y `TELEGRAM_WEBHOOK_SECRET_JUAN` en `dcasa-juan`; registrar el webhook con `setWebhook`
  hacia `/webhooks/telegram`; `/miid` da el chat id para las alertas.

### 6.14 Opcionales

- **Correo a clientes (Resend):** cuenta, una clave por entorno, dominio verificado y el interruptor «Enviar correos a
  clientes» ([CORREO.md](CORREO.md)).
- **Meta, píxel y catálogo:** todo apagado hasta tener la sección de privacidad aprobada ([META_EVENTOS.md](META_EVENTOS.md),
  [META_CATALOGO.md](META_CATALOGO.md)).
- **Turnstile:** `TURNSTILE_SITE_KEY` y `TURNSTILE_SECRET` ([SEGURIDAD_ACCESO.md §6.2](SEGURIDAD_ACCESO.md)).
- **Caché de páginas:** `TIENDA_FEED_TOKEN` y `TIENDA_ESTATICA` (`off` en producción hasta aprobarla en staging,
  `edge/wrangler.jsonc:71-73`; [OPERACION.md › Tienda rápida](OPERACION.md)).
- **Puente de WhatsApp por QR:** *Actions › Desplegar puente de WhatsApp*, primero `dry-run` y luego `desplegar`, después
  de Juan; `WA_TOKEN` y `WA_SESION_CLAVE` en el panel; descomentar `PUENTE` en `juan/wrangler.jsonc:33` (staging `:75`) y
  volver a desplegar Juan. Solo con un número **de prueba** en staging ([JUAN_PUENTE.md](JUAN_PUENTE.md)). Con la API
  oficial no hace falta.

## 7. Adaptar sin bifurcar la lógica

**Se cambia (datos y configuración):** lo de [VALORES_DE_LA_EMPRESA.md](replicar/VALORES_DE_LA_EMPRESA.md), las
variables de los `wrangler.jsonc`, los secretos, `puntos.json` (subiendo su `version`), las plantillas de Sofía y de
correo, el conocimiento de Juan y todo lo que se edita en Odoo
([CUENTAS_Y_SECRETOS.md §8](replicar/CUENTAS_Y_SECRETOS.md)).

**No se toca:**

- `vendor/odoo` (nunca);
- las invariantes de Socios y vendedores (sin columna de saldo, libros que no se editan, un solo patrocinador, nada se
  paga por afiliar, la comisión nunca hace fallar una venta, `DCASA_PIN_PEPPER` que no se rota: `CLAUDE.md`);
- el arranque y el despliegue (`docker/entrypoint.sh`, `docker/pg.sh`, `.github/scripts/`, `edge/src/`), salvo para
  corregir un error, y leyendo antes [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md);
- los nombres técnicos (`dcasa_*`, modelos, campos, parámetros): cambiarlos rompe la vía de mejoras del original.

**Comportamiento nuevo, en un módulo nuevo** que herede (como manda `CLAUDE.md`), con su prueba. Un módulo nuevo se
agrega a `ODOO_MODULES` (`docker/entrypoint.sh:176`) y a `MODULES` del `Makefile:5`, que es como entró `dcasa_sofia`
([LEEME_PRIMERO.md](LEEME_PRIMERO.md), bitácora del 2026-11-05). Cuantos menos archivos del núcleo cambie el negocio
nuevo (idealmente solo los de VALORES), más fácil es traer mejoras.

## 8. Traer mejoras del original y reglas del repositorio

```bash
git fetch upstream
git switch -c traer-mejoras origin/main
git merge upstream/main          # los conflictos caen casi siempre en los archivos de VALORES_DE_LA_EMPRESA.md
```

1. Resuelve los conflictos conservando los datos del negocio nuevo y el código nuevo del original. Lo que traiga datos
   de D'CASA (`puntos.json`, catálogo, textos, versiones estables) **no se acepta**.
2. Si el original subió la `version` de un módulo o trae `migrations/`, léelo antes: al desplegar, el arranque corre
   `odoo -u` sobre la base del negocio (`docker/entrypoint.sh:398-401`).
3. Si cambió el commit de `vendor/odoo`: `git submodule update --init --depth 1`.
4. Todas las pruebas en local, staging, revisión y recién después producción con la receta del §6.7.
5. **Nunca** despliegues una imagen más vieja sobre una base ya actualizada sin restaurar antes la base: con `-u`, el
   código viejo borra columnas y tablas nuevas con sus datos ([CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md), regla 2).

**Reglas que el equipo nuevo hereda** (de [`CLAUDE.md`](../CLAUDE.md) y [LEEME_PRIMERO.md](LEEME_PRIMERO.md)):

- Al empezar una sesión, leer `docs/LEEME_PRIMERO.md` y `docs/PRIORIDADES.md`; antes de desplegar o tocar el
  arranque, el borde o los flujos, `docs/CONTEXTO_AGENTICO.md`. Al terminar, la entrada de la bitácora, las
  prioridades al día y lo aprendido en el contexto agéntico.
- Convenciones de Odoo 19 (`<list>`, `invisible="expr"`, `models.Constraint`, `group_ids`, `self.env._`) y pruebas
  `@tagged('post_install', '-at_install')`: **todo cambio lleva prueba**.
- Todo método público nuevo, y todo *override* de uno de Odoo, va a la lista blanca de
  `addons/dcasa_base/tests/test_superficie_rpc.py` con su motivo.
- Toda prueba con fechas congela el reloj; toda prueba que provoca un `ERROR` lo atrapa con `assertLogs`
  (`scripts/test.sh` falla con cualquier `ERROR` del registro: `scripts/test.sh:41-45`).
- Toda pantalla nueva que un administrador deba encontrar va a `addons/dcasa_guia/data/guia.json`.
- Toda función nueva tiene que poder usarla Brian (la plantilla del PR lo pregunta).
- Adjuntos en R2; nunca se borran objetos de R2 al desvincular.
- Secretos nunca en el chat; datos de personas solo en Odoo; el «sí» de la gerencia antes de producción (la tabla de
  autorizaciones de [LEEME_PRIMERO.md §2](LEEME_PRIMERO.md), adaptada al negocio nuevo).

## 9. Antes de abrir al público

- [ ] `GET /__edge/health` en los dos entornos: 200, `version` = el commit desplegado, `base_al_dia: true`, `humo: ok`.
- [ ] Ningún dato de D'CASA a la vista: las búsquedas de [VALORES_DE_LA_EMPRESA.md](replicar/VALORES_DE_LA_EMPRESA.md)
      solo encuentran comentarios, migraciones viejas o ejemplos de formato.
- [ ] Recorrido a mano en computadora y celular: portada, `/shop`, una ficha, carrito, `/socios`, `/mi-cuenta`,
      `/privacidad`, `/terminos`, `/visitanos`; en el panel: Inicio, Conversaciones, una cotización e «Imprimir
      documentos» (PDF con la marca nueva).
- [ ] Como Vendedora y como Gerencia: la vendedora no ve costos, ganancia, Nómina ni facturas de proveedor
      ([PERMISOS.md](PERMISOS.md)).
- [ ] Políticas (privacidad con el párrafo de IA real, términos, garantía, cambios, abonos, Socios, vendedores)
      aprobadas por la asesoría legal del negocio; cifras de `puntos.json`, premios, bono y tasas de nómina decididas
      por la gerencia y quien lleve la contabilidad. Nada inventado.
- [ ] Catálogo propio cargado (o vacío a propósito); ningún producto ni foto de D'CASA.
- [ ] Juan: `/salud` sin secretos faltantes, `URL_PUBLICA` puesta, una conversación de prueba por cada canal encendido;
      su proveedor de IA y su tope del mes decididos.
- [ ] Brian: contesta en el panel; su tope de gasto puesto; Telegram con lista de chats permitidos.
- [ ] Doble factor enrolado por **dos** administradores; usuarios uno por persona; `admin` no se comparte.
- [ ] Puerta del equipo probada en `"0"`, luego `"avisar"`; en `"1"` solo cuando nadie aparece «sin pasar por la puerta».
- [ ] Respaldos: `pgbackrest/`, `adjuntos/` y, al día siguiente, `pg_dump/` en el bucket; simulacro con R2 de verdad
      hecho en staging.
- [ ] Barandas de costo: alertas de presupuesto y reglas de ciclo de vida de R2.
- [ ] Copia de `PGBACKREST_CIPHER_PASS` y `DCASA_PIN_PEPPER` de cada entorno (y `WA_SESION_CLAVE` si hay puente) en el
      gestor de contraseñas de la gerencia. Cloudflare y GitHub con 2FA y códigos de recuperación impresos.
- [ ] Dominio propio activo (si lo hay), `URL_SITIO` al dominio, webhook de Brian registrado de nuevo, QR impresos al
      dominio.
- [ ] Primera versión estable propia en `.github/versiones_estables.json` y en `volver-a-estable.yml` (§4.3).
- [ ] `CLAUDE.md` y los documentos de historia reescritos para el negocio nuevo (§4.3).

## 10. Trampas conocidas que pegan en una instalación nueva

Sacadas de [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md), donde está cada una con su causa y su arreglo.

1. **`routes` con un dominio que no es de la cuenta.** `edge/wrangler.jsonc` trae el dominio de D'CASA: hasta tener el
   propio en Cloudflare, `"routes": []` (§6.2). Y `routes` **se hereda** en `env.staging`: siempre `"routes": []` ahí.
2. **`app_version` es el SHA que construyó el CI** (el de la rama), nunca el del *squash* en `main`: con otro, falla con
   `IMAGE_REGISTRY_DOESNT_CONTAIN_IMAGE` y el Worker nuevo igual queda activo (Cloudflare activa el Worker antes que la
   imagen). Nunca inventar ni completar un SHA.
3. **«Sano» no es un 200.** Vale la versión desplegada con la base al día y el humo en verde; después de cada despliegue
   se abre el Inicio (incidente 1, #97).
4. **El código y la base van juntos.** Nunca bajar una imagen sin restaurar antes la base (regla 2).
5. **`CANONICAL_HOST` tiene que ser donde el sitio responde de verdad.** Dejar vacía la de GitHub: se toma el anfitrión
   de `URL_SITIO` (`.github/workflows/desplegar.yml:286-296`). Si apunta a un dominio sin ruta, las fotos y PDF de
   Telegram y WhatsApp no llegan.
6. **Puerta del equipo:** nunca directo a `"1"` (incidente 4). Staging viene en `"1"`: bajarla a `"0"` (§6.2).
7. **El día del dominio:** el respaldo previo falla porque `URL_SITIO` todavía no resuelve (Desplegar 29), y desplegar
   con el `app_version` de un commit sin `routes` sale sin dominio (Desplegar 30). El dominio propio no se crea si el
   nombre ya tiene un registro A o CNAME.
8. **Las variables del panel se aplican al reiniciar** o en el siguiente despliegue; los despliegues usan `--keep-vars`
   para no borrarlas.
9. **`DCASA_PIN_PEPPER` y `PGBACKREST_CIPHER_PASS` no se rotan nunca**; si la consulta de secretos falla, el despliegue
   aborta sin escribir nada. Guardar la copia **antes** del primer despliegue.
10. **Worker a Worker, solo por *service binding*** (la URL pública da el error 1042) y en orden: `dcasa` → `dcasa-juan`
    → `dcasa-puente-wa`. Cloudflare no despliega un binding a un Worker que no existe.
11. **Juan sin `URL_PUBLICA`** guarda los archivos del cliente pero Odoo no puede bajarlos («No se pudo traer 1 archivo»).
12. **La espera de la salud tiene que despertar a Odoo:** la portada sale de la copia del borde; por eso
    `esperar_salud.sh` visita `/web/login`. Staging puede tardar ~27 minutos: no cancelar.
13. **429 de R2 o HTTP 000 en el respaldo previo:** no toca producción; relanzar *Desplegar* con el mismo digest. Un 503
    de producción apagada: esperar el minuto 7 de la hora (el cron la despierta) y relanzar.
14. **Cuota de artefactos de GitHub llena** («Artifact storage quota has been hit»): *Limpiar copias temporales* y
    esperar 6-12 horas ([OPERACION.md](OPERACION.md)).
15. **La app de contenedores apareció «revertida» a la imagen anterior** en 5 despliegues (incidente 5, causa sin
    confirmar): después de desplegar, mirar también la etiqueta de la imagen activa.
16. **No activar «Exigir 2FA» por correo en Odoo:** sin correo saliente, nadie recibe el código y todos quedan fuera
    ([SEGURIDAD_ACCESO.md §3](SEGURIDAD_ACCESO.md)).
17. **Capturas de referencia visual:** si cambia la marca, se regeneran a propósito y en el mismo commit; Chromium y las
    fuentes de cada máquina pintan distinto (el CI tolera 6 %, en local 1,5 %).
18. **WhatsApp:** la llave del Explorador de la API Graph vence en horas; suscribirse a los webhooks solo en el número
    real. Un modelo «contributor» de Meta entrena con las conversaciones: la política de privacidad lo tiene que decir.
19. **Un módulo que agrega una exigencia** (motivo, grupo, candado) rompe a los demás que escriben ese modelo: buscarlos
    antes de unir (CI #211).

## 11. Lo que no se copia nunca

- **Datos de clientes y del equipo** de D'CASA (ni de ningún otro negocio).
- **La base de datos ni los buckets de R2** de otro negocio: cada negocio arranca con su base vacía y sus buckets.
- **Secretos:** ningún token, clave, pimienta ni clave de cifrado se reusa entre negocios ni entre entornos.
- **Las cifras de `puntos.json`, los premios, la meta del bono, el catálogo y las fotos** (`fuentes/`, `up media/`,
  `addons/dcasa_catalogo/static/img/productos/`) y las versiones estables de D'CASA.
- **Los informes y la bitácora** de D'CASA en `docs/` (historia, no instrucciones para el negocio nuevo).

## 12. Lo que no se pudo verificar (preguntas abiertas)

- **Instalar con el catálogo vacío o con otro catálogo** no se ha probado (`addons/dcasa_catalogo/__init__.py:6-23`):
  comprobarlo con `scripts/test.sh` en la primera réplica.
- **El permiso del token de Cloudflare para el binding de Workers AI** al desplegar Juan (`juan/wrangler.jsonc:24`) no
  está documentado en el repositorio.
- **Qué pasa exactamente si `routes` nombra una zona que no está en la cuenta**: por eso el §6.2 manda dejarla vacía.
- **Si `/web/signup` (crear cuenta de cliente) está abierto:** ningún ajuste del código lo fija.
- **El origen de las fotos del sitio** que no son del tema Loftspace ([REDISENO.md › Fotografía](historico/REDISENO.md)).
- **WhatsApp en coexistencia** (la app del teléfono y la API a la vez) y la forma del aviso de «eco»: sin verificar contra
  Meta ([JUAN_CANALES.md §1](JUAN_CANALES.md)).
- **Regla general:** si un documento no coincide con el código, manda el código (y se corrige el documento).

## 13. Mantener esta guía al día

Cuando cambie algo de lo que cita esta guía (un archivo se mueve, un secreto nuevo, un paso nuevo del despliegue), se
corrige aquí en el mismo cambio. Para comprobar que todas las rutas citadas existen:

```bash
python3 - <<'PY'
import pathlib, re
raiz = pathlib.Path('.')
faltan = set()
for doc in ['docs/REPLICAR.md', *map(str, raiz.glob('docs/replicar/*.md'))]:
    base = pathlib.Path(doc).parent
    texto = pathlib.Path(doc).read_text(encoding='utf-8')
    for ruta in re.findall(r'`((?:addons|edge|juan|puente-wa|docker|scripts|\.github|docs|vendor)/[^`:\s<>]+)', texto):
        ruta = ruta.rstrip('/')
        if not (list(raiz.glob(ruta)) if '*' in ruta else (raiz / ruta).exists()):
            faltan.add(ruta)
    for enlace in re.findall(r'\]\(([^)#]+\.md)', texto):
        if not (base / enlace).exists():
            faltan.add(enlace)
print('\n'.join(sorted(faltan)) or 'Todas las rutas existen.')
PY
```

Y para los secretos: comparar la tabla de [CUENTAS_Y_SECRETOS.md §2.2](replicar/CUENTAS_Y_SECRETOS.md) con
`rg -o "(secrets|vars)\.[A-Z_0-9]+" .github/workflows | sort -u`.
