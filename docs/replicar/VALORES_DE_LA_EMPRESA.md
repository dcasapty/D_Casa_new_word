# Valores propios de D'CASA y dónde viven

Parte de [Cómo instalar este sistema para otra empresa](../REPLICAR.md) (§4). Aquí está **cada dato de D'CASA** que el
código, los datos de arranque o la configuración traen escrito, con su archivo y su línea, y qué poner en su lugar.
Verificado contra el código el **2026-11-06** (commit base `700c34a`). Si una línea se movió, manda el código: busca
el texto con `rg` y corrige esta tabla.

> **Regla de oro:** aquí no se inventa nada. Lo que el negocio nuevo todavía no decidió (una cifra, un plazo, una
> política) se deja vacío, en `null` o en `PENDIENTE`, y se le pregunta a la gerencia del negocio. Nunca se copian las cifras de D'CASA.

## Cómo encontrarlo todo (antes de dar el trabajo por hecho)

```bash
rg -n "D'CASA|D&apos;CASA|dcasapty|La Chorrera|Libertadores|Panamá Oeste" \
   --glob '!vendor/**' --glob '!fuentes/**' --glob '!up media/**' --glob '!docs/**'
rg -n --hidden "dcasapty|workers\.dev" .github
rg -n -i "1340B1|FED00F|0E2A6B|Anton|Oswald" addons edge --glob '!**/tests/**'
```

Y una búsqueda por cada dato de la sección «Datos reales de la empresa» de [`CLAUDE.md`](../../CLAUDE.md) (RUC,
teléfono, correo): `rg -n -F '<dato>'`. Muchas apariciones son el nombre en manifiestos, comentarios o ejemplos de
formato de celular (el número de la tienda sirve de ejemplo de número panameño en docstrings y pruebas; ahí no hace
falta cambiarlo).
Lo que **se ve** o **cambia el comportamiento** está en las tablas de abajo.

No hace falta tocar las migraciones viejas (`addons/*/migrations/`): solo corren al actualizar una base que ya tenía
una versión anterior del módulo, nunca en una instalación nueva.

## A. Datos de la empresa (nombre, RUC, dirección, teléfono, correo)

| Qué | Dónde (archivo:línea) | Qué poner |
|---|---|---|
| Nombre, calle, ciudad, país, RUC y DV, teléfono, correo, sitio, logo, colores y lema de los documentos | `addons/dcasa_base/data/res_company_data.xml:7-22` | Los del negocio nuevo. Es `noupdate`: en una base **ya instalada** se cambia en *Ajustes › Empresas*, no aquí |
| Nombre del sitio, WhatsApp inicial, logo, favicon, Instagram y TikTok | `addons/website_dcasa/data/website_data.xml:5-11` | Los del negocio (también `noupdate`: luego, *Sitio web › Configuración › Ajustes*) |
| Coordenadas de la tienda (página «Visítanos» y datos estructurados) | `addons/website_dcasa/models/website.py:27-28` | Las de su local |
| Mapa incrustado de Google | `addons/website_dcasa/views/homepage_templates.xml:199` | El `iframe` de su ficha de Google Maps |
| Mensaje inicial de WhatsApp y el de cada producto | `addons/website_dcasa/models/website.py:30` y `:185` | «Hola <negocio>, …» |
| Título y descripción de la portada para Google | `addons/website_dcasa/models/website.py:38-43` (y los valores viejos que se pueden pisar, `:46-58`) | Los suyos, sin promesas que no haga |
| Textos viejos que el módulo corrige solo (financiamiento, entregas) | `addons/website_dcasa/models/website.py:63-97` | Vaciar las listas si no aplican al negocio nuevo |
| Región por defecto de los datos estructurados | `addons/website_dcasa/models/website.py:403` | Su provincia |
| Menú «Catálogo · Socios D'CASA · Visítanos» | `addons/website_dcasa/models/website.py:110-114` | El nombre de su programa de puntos |
| «Retiro en tienda (…)» | `addons/website_dcasa/models/tienda.py:32` | Su ciudad |
| Nombre del almacén al instalar | `addons/dcasa_base/__init__.py:213-214` | El suyo |
| Cuenta analítica «Tienda física (…)» | `addons/dcasa_contabilidad/data/analitica_data.xml:9` | La suya |
| Provincia fija en la dirección que da Juan | `addons/dcasa_conversaciones/models/tienda.py:27` | La suya (o quitarla) |
| Nombre y lema en la pantalla de entrada del panel | `addons/dcasa_interfaz/views/login_templates.xml:6` | Los suyos |
| Logo de la barra lateral del panel | `addons/dcasa_interfaz/static/src/xml/barra_lateral.xml:20` | Usa `dcasa_base/static/img/logo.png` (ver §B) |
| Dominio de los términos de vendedores (texto en el panel) | `addons/dcasa_socios/views/vendedores_views.xml:467` | Su dominio |
| Correo para retirar el consentimiento de Meta | `addons/dcasa_meta_eventos/models/res_partner.py:106` | Su correo |
| Ejemplos de correo (`…@dcasapty.com`) en ayudas y marcadores | `addons/dcasa_brian/models/herramientas_usuarios.py:39,141,146`, `addons/dcasa_seguridad/views/templates.xml:53`, `addons/dcasa_correo/models/res_config_settings.py:64`, `addons/dcasa_correo/views/res_config_settings_views.xml:48,52`, `addons/website_dcasa/views/res_config_settings_views.xml:11` | Ejemplos con su dominio |
| Autor y sitio de cada módulo | cada `addons/*/__manifest__.py` (`author`, `website`) | Opcional: no lo ve el cliente |
| Proyecto, reglas de marca y datos de la empresa para quien programa | [`CLAUDE.md`](../../CLAUDE.md) (secciones «Proyecto», «Reglas de marca», «Datos reales de la empresa») | Reescribirlas con las del negocio nuevo (ver [REPLICAR.md §8](../REPLICAR.md)) |

