# Catálogo para Meta (Facebook e Instagram) — `dcasa_meta_catalogo`

Puesto al día el 2026-10-17. Es el **Paquete 1** del diseño de Meta (catálogo, píxel y Conversions API). El
**Paquete 2** (`dcasa_meta_eventos`: píxel, ventas reportadas a Meta y consentimiento) está en
[META_EVENTOS.md](META_EVENTOS.md).

## En palabras sencillas

- Meta (Facebook e Instagram) puede mostrar anuncios de tus muebles con su foto, su precio y su enlace. Para eso
  necesita una **lista de tus productos**: el catálogo. Odoo la arma sola y Meta la lee cada hora o cada día desde
  una **dirección secreta**.
- **Viene apagado.** Mientras no lo enciendas, la dirección no entrega nada.
- Van **todos los productos publicados en la tienda en línea**, menos:
  - los que marques **«No anunciar en Facebook e Instagram»** (en la ficha del producto o en la lista de Productos);
  - los que **no tienen foto**;
  - los que tienen **precio cero**.
- El **precio** es el mismo que se ve en la página del producto: hoy **sin ITBMS** (la web dice «+ ITBMS»).
- Nunca van la referencia del proveedor, el código de barras, el costo ni nada interno. Sí va el **código público**
  (DC-…), el mismo que el cliente ve en la tienda.
- Con las **campañas** («Navidad», «Regreso a clases»…) marcas varios productos a la vez y en Meta armas con ellas el
  grupo de productos que se anuncia.

### Dónde está

| Quiero… | Voy a… |
|---|---|
| Encender o apagar el catálogo, copiar la dirección, ver cuántos van y cuáles quedan fuera | Sitio web › Anuncios en Meta › **Catálogo para Meta** |
| Crear o archivar una campaña | Sitio web › Anuncios en Meta › **Campañas para anuncios** |
| Poner una campaña en varios productos a la vez | Productos (la lista): marca los productos y escoge la campaña en la columna **«Campaña (Meta)»** |
| Que un producto no salga en los anuncios | La ficha del producto › pestaña Ventas › **Anuncios en Meta** › «No anunciar en Facebook e Instagram» |

Solo **Gerencia y los administradores** ven estas pantallas y estos campos. La Vendedora no.

> **Por qué «Sitio web › Anuncios en Meta» y no «Sitio web › Configuración»:** en Odoo 19 «Configuración» es solo de
> administradores (`base.group_system`) y Gerencia no lo vería. El diseño pide que lo use Gerencia.

### Cómo se conecta con Meta (cuando se traslade el dominio)

1. Odoo necesita su **dirección pública con https** (`web.base.url` congelado con el dominio). Mientras sea una
   dirección local, la pantalla dice «Todavía no hay dirección» y la ruta responde 503: nunca se le dan a Meta enlaces
   de la máquina.
2. En **Commerce Manager**, crea el catálogo «D'CASA» › Orígenes de datos › Feed de datos › **Programado**. Pega la
   dirección que muestra Odoo, frecuencia cada hora o diaria, moneda USD.
3. En Odoo, **enciende** el catálogo y en Meta dale a «Subir ahora». Si Meta no puede leerla, avisar: puede ser el
   bloqueo de bots de Cloudflare.
4. Para anunciar una campaña: en el catálogo de Meta › Conjuntos de productos, crea el conjunto con **«Etiqueta
   personalizada 1 es igual a navidad»** (el código de la campaña).
5. Si cambias la dirección secreta («Cambiar la dirección secreta»), la vieja deja de funcionar: hay que pegar la
   nueva en Meta.

## Decisiones de la dueña (pendientes; están construidas con la recomendación del diseño)

