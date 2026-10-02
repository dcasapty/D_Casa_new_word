# Ronda 7 · El constructor de páginas de Odoo y el sitio de D'CASA

Fecha: 02/10/2026 · Para: la dueña · Alcance: qué es «Sitio web → Nuevo → Nueva página / Editar» en el
panel, si sirve de algo cuando el sitio se mantiene por código, qué se quitó y qué se conservó. Cambios
solo en `addons/dcasa_interfaz` (no se tocaron `website_dcasa`, `dcasa_tienda_borde` ni `edge/`).

## La pregunta

> Vi en el panel el constructor de páginas (plantillas, galería…). ¿Sirve de algo? Me preocupa que mi
> equipo edite desde ahí y «no se actualice» o choque con lo que se hace por código. Lo único que quiero
> conservar es ver el sitio en versión móvil desde el panel.

**Respuesta corta:** no sirve mientras el sitio se mantenga por código, y sí choca: cada página que se
guarde con el constructor deja de recibir los cambios del código. Se apagó por completo (nadie puede
abrirlo, ni la dueña), se dejó una guarda por si alguien consigue el permiso igual, y la vista previa
móvil se hizo aparte, propia, sin el constructor. Lo que sí se usa (publicar productos y páginas,
pedidos de la tienda, ventas en línea, configuración) se queda.

## Qué hace el constructor, en palabras simples

El sitio de D'CASA está escrito como **plantillas** dentro del módulo `website_dcasa`: la portada, la
tienda, la ficha de producto, Visítanos, Black Weekend, Socios, el pie de página… Cada despliegue trae
las plantillas nuevas y Odoo las recarga.

El constructor de Odoo deja arrastrar bloques, cambiar textos y colores y crear páginas sueltas desde el
navegador. Está pensado para quien **no** mantiene el sitio por código.

## Por qué choca con el código (verificado en Odoo 19)

Cuando alguien guarda con el constructor una página que viene de un módulo, Odoo **no toca la plantilla
del módulo**: hace una **copia de esa plantilla solo para el sitio** y, desde ese momento, el sitio dibuja
la copia. Es el mecanismo *copy-on-write* de `vendor/odoo/addons/website/models/ir_ui_view.py`:

- `write()` (línea 93): si hay un sitio en el contexto y la vista no tiene `website_id`, la copia
  (`view.copy({'website_id': …, 'key': view.key})`) y escribe el cambio **en la copia**.
- Al dibujar la página, `filter_duplicate()` y `_get_template_domain()` prefieren la copia del sitio y
  dejan de lado la plantilla genérica del módulo (misma `key`).
- En la siguiente actualización del módulo, `_load_records_write()`
  (`vendor/odoo/odoo/addons/base/models/ir_ui_view.py`, línea 2612) solo pasa a la copia los campos que
  **nadie modificó**. El contenido editado a mano ya no se actualiza nunca más desde el código.

Resultado: la página «editada en el panel» se congela con lo que tenía ese día, y los cambios por código
dejan de verse ahí sin ningún aviso. Para volver a la versión del código hay que borrar la copia a mano
(Ajustes → Técnico → Vistas). Es exactamente el «no se actualiza» que preocupaba.

**Páginas nuevas desde el constructor.** Crear una «Nueva página» no rompe las existentes: nace una página
suelta (`website.page` + su vista) que vive solo en la base de datos. Pero esa página no está en el
repositorio, no la cubren las pruebas ni el diseño de marca, no se regenera en la caché del borde por las
mismas reglas, y si un día se reconstruye la base desde el código, no existe. Es contenido fuera de control.

**Hoy, en una instalación limpia con todos los módulos**, Odoo crea por su cuenta estas copias por sitio
(ninguna del constructor): {{COPIAS}}. Son del propio Odoo (`website_sale`, el tema, la portada vacía
`website.homepage` que `website_dcasa` llena por herencia) y la guarda nueva **no las bloquea**.

## Qué carga y cuánto pesa (medido)

Medido en la base de pruebas con todos los módulos instalados (tamaño minificado / comprimido como lo
envía el servidor), `vendor/odoo/addons/website/__manifest__.py` y
`vendor/odoo/addons/website/static/src/client_actions/website_preview/website_builder_action.js`:

| Qué | Cuándo se carga | JS | CSS |
|---|---|---|---|
| Sitio público (`web.assets_frontend`) | cada visitante, siempre | {{FRONTEND_JS}} | {{FRONTEND_CSS}} |
| Panel de Odoo (`web.assets_web`) | cada usuario interno, siempre (cacheado por el navegador) | {{WEB_JS}} | {{WEB_CSS}} |
| · de eso, el editor del sitio (`website.assets_editor`: botones «Editar/Nuevo», editor HTML/CSS…) | va dentro del panel aunque nadie lo use | {{EDITOR_JS}} | {{EDITOR_CSS}} |
| Constructor (`website.website_builder_assets`, incluye `html_builder.assets`) | **al abrir «Sitio web» en el panel** (Odoo lo precarga «para que Editar sea más rápido», línea 152), y en modo edición | {{BUILDER_JS}} | {{BUILDER_CSS}} |
| Lo que el constructor inyecta en la página (`website.assets_inside_builder_iframe`) | solo en modo edición | {{IFRAME_JS}} | {{IFRAME_CSS}} |

Lo que importa de la tabla:

- **El visitante no paga nada por el constructor.** La página pública solo carga `web.assets_frontend`;
  los bundles del constructor se piden aparte y solo desde el panel. No hay nada que apagar para
  mejorar la tienda.