## B. Marca: colores, tipografías, logos e íconos

| Qué | Dónde | Qué hacer |
|---|---|---|
| Paleta del sitio (azul, amarillo, hueso, blanco, navy) | `addons/website_dcasa/static/src/scss/primary_variables.scss:11-22` | Sus colores (`o-color-1` a `o-color-5`) |
| Tipografías del sitio (Anton, Oswald, Inter) | `addons/website_dcasa/static/src/scss/primary_variables.scss:26-48`; archivos en `addons/website_dcasa/static/src/fonts` | Las suyas, **autoalojadas** (sin Google Fonts) |
| Colores del panel de Odoo | `addons/dcasa_base/static/src/scss/primary_variables.scss:4-22` y `addons/dcasa_interfaz/static/src/scss/tokens.scss` (escala `--dc-azul-*`, `--dc-amarillo`) | Su escala |
| Colores de la empresa (documentos) | `addons/dcasa_base/data/res_company_data.xml:18-21` | Primario y secundario |
| Colores sueltos en otros SCSS, reportes y SVG | `rg -l -i "1340B1|FED00F" addons edge` (unos 70 archivos: factura, abonos, contabilidad, correo, Brian, Conversaciones, Socios, Mi cuenta, Escáner, Sofía, íconos) | Reemplazar en el mismo commit |
| Fuentes del panel y de los PDF | `addons/dcasa_base/static/src/fonts`, `addons/dcasa_interfaz/static/src/fonts`, `addons/dcasa_invoice/static/src/fonts` | Las suyas |
| Prueba que exige la fuente de marca en el PDF | `.github/workflows/ci.yml:364` (busca `Anton` en la cotización) | Cambiar el nombre de la fuente si cambia |
| Logo de fábrica (empresa, sitio, correos, barra lateral) | `addons/dcasa_base/static/img/logo.png` (lo leen `res_company_data.xml:17`, `website_data.xml:7`, `website.py:18`, `dcasa_correo/models/correo.py:204`) | Reemplazar el archivo |
| Íconos de pantalla de inicio y favicon (panel y sitio) | `addons/dcasa_base/static/img/icono/` (`logo-192.png`, `logo-512.png`, `logo-maskable-*.png`, `apple-touch-icon.png`) y `addons/website_dcasa/static/src/img/favicon.png`; los usan `addons/dcasa_interfaz/views/layout_templates.xml:10,20`, `addons/dcasa_interfaz/controllers/webmanifest.py:13-19` y `addons/website_dcasa/views/layout_templates.xml:64-66` | **No a mano:** cambiar `logo.png` y correr `python scripts/iconos_de_la_marca.py`, que los regenera todos |
| Logo de la cabecera del sitio | `addons/website_dcasa/static/src/img/logo-200.webp` y `logo-400.webp` (`addons/website_dcasa/views/layout_templates.xml:158-159`) | Versiones de 200 y 400 px del logo nuevo |
| Íconos de las apps del panel | `addons/dcasa_interfaz/static/src/img/iconos/*.svg` y `addons/*/static/description/icon.svg` | Con sus colores |
| Fotos de portada, categorías e inspiración | `addons/website_dcasa/static/src/img/` (`hero*`, `cat-*`, `insp-*`, `split-*`, `black_weekend/`); las de categorías salen de `CATEGORIAS_PORTADA` en `addons/website_dcasa/models/website.py:100-107` | Son del tema *Loftspace* de Odoo (LGPL-3) según [REDISENO.md › Fotografía](../historico/REDISENO.md); confirmar el origen de cada una antes de reusarla y poner las del negocio cuando las tenga |
| Página «estamos abriendo» del borde (título, colores, enlace `wa.me`) | `edge/src/arranque.ts:25,41-49,56` | Nombre, colores y su número en formato internacional sin `+` |
| Título de la pantalla de la puerta del equipo | `edge/src/puerta_aviso.ts:168` | Su nombre |
| Texto de las alertas de caída del contenedor | `edge/src/handler.ts:692,698` | Su nombre (opcional) |
| Capturas de referencia del contrato visual | `addons/website_dcasa/tests/referencia/*.webp` y `addons/dcasa_conversaciones/tests/referencia/panel-*.webp` | Si cambia la cabecera, el hero o la pantalla de Conversaciones, regenerarlas **a propósito** con `scripts/actualizar_referencias_visuales.sh` y `scripts/actualizar_referencias_visuales_juan.sh`, en el mismo commit (trampa en [REPLICAR.md §10](../REPLICAR.md)) |