| # | Pregunta | Cómo quedó | Recomendación |
|---|---|---|---|
| 1 | Precio en el catálogo | El de la página, **sin ITBMS** | Así (espera la pregunta 9.4.5 al abogado: ¿un anuncio puede mostrar el precio sin ITBMS si la página dice «+ ITBMS»?) |
| 2 | Disponibilidad | «Como la tienda en línea»: todo lo publicado sale disponible | Así hasta que el inventario sea real; después, «Según las existencias» (un clic en la pantalla) |
| 3 | Marca (`brand`) | El nombre de la empresa | Que ella confirme: ¿«D'CASA Panamá» o la del fabricante? Se cambia en la pantalla |
| 4 | Condición | «Nuevo» para todo | Que confirme si hay piezas de exhibición; hoy es una sola condición para todo el catálogo |
| 5 | Qué productos entran | Todos los publicados, menos los que ella marque | Así |

Nada de esto lleva cifras inventadas: no hay precios, descuentos ni existencias escritos a mano; todo sale de Odoo.

## Para quien programa

### El contrato con `dcasa_meta_eventos` (diseño §2.1)

- `id` del catálogo = `content_ids` del píxel = `content_ids` de la Conversions API = `str(product.product.id)`
  (la variante, en decimal y sin prefijo). `content_type` siempre `product`.
- `item_group_id` = `g<product.template.id>`, solo si la plantilla tiene más de una variante activa.
- Nunca se usa como id `default_code` (referencia del proveedor), `barcode` (etiquetas internas, no GTIN) ni el código
  DC (no existe por variante). Los dos módulos no dependen uno del otro; una prueba cruzada de la unión lo verifica.

### La ruta

`GET /dcasa/meta/catalogo.csv?feed=<id>&token=<access_token>` (`controllers/catalogo.py`): `auth='public'`,
`save_session=False`, `sitemap=False`, sin la capa del sitio (no pone `frontend_lang`).

| Caso | Respuesta |
|---|---|
| Sin `feed`, `feed` inválido o que no existe, o un feed que no es de Meta | 404 |
| Token malo (comparado en tiempo constante con `_find_and_check_feed_access` de Odoo) | 403 |
| Catálogo apagado (`dcasa_activo`) | 404 |
| Sin dirección pública **https** (`website._dcasa_url_publica()` vacío o `http://`; decisión de esta entrega: nunca enlaces sin cifrar) | 503 con `Retry-After` |
| Otra petición lo está armando y no hay ninguno guardado | 503 con `Retry-After: 60` |
| Bien | 200, `text/csv; charset=utf-8`, **sin gzip** (no verificado que Meta lo acepte; Cloudflare comprime), `Cache-Control: no-store`, `X-Robots-Tag: noindex, nofollow`, sin `Set-Cookie` |

`/gmc.xml` (el feed nativo de Google) **nunca** sirve un feed de Meta (`_render_and_cache_compressed_gmc_feed` y
`_render_gmc_feed` lo rechazan): ese formato publica la referencia del proveedor y el código de barras. Un catálogo de
Meta tampoco se puede convertir en otro tipo, y su token solo se cambia por uno de 32 caracteres al azar
(sobrescritura de `write`). **Borde:** la ruta pasa directo a Odoo; no está en la caché de páginas ni en
`CACHEABLE_PATTERNS`; no se tocó `edge/`.

### El CSV

UTF-8 sin BOM, módulo `csv`, cabecera en este orden:
`id, item_group_id, title, description, availability, condition, price, sale_price, sale_price_effective_date, link,
image_link, additional_image_link, brand, product_type, custom_label_0 … custom_label_4`.