- **El panel sí lo pagaba**: cada vez que alguien abría «Sitio web» en Odoo (la vista previa de Odoo),
  el navegador descargaba y ejecutaba el constructor completo ({{BUILDER_JS}} de JavaScript) y pedía al
  servidor la lista de bloques (`website.snippets`), **aunque no fuera a editar**. La nueva «Vista previa
  móvil» no usa esa pantalla: es un marco con el sitio y nada más.
- La parte del editor que viaja dentro del bundle del panel ({{EDITOR_JS}}) no se puede quitar sin
  modificar los módulos de Odoo (regla del repositorio: `vendor/odoo` no se toca) y se cachea; su costo
  es una sola descarga.

**¿Se puede desinstalar algo?** No. El constructor (`html_builder`) es dependencia directa de `website`
y de `website_sale`, que son la tienda misma. Lo que se puede hacer —y se hizo— es que nadie lo pueda
abrir y que el panel no lo precargue.

## Quién podía abrirlo

Odoo muestra «Editar», «Nuevo», la vista previa móvil propia y el editor de menús a quien tiene el grupo
**Sitio web / Editor** (`website.group_website_restricted_editor`), y los temas, el editor HTML/CSS y las
páginas a **Editor y diseñador** (`website.group_website_designer`;
`website/static/src/client_actions/website_preview/website_systray_item.xml`). Odoo da el de diseñador a
`admin` y a **todo administrador** (Ajustes) al instalar, y `website_dcasa` se lo daba al rol Gerencia.
Es decir: la dueña y cualquier gerente lo tenían.

## Qué se quitó

1. **Los grupos de editor y diseñador, a todo el mundo** (incluida la dueña), de forma automática en cada
   actualización del módulo `dcasa_interfaz`: también se retira la implicación desde Ajustes
   (`base.group_system`) y desde Gerencia. Sin esos grupos, Odoo no dibuja ningún botón de edición, ni en
   el sitio ni en el panel.
2. **Los menús del constructor** en «Sitio web»: Página de inicio (vista previa de Odoo), Editor de menús,
   Esta página (propiedades, SEO, editor HTML/CSS, editar menú), Páginas técnicas; y los reportes de
   visitantes/analytics, porque la tienda se sirve desde la caché de Cloudflare a los visitantes anónimos y
   Odoo no los ve (las visitas se miran en Cloudflare). Quedan colgados del grupo «Editor y diseñador», que
   nadie tiene: si algún día se devuelve, vuelve todo junto.
3. **Guarda de seguridad** (`addons/dcasa_interfaz/models/sitio.py`): aunque alguien consiguiera el grupo,
   las plantillas de D'CASA (`website_dcasa.*`, `dcasa_*.*` y la portada `website.homepage`) no admiten
   copias por sitio ni ediciones desde el panel. El mensaje: «Esta página se mantiene desde el código y no
   se edita desde aquí: pide el cambio a quien mantiene el sitio». De una página de D'CASA solo se puede
   publicar/despublicar y cambiar su título y descripción para Google. No frena instalar ni actualizar
   módulos, ni lo que Odoo hace por dentro (`sudo`), y un administrador puede apagarla con el parámetro
   `dcasa_interfaz.sitio_editable` = 1 (ver `docs/OPERACION.md`).

## Qué se conservó

- **Vista previa móvil** (nueva, propia): «Sitio web → Vista previa móvil» y el botón **Ver en el
  celular** del Inicio. El sitio público en un marco de teléfono 390×844, con alternador a tableta (768)
  y escritorio (1440), atajos a Inicio / Tienda / Socios / Visítanos, dirección a mano, Recargar y Abrir
  aparte. Usa la dirección canónica del sitio (`web.base.url`, que el despliegue fija a
  `https://dcasapty.com` o al dominio de staging) si coincide con la del panel; si el panel se abrió por
  otra dirección (p. ej. `workers.dev`), enmarca esa misma, porque el borde solo permite enmarcar al mismo
  origen (`frame-ancestors 'self'` y `X-Frame-Options: SAMEORIGIN`, `edge/src/routing.ts`). Nunca entra en
  modo edición y no carga el constructor.
- **Páginas** (ver y publicar), **Productos** (publicar/despublicar, fotos, textos, categorías),
  **Pedidos** de la tienda, **Ventas en línea**, **Configuración** (WhatsApp del sitio, pagos, entregas).
- «Sitio web» pasa a verse para **Gerencia** (antes solo quien tuviera el grupo de editor).

## Consumo

- Para el visitante: igual que antes (el constructor nunca se cargaba en la página pública).
- Para el panel: menos. La pantalla «Sitio web» de Odoo precargaba el constructor
  ({{BUILDER_JS}} + {{BUILDER_CSS}}) y una consulta de bloques cada vez que se abría; la vista previa
  nueva no. El resto del panel pesa lo mismo.
- Para el servidor: nada nuevo corre de fondo; la guarda son dos comprobaciones en memoria al guardar una
  vista o una página (algo que casi nunca ocurre fuera de un despliegue).

## Pruebas

`addons/dcasa_interfaz/tests/test_sitio.py`: nadie queda con grupos de editor tras actualizar (y la
actualización los vuelve a retirar si alguien los puso); los menús del constructor no salen para Gerencia
y los útiles sí; la guarda bloquea la copia por sitio de una plantilla de `website_dcasa` con el mensaje,
deja pasar las copias de Odoo (`website_sale`) y lo interno; la portada solo se publica y cambia su SEO; la
vista previa existe, cuelga de «Sitio web», apunta a la URL canónica y no usa modo edición.

**Pendiente para quien mantiene `website_dcasa`** (fuera del alcance de esta ronda): su
`security/dcasa_roles_website.xml` sigue dándole «Editor y diseñador» a Gerencia (lo retira
`dcasa_interfaz` en cada actualización) y su `tests/test_roles.py` afirma lo contrario de esta política;
conviene borrar el primero y voltear el segundo.