Las reglas de marca de D'CASA (el amarillo nunca toca el blanco, sistema plano, CTA único) están en `CLAUDE.md` y las
vigilan pruebas de diseño (por ejemplo `addons/website_dcasa/tests/test_diseno.py`). Si el negocio nuevo tiene otras
reglas, se reescriben en `CLAUDE.md` y se ajustan esas pruebas en el mismo commit.

## C. Textos del sitio, políticas y documentos

El sitio **se edita por código**, no con el constructor visual de Odoo ([OPERACION.md › El sitio se edita por
código](../OPERACION.md)).

| Qué | Dónde | Qué hacer |
|---|---|---|
| Barra de anuncios (entregas, tienda) | `addons/website_dcasa/views/layout_templates.xml:26-27` | Sus zonas reales |
| Descripción de la tienda en línea y beneficios del catálogo | `addons/website_dcasa/views/layout_templates.xml:103,126-128` | Los suyos |
| Pie: lema, RUC, dirección, correo, Instagram, TikTok | `addons/website_dcasa/views/layout_templates.xml:290-316` | Los suyos |
| Portada: «Visítanos», hero con el lema, beneficios, Instagram, preguntas frecuentes | `addons/website_dcasa/views/homepage_templates.xml:134-135,225-226,247,255,324,356,372` | Sus textos (sin promesas de entrega, pago o garantía que no haga) |
| Página «Visítanos» (dirección, teléfono, correo, Instagram, mapa) | `addons/website_dcasa/views/homepage_templates.xml:149,161-200` | Los suyos |
| Dirección y correo en otras páginas | `addons/website_dcasa/views/paginas_templates.xml:50-53` | Los suyos |
| Política de privacidad: quiénes somos, **inteligencia artificial** (Juan, el modelo de Meta que entrena con los datos, Anthropic), derechos y correo | `addons/website_dcasa/views/legal_templates.xml:36-110` (quiénes somos `:39-40`, IA `:62-85`, correo `:99`) | **Con su asesoría legal.** El párrafo de IA describe la elección de D'CASA (Ley 81 de 2019); si el negocio nuevo elige otro proveedor o modelo, el texto cambia |
| Términos y condiciones | `addons/website_dcasa/views/legal_templates.xml:112-` (empresa `:115-116`) | Con su asesoría legal |
| Términos de Socios | `addons/dcasa_socios/views/socios_templates.xml:430` | Con su asesoría legal y sus cifras (§F) |
| Términos de vendedores | `addons/dcasa_socios/views/vendedores_templates.xml:159` | Ídem |
| Campaña Black Weekend (página, textos y productos) | `addons/website_dcasa/views/black_weekend_templates.xml`, `addons/website_dcasa/models/black_weekend.py:224`, códigos en `addons/dcasa_catalogo/catalogo.py:281` y variables `DCASA_BLACK_WEEKEND*` de `edge/wrangler.jsonc:65-67,150-152` | Sin campaña: `"0"` en **los dos** entornos (staging hoy está en `"1"`) y cambiar `edge/test/fase1.test.ts:468-479` en el mismo commit |
| Garantía, cambios y términos que se imprimen en factura y cotización | `addons/dcasa_invoice/models/res_company.py:18-31` | Son las políticas de D'CASA con sus plazos: poner las del negocio (con su asesoría legal). Se escriben una vez, en campos vacíos; luego se editan en *Ajustes › Empresas › Documentos D'CASA* |
| Hoja «Condiciones de abono» (penalidades y recargos) | `addons/dcasa_abonos/models/condiciones.py:15-26` | Las suyas, o vaciarla; se edita también en *Ajustes* |
| Dónde vive cada política y cómo se cambia | [PERMISOS.md › Políticas del sitio](../PERMISOS.md) | — |