| Columna | De dónde sale |
|---|---|
| `title` | El nombre sin `default_code` (`display_default_code=False`); en las variantes, con sus atributos. ≤ 150, cortado en una palabra |
| `description` | `description_sale`; si no, `description_ecommerce` en texto plano (sin HTML ni enlaces, tipo oración si venía todo en mayúsculas, ≤ 5,000); si no, el título |
| `availability` | `in stock` / `out of stock` (con espacio). «Como la web»: todo `in stock`. «Según existencias»: `out of stock` si `dcasa_stock` ≤ 0 en un producto que controla inventario |
| `condition`, `brand` | Los del catálogo (pantalla) |
| `price` | El que dibuja la ficha: `_get_additionnal_combination_info` con el sitio, nunca `list_price` directo. La tarifa es la de un visitante anónimo que llega por primera vez: la misma función de la ficha (`website._get_and_cache_current_pricelist`), como el usuario público, sin carrito y sin lo que recuerde la sesión de quien pide. Formato `399.00 USD` (decimales de la moneda; no `gmc_format_price`, que escribe `40.0 USD`). Con descuento, `price` es el tachado y `sale_price` el que se paga |
| `sale_price`, `sale_price_effective_date` | Solo si la tarifa marca descuento (`has_discounted_price`); fechas ISO 8601 en UTC, `inicio/fin`, como Odoo |
| `link` | La URL pública absoluta de la variante (`website_url`, con `?attribute_values=` en las variantes). Sin UTM: van en el anuncio |
| `image_link` | `website._dcasa_img_url(variante, 1024, 'jpg')` absoluta: JPEG a 1024 px con versión `?v=` |
| `additional_image_link` | Hasta 10 fotos extra (las de la variante y luego las del producto), separadas por coma |
| `product_type` | La ruta de la categoría pública principal, con « > » |
| `custom_label_0` | La categoría pública principal (la primera por `sequence`), en ASCII: `habitacion_de_ninos` |
| `custom_label_1` | El código de la campaña (vacío si no tiene o si la campaña está archivada) |
| `custom_label_2` | `disponible` / `pocas` (5 o menos, el umbral de Juan y del Escáner) / `agotado`, según `dcasa_stock`; sin control de inventario (combos), `disponible`. Mientras el inventario no esté confirmado no se usa para anuncios; se emite igual |
| `custom_label_3` | Franja de precio con los mismos cortes de los filtros de Productos: `hasta_100`, `100_a_300`, `300_a_600`, `mas_de_600` (una prueba lo compara) |
| `custom_label_4` | El código público `DC-…`, en mayúsculas, tal como lo ve el cliente |

Las etiquetas 0 a 3 son solo `[a-z0-9_]`, ≤ 100: los filtros de conjuntos de Meta no admiten tildes ni eñes.

**Qué entra** (`_get_feed_product_domain` para `target='meta'`): `website._dcasa_dominio_publicado()` visto por el
visitante anónimo (publicado y a la venta en ese sitio), `sale_ok`, `dcasa_meta_no_anunciar = False` y, si el feed tiene
categorías, solo esas. Después quedan fuera las variantes sin foto, las de precio de lista cero (o cuyo precio en la ficha es cero) y las
que no son posibles (`_is_variant_possible`). Rige el límite nativo: 5,000 productos (constraint) y 6,000 como tope duro.

**Nunca salen:** `standard_price` ni ningún costo o margen, `default_code`, `seller_ids` ni códigos o nombres del
proveedor, `barcode`, `gtin`, `mpn`, notas internas, productos sin publicar o archivados.

### Caché y rendimiento

- El CSV se guarda en gzip en `feed_cache` (el campo nativo) y se sirve descomprimido. Se vuelve a armar solo si cambió
  la huella (`dcasa_huella`) o pasó un día (`cache_expiry`); «Regenerar ahora» es el `action_invalidate_cache` nativo.
- La huella son ~10 consultas de `count` y `max(write_date)` sobre los productos y variantes del dominio, fotos extra,
  precios extra de atributos, categorías públicas, campañas, reglas de tarifa, impuestos y existencias, más la
  configuración del feed y del sitio y la fecha del día. Así no se reescribe el adjunto en R2 cuando nada cambió.
- Mientras otra petición lo arma (`lock_for_update`, sin esperar), se sirve el guardado.
- Fotos y existencias van por lotes de 200. Medido el 2026-10-17 (`tests/test_rendimiento.py`, con su tope): **36
  consultas para 20 productos y las mismas 36 para 60**; si la tienda usa tarifas, el precio de cada ficha busca sus
  reglas y crece ~1 consulta por producto (56 para 20, 96 para 60).