## D. El número de WhatsApp (CTA único)

- En Odoo: *Sitio web › Configuración › Ajustes*, campo `dcasa_whatsapp_number` (valor inicial en
  `addons/website_dcasa/data/website_data.xml:6`). Todos los botones del sitio lo usan.
- Fuera de Odoo queda fijo en la página «estamos abriendo» del borde: `edge/src/arranque.ts:56`.
- El WhatsApp que atiende **Juan** es otra cosa: el número conectado a la API de Meta
  ([CUENTAS_Y_SECRETOS.md §4.2](CUENTAS_Y_SECRETOS.md)).
- La regla «CTA único: Escríbenos por WhatsApp» es de la marca D'CASA (`CLAUDE.md`, regla 5): se conserva o se
  cambia según el negocio nuevo.

## E. Correo a clientes (Resend)

| Qué | Dónde | Qué poner |
|---|---|---|
| Remitente, nombre y dirección de respuesta de fábrica | `addons/dcasa_correo/models/correo.py:35-38` | Los suyos (también se cambian en *Ventas › Configuración › Correo a clientes*) |
| Texto de WhatsApp de los correos | `addons/dcasa_correo/models/correo.py:40` | «Hola <negocio>, …» |
| Plantillas (factura o abono, cotización, recordatorio, bienvenida, prueba) | `addons/dcasa_correo/data/mail_templates.xml` | Nombre y tono del negocio, sin cifras |
| Marco de los correos (logo, colores) | `addons/dcasa_correo/views/layout_correo.xml` | Sus colores |
| Dominio verificado en Resend y sus registros DNS | Panel de Resend y DNS en Cloudflare ([CORREO.md §5](../CORREO.md)) | Su dominio |

## F. Socios (puntos y referidos) y programa de vendedores

| Qué | Dónde | Regla |
|---|---|---|
| **Todas** las cifras de Socios y de vendedores | `addons/dcasa_socios/data/puntos.json` (secciones `acumulacion`, `bienvenida`, `referido`, `canje`, `vencimiento`, `cumpleanos` y `vendedores`) | El negocio nuevo pone **las suyas**; nunca se copian las de D'CASA. Lo no decidido queda en `null` o `PENDIENTE` y **no se rellena a ojo** (regla 1 de Socios en `CLAUDE.md`). Subir `version`. Decidir `vendedores.programaActivo`. Dejar `vendedores.canje.externosHabilitado` y `efectivoHabilitado` en `false` hasta el dictamen de la asesoría legal y de la contabilidad |
| Premios de fábrica | `addons/dcasa_socios/data/premios_data.xml` | Los suyos, o ninguno |
| Ajustes del programa de vendedores después de instalar | *Ajustes › Programa de vendedores* (versiones hacia adelante en `dcasa.vend.reglas`) | Ver [VENDEDORES.md](../VENDEDORES.md) |
| Nombre «Socios D'CASA» | menú (`addons/website_dcasa/models/website.py:112`), plantillas de Socios y de Sofía, prompt de Juan | El nombre de su programa |

Las reglas de los dos programas (sin columna de saldo, libro que no se edita, `DCASA_PIN_PEPPER` que nunca se rota,
nada se paga por afiliar…) son **invariantes del código**: se quedan. Están en `CLAUDE.md` y en
[SOCIOS.md](../SOCIOS.md) y [VENDEDORES.md](../VENDEDORES.md).

## G. Nómina, cobros y otras cifras del negocio

| Qué | Dónde | Qué hacer |
|---|---|---|
| Meta de ventas y % del bono | `addons/dcasa_nomina/data/meta_ventas_data.xml` | Los suyos, o quitar el registro |
| Tasas legales de la planilla de Panamá | `addons/dcasa_nomina/data/nomina_data.xml` (el propio archivo dice que no se verificaron contra la Gaceta Oficial) | Las valida quien lleve la contabilidad |
| Formas de cobro que se crean al instalar (Efectivo, Yappy, Tarjeta) | `addons/dcasa_base/__init__.py:12-16` | Las suyas |
| Financieras como forma de pago (Tafi, Crediviva) | `addons/dcasa_base/__init__.py:21-24` | Son de D'CASA: quitarlas de la lista o archivarlas en Odoo después de instalar |
| Tope de descuento de la Vendedora | *Ajustes de Ventas* | Lo decide la gerencia |
| Regla «todo precio termina en .99» de los pedidos del proveedor | `addons/dcasa_catalogo/reglas.py` (`precio_terminado_en_99`), usada por `scripts/importar_catalogo.py` | Solo si el negocio la quiere |

## H. Juan (el asistente de los clientes)

| Qué | Dónde | Qué hacer |
|---|---|---|
| Quién es Juan, de qué tienda y en qué ciudad | `juan/src/dcasa/prompt.ts:79-82,159,253` | Nombre del negocio, giro y ciudad. El resto del prompt (fuentes de verdad, reglas, voz) se conserva salvo que el negocio cambie la voz |
| Lo mismo para los borradores y resúmenes del panel | `juan/src/odoo-panel-sugerir.ts:107`, `juan/src/odoo-panel-resumir.ts:80` | Ídem |
| Guardia de salida: dominio de las páginas legales que Juan puede citar y el texto «asistente virtual de D'CASA» | `juan/src/dcasa/salvaguardas.ts:217,417` | Su dominio y su nombre |
| Nombre público por defecto del Worker | `juan/src/config.ts:87` | «el equipo de <negocio>» |
| Bienvenida y nombre público por defecto en Odoo | `addons/dcasa_conversaciones/models/ajustes.py:67,79` | Los suyos (luego se editan en *Conversaciones › Configuración › Ajustes de Juan*) |
| Textos fijos del sistema (tope diario, fallo técnico, archivo recibido) | `juan/src/dcasa/textos.ts` | Revisar el tono |
| Lo que Juan sabe del negocio | Odoo, *Conversaciones › Conocimiento del bot*; semilla `addons/dcasa_conversaciones/data/conocimiento_data.xml` (`noupdate`: dirección, horario y Socios se arman solos con los datos vivos; garantía y compra vienen **inactivas**) | Cargar el conocimiento del negocio nuevo en Odoo, sin inventar políticas |
| Horario, canales, proveedor y modelos de IA, tope mensual, palabras prohibidas | *Conversaciones › Configuración › Ajustes de Juan* ([JUAN.md, Parte 2 §8](../JUAN.md)) | Lo decide la gerencia. Si elige un modelo «contributor» de Meta (entrena con las conversaciones), la política de privacidad lo tiene que decir (§C) |
| Sitio público al que Juan completa los enlaces | `juan/wrangler.jsonc:49` (producción) y `:80` (staging) | La dirección donde el sitio responde **hoy** (el `workers.dev` hasta tener dominio) |
| Catálogo, precios, existencias | Siempre de Odoo por herramientas: el prompt no tiene cifras ([JUAN.md, Parte 2 §9](../JUAN.md)) | Nada que cambiar en el Worker |