### Permisos

- `dcasa.meta.campana`: lectura para usuarios internos; escribir, crear y borrar para Gerencia
  (`sales_team.group_sale_manager`) y administradores.
- `product.feed`: Gerencia lee y escribe (no crea ni borra). Los menús son de Gerencia y administradores.
- `dcasa_meta_no_anunciar` y `dcasa_meta_campana_id` en el producto llevan `groups` de Gerencia y administradores: la
  Vendedora no los ve ni los escribe, tampoco por RPC.
- Botones (en `LISTA_BLANCA` de `dcasa_base/tests/test_superficie_rpc.py`): «Cambiar la dirección secreta»
  (`action_dcasa_meta_nueva_direccion`) y «Ver los que quedan fuera» (`action_dcasa_meta_ver_fuera`) exigen Gerencia o
  administrador en el servidor antes de cualquier `sudo()`; y la sobrescritura de `write`.

### Decisiones de esta entrega (sobre el diseño)

- **Interruptor** `dcasa_activo` («Encendido», apagado de fábrica y en el historial del catálogo): el diseño §1.3 pide
  que nada salga sin su interruptor; apagado, la ruta responde 404 sin datos.
- **Solo https:** sin dirección pública `https://` no hay URL ni CSV (503), para no darle a Meta enlaces sin cifrar.
- **Menú propio** «Sitio web › Anuncios en Meta» (ver arriba por qué no «Configuración»). El Paquete 2 decide dónde
  cuelga «Eventos enviados a Meta»; no depende de este módulo.
- **Existencias por plantilla** (`dcasa_stock`, como dice el contrato §2.3): todas las medidas de una cama comparten la
  etiqueta. Lo que no controla inventario (combos) es `disponible`, como en el Escáner y en Juan.
- **El código de la campaña** se calcula del nombre al crearla y no cambia al renombrarla (si cambiara, el conjunto
  de Meta se quedaría vacío). Solo `[a-z0-9_]`, único.
- **Los dos campos del producto** (`dcasa_meta_no_anunciar`, `dcasa_meta_campana_id`) son de Gerencia y
  administradores también en el servidor (`groups` en el campo).

### Brian

No lleva herramienta en esta ronda (diseño §7.9): marcar campañas y ver el estado de lo enviado a Meta quedan para
después. Mientras tanto Brian sí encuentra las pantallas: las tareas «Anunciar tus productos en Facebook e
Instagram», «Marcar productos para una campaña de anuncios», «Ver qué ventas se reportaron a Meta» y «Conectar el
píxel de Meta y mandar un evento de prueba» (esta, de la unión) están en la Guía (`dcasa_guia/data/guia.json`) y su
herramienta `buscar_en_guia` las devuelve, a cada quien solo las que puede abrir.

### Sin verificar con la documentación oficial de Meta (se comprueba al conectar)

- Si `brand` es obligatorio.
- Que Meta acepte `additional_image_link` separado por comas en el CSV.
- El formato exacto de `sale_price_effective_date`.
- El agente con que Meta descarga el feed (por el bloqueo de bots de Cloudflare).

### Pruebas

`addons/dcasa_meta_catalogo/tests/` (`post_install`; ninguna llama a Meta; `web.base.url` = `https://tienda.example`):
reglas puras (etiquetas, franjas contra los filtros de `dcasa_catalogo`, «pocas», formato de precio, texto plano),
contenido (qué entra y qué no, una fila por variante, `item_group_id`, disponibilidad en los dos modos, etiquetas y
campañas), privacidad (ni `default_code`, ni costo, ni código de barras, ni datos del proveedor), precio (igual al
que dibuja la ficha, con variante y con descuento), acceso (apagado, 403/404/503, cabeceras, `/gmc.xml`, enlaces
https), caché, rendimiento, campañas y permisos.