## I. Sofía (la asistente del CRM)

- Mensajes que propone: `addons/dcasa_sofia/data/plantillas.xml` (`noupdate`; dicen «Soy {vendedora} de D'CASA» y
  «programa Socios D'CASA»). Cambiar el nombre del negocio antes de instalar; después los edita Gerencia en *CRM ›
  Configuración › Mensajes de Sofía*. Sin precios ni cifras ([SOFIA.md](../SOFIA.md)).
- Ajustes (revisar cada mañana, resumen por Telegram): *Conversaciones › Configuración › Ajustes de Juan*, grupo «Sofía».

## J. Brian (el asistente del panel)

- Instrucciones fijas: `addons/dcasa_brian/models/conversacion.py:800` («el asistente de D'CASA Panamá, tienda de
  muebles en La Chorrera»). Nombre, giro y ciudad del negocio nuevo.
- Proveedor, modelo y clave: variables y secretos de GitHub ([CUENTAS_Y_SECRETOS.md §2](CUENTAS_Y_SECRETOS.md)).

## K. La Guía (`dcasa_guia`)

- `addons/dcasa_guia/data/guia.json` (y `guia_roles.json`): atajos en palabras sencillas. Nombra «D'CASA» en varias
  notas (por ejemplo la pestaña «Documentos D'CASA» y el rol «D'CASA» de la ficha del usuario). Cambiar el nombre si se
  cambia en las vistas; nunca fechas ni montos de impuestos inventados (`CLAUDE.md`, «La Guía»; [GUIA.md](../GUIA.md)).
- El nombre del grupo de roles «D'CASA» (Vendedora, Caja, Gerencia) está en
  `addons/dcasa_base/security/dcasa_roles.xml:16`.

## L. Catálogo, `fuentes/` y `up media/` (no se copian)

| Qué | Dónde | Qué hacer |
|---|---|---|
| Productos que se cargan **al instalar** (`post_init_hook`) | `addons/dcasa_catalogo/__init__.py:6-23` lee `addons/dcasa_catalogo/data/catalogo.json`, `data/fichas.json`, `data/inventario_anterior.csv` y las fotos de `addons/dcasa_catalogo/static/img/productos/`, y marca los productos de Black Weekend (`addons/dcasa_catalogo/catalogo.py:281`) | **Reemplazar o vaciar** antes del primer despliegue: si no, la base nueva nace con el catálogo, los precios y las existencias de D'CASA |
| Categorías del catálogo | `addons/dcasa_catalogo/data/product_category_data.xml` y `product_public_category_data.xml` | Las suyas |
| Importador del Excel y las fotos | `scripts/importar_catalogo.py` (lee `up media/DCASA_listado_productos.xlsx`, `:58`, y los pedidos `LTSC-07`, `:142-150`) | Hecho a la medida del Excel de D'CASA: para otro formato, adaptar o cargar los productos en Odoo (importar, *Cargar datos del sistema anterior* de [MIGRACION.md](../MIGRACION.md), o el importador de Brian de [BRIAN.md](../BRIAN.md)) |
| Originales de fotos | `fuentes/` (994 MB en el árbol) | Borrar en la copia; la historia de git igual los guarda (§3 de REPLICAR) |
| Bandeja de la dueña | `up media/` (y el flujo `.github/workflows/up-media.yml`, que procesa, hace commit a `main` y despliega a staging) | Vaciar; usar el flujo solo si el negocio adopta ese proceso ([OPERACION.md › Cómo subir fotos](../OPERACION.md)) |
| Informe del inventario anterior | `docs/inventario-anterior-informe.md`, `docs/inventario-anterior-fotos-faltantes.xlsx`, `docs/CATALOGO_REVISAR.md` | Historia de D'CASA: no aplica |

## M. Dominios y el subdominio `workers.dev` de la cuenta

D'CASA usa el dominio `dcasapty.com` y su cuenta de Cloudflare tiene el subdominio `dcasapty.workers.dev`. Los dos
cambian en la cuenta nueva (el subdominio se ve en *Workers & Pages* de la cuenta).

| Qué | Dónde | Qué poner |
|---|---|---|
| Dominio canónico de producción y de staging | `edge/wrangler.jsonc:58` y `:144` | Su dominio. Ojo: con `URL_SITIO` puesta y `CANONICAL_HOST` vacía en GitHub, el despliegue usa el anfitrión de `URL_SITIO` y este valor no manda (`.github/workflows/desplegar.yml:286-296`) |
| Dominio propio del Worker | `edge/wrangler.jsonc:110-113` (`routes` con `custom_domain: true`) y `:116` (`workers_dev: true`) | **Hasta que su dominio esté en Cloudflare:** `"routes": []`. Después, su dominio y `www` (ver [REPLICAR.md §6.7](../REPLICAR.md)) |
| Rutas de staging | `edge/wrangler.jsonc:177-179` | Dejar `"routes": []` (si no, staging hereda el dominio de producción) |
| Aviso de la caché de páginas de staging | `edge/wrangler.jsonc:162` | `https://dcasa-staging.<subdominio>.workers.dev/__edge/tienda/regenerar` |
| Sitio de Juan | `juan/wrangler.jsonc:49,80` | Ver §H |
| Dirección del puente y dominios de los que baja medios | `puente-wa/wrangler.jsonc:62,65,110,111` | Su subdominio y su dominio |
| Comprobación del puente tras desplegar | `.github/workflows/desplegar-puente.yml:159` | Su subdominio |
| Dominios del puente para Odoo | `addons/dcasa_conversaciones/models/panel_calculos.py:12` | Los suyos |
| `web.base.url` de la prueba de integración de Juan | `scripts/integracion_juan_datos.py:22` | Opcional (es una base de prueba) |
| Tabla del contrato del contenedor | `edge/CONTRATO_CONTENEDOR.md:79` | Documentación |
| Variable `URL_SITIO` de cada environment de GitHub | GitHub (no está en el repositorio) | [CUENTAS_Y_SECRETOS.md §2.2](CUENTAS_Y_SECRETOS.md) |

## N. Nombres de los recursos de Cloudflare (cada `wrangler.jsonc`)

**Se pueden dejar tal cual**: los Workers, las apps de contenedores, los KV y los Durable Objects son de cada cuenta,
y los buckets de R2 también (el punto S3 lleva el ID de la cuenta: `.github/scripts/secretos_despliegue.sh:81`).
Renombrarlos obliga a cambiar los `services` que los enlazan, los flujos y las pruebas que leen los nombres
(`juan/test/despliegue.test.ts:42-47`, `edge/test/fase1.test.ts`, `puente-wa/test/despliegue.test.ts`). El nombre del
Worker sí se ve en su dirección `https://<worker>.<subdominio>.workers.dev`.

| Worker | Archivo:línea | Recursos |
|---|---|---|
| `dcasa` (producción) / `dcasa-staging` | `edge/wrangler.jsonc:3` / `:125` | Contenedor `OdooContainer` (`:12-31` y `:126-136`: `standard-1` en producción, `basic` en staging, 1 instancia, región `ENAM`, política `default` inmutable); Durable Object `ODOO` (`:33-36`); KV `TIENDA` sin `id` (lo crea wrangler: `:42`, `:141`); crons `7 * * * *` y `17 8 * * *` (`:48`, `:142`, iguales a `edge/src/handler.ts:429-430`); bucket `R2_BUCKET` = `dcasa-respaldos` / `dcasa-respaldos-staging` (`:68`, `:153`); variables `:57-96` y `:143-176` |
| `dcasa-juan` / `dcasa-juan-staging` | `juan/wrangler.jsonc:5` / `:63` | Durable Objects `CONVERSACION` y `GLOBAL` (`:13-19`, `:64-70`); Workers AI `AI` (`:24`, `:71`); service binding `DCASA` → `dcasa` / `dcasa-staging`, entrada `JuanEntrada` (`:31-34`, `:73-76`); `PUENTE` comentado (`:33`, `:75`); cron `23 * * * *` (`:37`, `:77`); variables `:47-56`, `:78-85` |
| `dcasa-puente-wa` / `dcasa-puente-wa-staging` (opcional; nunca desplegado en producción) | `puente-wa/wrangler.jsonc:9` / `:91` | Contenedor `PuenteWa` `lite` (`:18-32`, `:92-101`); Durable Object `WA` (`:33-38`); service binding `JUAN` → `dcasa-juan` / `dcasa-juan-staging` (`:43`, `:106`); cron cada minuto (`:48`, `:107`); variables `:58-78`, `:108-119`; bucket de copias comentado (`:83`) |

Otros nombres fijos: la imagen de Odoo se sube al registro como `dcasa-odoo:<SHA>` (`.github/workflows/desplegar.yml:90`)
y los flujos del puente nombran sus Workers en `.github/workflows/desplegar-puente.yml:132,158`.

**Horas de los crons:** están en UTC y pensadas para Panamá (UTC−5): `17 8 * * *` = 03:17 en Panamá
(`edge/wrangler.jsonc:44-48`). En otro huso, moverlos y cambiar a la par `CRON_HORARIO` y `CRON_RESPALDO` de
`edge/src/handler.ts:429-430` (hay prueba: `edge/test/fase1.test.ts:450-453`).

## O. Cuentas externas que llevan nombre del negocio (no están en el código)

- **Telegram:** dos bots distintos, el de Brian y el de Juan (un bot solo tiene un destino: [BRIAN.md › Telegram](../BRIAN.md)).
  Nombres y usuarios los elige el negocio en @BotFather.
- **Meta:** la app (D'CASA la llamó «D'CASA Juan»), la página de Facebook, la cuenta profesional de Instagram, el
  portafolio de negocios y el número de WhatsApp ([JUAN_CANALES.md §3](../JUAN_CANALES.md), [JUAN_CANALES.md §1](../JUAN_CANALES.md)).
- **Cloudflare Zero Trust:** el nombre del equipo (`<equipo>.cloudflareaccess.com`) y la política de correos del equipo
  ([SEGURIDAD_ACCESO.md §8.4](../SEGURIDAD_ACCESO.md)).
- **Resend:** el dominio verificado y el remitente.

## P. Pruebas que fijan datos de D'CASA (cambiarlas en el mismo commit)

Cambiar un dato sin cambiar su prueba deja el CI en rojo. Las que hay que revisar:

- `.github/workflows/ci.yml:303` (la portada debe decir el lema), `:305` (`/socios` debe decir «Tus puntos») y `:364`
  (fuente `Anton` en el PDF).
- `edge/test/anfitrion-canonico.test.ts:32-33` (`CANONICAL_HOST` de los dos entornos), `edge/test/fase1.test.ts:462-499`
  (Black Weekend, staging, `routes` con el dominio, `workers_dev`), `juan/test/despliegue.test.ts:42-47` (nombres de
  los Workers enlazados), `puente-wa/test/despliegue.test.ts:70-71,108` (dirección y dominios del puente).
- Pruebas de Odoo con datos de la empresa: `addons/dcasa_base/tests/test_dcasa_base.py` (RUC y dirección),
  `addons/website_dcasa/tests/` (`test_legal.py`, `test_diseno.py`…), `addons/dcasa_invoice/tests/` (los documentos
  aprobados de `addons/dcasa_invoice/tests/aprobado/*.html` llevan los datos de la empresa: se regeneran),
  `addons/dcasa_correo/tests/`, `addons/dcasa_contactos/tests/`, `addons/dcasa_fe_pa/tests/`. En total, unas 60
  carpetas de pruebas mencionan algún dato o ejemplo de D'CASA:
  `rg -l "dcasapty|La Chorrera|Libertadores" addons --glob '**/tests/**'`.
- Pruebas que usan el catálogo de D'CASA (si se vacía o se reemplaza): `addons/dcasa_catalogo/tests/` y la integración
  de Juan (`juan/test/integracion/historia.ts` busca productos del catálogo real).
- Las capturas de referencia visual (§B).

La manera segura: cambiar los datos, correr `scripts/test.sh` completo y `npm test` en `edge/`, `juan/` y
`puente-wa/`, y corregir cada prueba que falle **entendiendo** por qué (nunca borrarla para que pase).
