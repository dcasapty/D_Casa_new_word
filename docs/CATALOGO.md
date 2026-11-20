# Catálogo real

De dónde sale lo que se vende en Odoo (inventario, ventas y tienda web: es el mismo producto).

## Fuentes

- `fuentes/carga-inicial/DCASA_listado_productos.xlsx`, hoja «Productos»: código, nombre, precio
  **sin ITBMS** («+ITBMS»), precios por tamaño, combo/el par, existencias y observaciones.
- `fuentes/carga-inicial/*.png`: fotos originales. **El nombre es el código**: `CODIGO.png` o
  `CODIGO_1.png`, `CODIGO_2.png`… (varias fotos del mismo producto). Una `/` del código
  se escribe `-` en el archivo. No van en la imagen Docker (`.dockerignore`).
- `up media/` es la **bandeja de entrada** de la dueña (sube desde GitHub, sin terminal): ahí solo
  queda lo pendiente. Con cada subida, `.github/workflows/up-media.yml` corre
  `scripts/procesar_up_media.py`, que regenera el catálogo, mueve con `git mv` lo ya cargado a
  `fuentes/<pedido-o-carga>/` (y lo que no es de ningún producto a `descartado/<fecha>/`, con el
  motivo en su `LEEME.md`) y escribe `up media/RESUMEN.md` (qué foto fue a qué producto, qué quedó
  pendiente y por qué, qué Excel se cargó). El importador busca cada original primero en la
  bandeja y después en `fuentes/**`, así el catálogo se regenera completo con la bandeja vacía.
  Originales pesados: `scripts/archivar_fuentes.sh` (R2, prefijo `fuentes/`; ver
  `docs/OPERACION.md` › «Cómo subir fotos»). Operación para la dueña: esa misma sección.

## Cómo se carga

1. `scripts/importar_catalogo.py` lee el Excel y las fotos y genera:
   - `addons/dcasa_catalogo/data/catalogo.json` (precios copiados, nunca calculados);
   - `addons/dcasa_catalogo/static/img/productos/*.jpg` (1600 px, livianas);
   - `docs/CATALOGO_REVISAR.md`: lo que el Excel deja en duda.
2. El módulo `dcasa_catalogo`, al instalarse, crea los productos:
   - precio del Excel tal cual, **sin ITBMS**, con el impuesto «ITBMS 7%» que **se suma** al
     precio (decisión de la dueña, 2026-10-01; prueba: factura INV/2026/00821,
     329.99 + 23.10 = 353.09). La web muestra «$39.99 + ITBMS»; el total con impuesto
     sale en el carrito, la cotización y la factura;
   - camas/colchones con tamaños → variantes Twin/Full/Queen/King;
   - primera foto = principal, el resto a la galería; sin foto → no se publica;
   - inventario activo en 0 («Sin confirmar») y la web deja comprar igual.

## Actualizar

Con un Excel o fotos nuevas en la bandeja: `python scripts/procesar_up_media.py` (o solo
`python scripts/importar_catalogo.py` si no se quiere mover nada; los dos necesitan `openpyxl` y
`Pillow`), commit, y en la base `odoo-bin shell` →
`from odoo.addons.dcasa_catalogo.catalogo import cargar_catalogo; cargar_catalogo(env); env.cr.commit()`.
Solo crea los códigos que falten: lo que se cambió en Odoo (precios, fotos, textos) no se pisa.

## Regla de precios: todo termina en .99

Decisión de la dueña (2026-10-02): **todo precio termina en .99**. Se conserva la parte entera
y los centavos pasan a .99: 318.66 → 318.99, 439.98 → 439.99, 186.64 → 186.99; 129.99 queda
igual. Vale para el precio del producto y para los de combo, siempre **sin ITBMS**.
Código: `reglas.precio_terminado_en_99` (con tests en `tests/test_pedido_ltsc07.py`).

## Pedidos nuevos cargados como la mercancía inicial (LTSC-07)

El pedido LTSC-07 (`fuentes/LTSC-07/Catalogo_LTSC-07_Precios_PRODUCTOS_NUEVOS.xlsm`, hoja «Catálogo
LTSC-07», encabezado en la fila 4) entra por el mismo camino que la carga inicial —inventario
**y** tienda web— y no por Brian. `scripts/importar_catalogo.py` (lista `PEDIDOS`) lo agrega a
`catalogo.json`:

- **Precio**: «Precio cama sola» con la regla .99. Las columnas «Total con ITBMS» se ignoran.
- **Combo**: las columnas Imperial / Dulce Sueños / First Class son cama + colchón **sin
  ITBMS**; van a «Precio en combo o el par» con el nombre del colchón y la regla .99:
  «Combo con colchón First Class $439.99». Celda vacía = sin combo (no se inventa).
- **Medidas**: «Largo × Ancho × Alto: 203 × 193 × 123 cm». Si el Excel pone «Queen» o «Full»
  en vez de medidas, o las medidas no cuadran (`medidas_dudosas`), la ficha sale sin medidas.
- **Mismo código, varios colores** (908K beige/negro/gris, 908Q beige/negro): **un** producto
  con variantes del atributo «Color», el mismo precio en cada color y cada variante con su foto
  (`image_variant_1920`) y su galería; referencia `908K-BEIGE`, `908K-NEGRO`…
- **Código que ya estaba en el catálogo** (Y0300300, $159.99): el que estaba **no se toca**
  (ni precio ni foto); las unidades del pedido son un producto aparte con sufijo:
  `Y0300300-LTSC07` a $129.99 (decisión de la dueña). Sin textos de promoción en el nombre.
- **Fotos** (`up media/` y `fuentes/LTSC-07/`, las que no son de la carga inicial; .jpg/.png/.webp), en este orden
  (`reglas.asignar_foto`):
  1. decisiones revisadas a mano, con su motivo (`decisiones` del pedido en el script);
  2. código al inicio del nombre del archivo (`908K - Cama…`, `Y0200201 -Full…`); si el código
     tiene varios colores, el color del archivo elige la variante; si el color o el material
     del archivo no son los del Excel, se asigna igual por código y queda el aviso;
  3. sin código: tamaño + color + medidas del nombre deben señalar **una sola** fila del Excel
     («Queen – crema 205 × 151» → 825Q). Si señalan varias, no se adivina: decisión a mano o
     sin foto, y queda anotado.
  Si no hay foto en la carpeta, va la foto incrustada en la fila del Excel. Varias fotos: la
  primera es la principal y las demás van a la galería («con colchón» al final). Se guardan
  como `<código>[-color]_<n>.jpg` (o `_excel.jpg`), 1600 px, JPEG.
- **Publicación**: con foto se publica (igual que la carga inicial); categoría según el nombre
  (`reglas.categoria_de_nombre`: camas → Recámaras) y tamaño único como atributo «Tamaño».
- Cada asignación de foto, cada precio (Excel → cargado) y cada duda quedan en
  `docs/CATALOGO_REVISAR.md` › «Pedido LTSC-07».

**Despliegue**: la base de staging ya existe, así que la carga no corre en la instalación sino
en la migración `migrations/19.0.1.3.0/post-migrate.py` (`-u dcasa_catalogo` de
`docker/entrypoint.sh` al cambiar `APP_VERSION`): `cargar_catalogo` crea solo los códigos que
faltan. Un código que ya existe en Odoo sin ser de esta carga (p. ej. lo cargó Brian) no se
duplica ni se pisa: queda en el registro.

## Existencias de prueba (solo staging)

Para probar ventas en staging, cada producto inventariable recibe **10 unidades** en el
almacén principal (pedido de la dueña; después la dueña pone las reales). Seguro por diseño:

- Parámetro `dcasa_catalogo.stock_prueba` (vacío o 0 = apagado). Lo fija `docker/entrypoint.sh`
  desde `DCASA_STOCK_PRUEBA` (`edge/wrangler.jsonc`: `10` en staging, `0` en producción). Con
  `DCASA_ENTORNO` distinto de `staging` queda **siempre en 0**: producción no recibe
  existencias inventadas.
- `catalogo.aplicar_stock_prueba` solo toca productos inventariables, sin lote/serie, con
  existencias 0 y **sin ningún movimiento de inventario**: un conteo real o una venta nunca se
  pisan. Usa el ajuste de inventario de Odoo (`stock.quant._apply_inventory`), que deja su
  movimiento: la segunda vez ya no hace nada.
- Corre en la migración 19.0.1.3.0 y, en staging, una vez por versión desde el entrypoint
  (paso «2c»), después de fijar el parámetro.

## Inventario nuevo desde el Excel de un proveedor (Brian)

Para los pedidos nuevos no hace falta el script ni un commit: se le manda a Brian el Excel del
proveedor (p. ej. «Catálogo LTSC-07»: título arriba, encabezado en la fila 4 y una foto por
producto en la columna «Imagen») y se le pide cargarlo.

1. `proponer_importacion` arma la vista previa: qué se crea, qué cambia de precio (antes →
   después), qué se omite y por qué, y con qué foto. No toca nada.
2. Gerencia revisa los avisos (códigos repetidos, sin precio, cambios de más del 30 %) y aplica
   con `aplicar_importacion` (confirmación con un clic).
3. Los productos nuevos siguen las mismas reglas de esta carga (`valores_producto_nuevo` y
   `reglas.py`, compartidas con `scripts/importar_catalogo.py`): precio del Excel tal cual,
   **sin ITBMS** (`modo_itbms = mas_itbms`), ITBMS 7 % que se suma, categoría y tamaño según el
   nombre, foto del Excel. Nacen **sin publicar**: se publican uno a uno con Brian
   (`publicar_producto_web`) o desde el producto, después de revisar nombre y fotos.
4. Si algo salió mal: `deshacer_importacion` (borra lo creado que nadie usó, archiva lo demás y
   devuelve los precios anteriores que nadie haya cambiado a mano).

Detalle técnico: `docs/BRIAN.md` › «Importar productos desde el Excel de un proveedor».
Los precios de combo (cama + colchón) de esos Excel son fórmulas sobre la tabla de colchones y
no se importan: el combo se escribe a mano en «Precio en combo o el par» si se quiere mostrar.

## Stock ordenable en Productos (para armar una campaña)

Pedido de la dueña (2026-10-10): el equipo de marketing arma las campañas a partir del inventario y necesita, en la
**misma lista de Productos**, ver qué categoría tiene más o menos stock y, dentro de ella, ordenar por precio (por
ejemplo, «las camas: cuál tiene más stock, cuál menos, de la más barata a la más cara»).

- **Cómo está hecho** (`dcasa_catalogo`, `models/product.py`): el campo `dcasa_stock` («Stock») es el mismo número que
  el «A la mano» de Odoo, pero **guardado en el producto** y recalculado solo con cada entrada, venta, ajuste o
  traslado. Odoo calcula el «A la mano» al vuelo y por eso su columna no se puede ordenar ni sumar por categoría.
  Suma todas las medidas y colores de la ficha (en las ubicaciones internas: bodega y tienda), vale 0 si el producto no
  controla inventario y no cuenta las medidas archivadas. Hay una prueba que lo compara con el «A la mano» de Odoo.
- **Dónde:** Inicio → **Productos**, Ventas → **Productos** e Inventario → **Productos**. Abren en lista (las tarjetas
  siguen a un clic en el selector de vistas). Ya no existe la pantalla aparte «Stock y precios».
- **Cómo se usa** (de izquierda a derecha en la pantalla):
  1. **Categorías a la izquierda** (con cuántos productos tiene cada una): toca «Camas».
  2. **Filtrar:** botones de un clic arriba: Disponibles, **Pocas unidades** (1 a 5), Agotados, rangos de precio
     (hasta $100, $100 a $300, $300 a $600, más de $600), En la tienda en línea, Sin foto. Se pueden sumar.
  3. **Ordenar:** botones **Mayor stock · Menor stock · Mayor precio · Menor precio**. Solo cambian el orden: los
     filtros y la categoría se quedan. Otro clic en el mismo botón vuelve al orden de siempre. Para ver lo que más
     escasea sin los agotados: «Disponibles» + «Menor stock». También se ordena tocando el título de la columna
     **Stock** o **Precio**.
  4. **Favoritos** (menú de la lupa): los mismos cuatro órdenes como favoritos compartidos, que sirven también en tarjetas.
- **Columnas:** foto, nombre, código, categoría de la tienda, precio, **Stock** (rojo si es negativo, naranja si es 0),
  publicado. El «A la mano» y el «Previsto» de Odoo siguen en las columnas opcionales (los esconde el selector de
  columnas de la derecha); el costo también.
- **Qué suma el stock de una ficha con medidas:** la ficha de una cama muestra el total de sus medidas (Twin, Full,
  Queen, King). Para ver cada medida, Inventario → **Variantes** (si está activado en Ajustes).
- **Se retiró** la pantalla de solo lectura «Stock y precios» que se había hecho primero (modelo `dcasa.producto.stock`):
  al actualizar el módulo, Odoo borra sus menús, vistas y favoritos solo.

## Black Weekend

Banda negra con titular amarillo en la portada (antes de los carriles), página `/black-weekend`
(con sitemap, canónica, `ItemList` y la imagen para compartir; la caché del borde guarda la misma página) y etiqueta
«Black Weekend» en las tarjetas de los productos marcados.

- **Qué productos:** los marcados en el producto (casilla «Black Weekend» junto a la categoría, con su orden y,
  si tiene colores, la variante destacada). La migración 19.0.1.4.0 de `dcasa_catalogo` marca los
  12 que eligió la dueña (`catalogo.BLACK_WEEKEND`; 908K en negro). Se pueden marcar o desmarcar
  más desde Odoo.
- **Precios:** los de la tienda (la tarifa del visitante), nunca escritos en una plantilla: si
  cambia el precio en Odoo, cambia la página. La línea «Combo con colchón <colchón> $X + ITBMS»
  sale del campo «Precio en combo o el par» (texto del Excel LTSC-07).
- **Cuándo se ve** (`ir.config_parameter`, hora de Panamá):
  - `dcasa_black_weekend.inicio` / `.fin`: `2026-10-02` / `2026-10-11` (decisión de la dueña, adelantada
    el 2026-10-02 para presentar la página el lunes 5: del viernes 2 a las 00:00 al domingo 11 a las 23:59:59, inclusive). Fuera de la ventana desaparece sola.
  - `dcasa_black_weekend.activo = 1`: visible ya, sin mirar fechas (staging, vista previa).
  - En el despliegue los fija `docker/entrypoint.sh` desde `DCASA_BLACK_WEEKEND` (producción `0`,
    staging `1`) y `DCASA_BLACK_WEEKEND_INICIO` / `_FIN` (`edge/wrangler.jsonc`). Para otra fecha:
    cambiar esas variables (o el parámetro en Ajustes › Técnico › Parámetros del sistema si la
    variable queda vacía).
  - La caché de páginas del borde se invalida al cambiar la marca o un parámetro, y el cron horario
    «D'CASA: Black Weekend» la invalida (y borra el sitemap guardado) cuando la campaña empieza o
    termina sola.
- **Lo que no lleva:** cuenta regresiva, «tiempo limitado», «remate», cuotas ni financiamiento
  (tafi: descartado por la dueña el 2026-10-02). Las gráficas de la dueña
  (`fuentes/graficas-black-weekend/115.png` … `153.png`) no son fotos de producto: solo `115.png` completa es la imagen para
  compartir (la dueña aceptó, el 2026-10-02, que ahí salgan tafi y «tiempo limitado»; la página no
  los repite). Revisión de las gráficas: `docs/CATALOGO_REVISAR.md`.

## Inventario del sistema anterior (capturas del 2026-10-02)

Las 7 capturas de Inventario → Productos del Odoo anterior (`up media/inventario-anterior/`, 535
productos) están transcritas en `inventario_anterior.csv` (doble lectura independiente por captura;
columna `dudas` con lo que se confirmó con zoom) y copiadas en `addons/dcasa_catalogo/data/`.
`inventario_anterior.cargar_inventario_anterior` las aplica en la migración 19.0.1.7.0 y al dar de
alta una base nueva, con las reglas de la dueña (LEEME del inventario):

- Llave = código (`default_code`); sin código, el nombre exacto. Mismo código: existencias, costo y
  precio si cambiaron (nombre y fotos no se tocan; el inventario manda sobre el precio, también en
  los del pedido LTSC-07: el informe lista los 23 que cambian). Código nuevo: producto nuevo,
  categoría por las palabras del nombre (`reglas.CATEGORIAS`), precio SIN ITBMS, publicado solo si
  tiene foto en `static/img/productos` (archivo que empieza por el código).
- Un código del inventario que en el catálogo tiene tamaños como variantes (`N-F10018-F-BK` →
  `N-F10018-F-BK-FULL`, `XHT022-F-W` → `XHT022-F-W-FULL`) se aplica a la variante del tamaño que dice
  el nombre, sin crear otro producto.
- «A la mano» → ajuste de inventario en el almacén principal; negativo → 0 y a la lista de conteo.
- «COMBO … + COLCHÓN» → producto sin publicar. «Descuento», «Propinas» y «X COLCHÓN … PARA COMBO»
  no se importan. Un código repetido en el CSV (XXI070507) solo entra la primera vez.
- Idempotente: la segunda corrida no crea nada ni deja movimientos.

Informe para la dueña: `scripts/inventario_anterior_informe.py` escribe
`docs/inventario-anterior-informe.md` (resumen y listas) y `docs/inventario-anterior-fotos-faltantes.xlsx`
(código, nombre, existencias de los productos nuevos sin foto).

## Combos de cama y colchón

> **Desde el 2026-10-22 lo práctico es armar el combo en la cotización** («Armar combo cama + colchón»), con el
> **precio en combo** de cada colchón por medida que pone Gerencia (*Ventas › Productos › Precios en combo*): ver
> [OPERACION.md](OPERACION.md), «Combos cama + colchón que se arman en la venta». Lo que sigue (el producto tipo
> «Combo» fijo) sigue funcionando para los combos que ya existen.

Un combo junta la cama y el colchón en **un solo producto con un solo precio**. Es el tipo **Combo** que ya trae Odoo
(no se instala nada). Los combos de la web siguen con su línea «Combo con colchón … + ITBMS» de arriba: esto es para
**vender** el combo en una cotización, una entrega y una factura.

**Crear o cambiar uno a mano** (también está en la Guía: «Crear o cambiar un combo fijo de cama y colchón (producto «COMBO»)»):

1. **Ventas › Productos › Productos › Nuevo.** Para cambiar uno que ya existe, búscalo por su nombre (empiezan con
   «COMBO»).
2. Escribe el **nombre**, como los demás: `COMBO CAMA KING … + COLCHÓN …`.
3. En **Tipo de producto** escoge **Combo**.
4. En **Precio de venta** pon el precio del **combo completo, sin ITBMS** y terminado en .99 (la regla de arriba). No es
   el de la cama ni el del colchón.
5. En **Opciones de los combos** escribe «Cama», toca **Crear y editar…** y, en la ventana que abre, agrega una línea
   con la cama; guarda. Repite con «Colchón».
   - Si el cliente puede **escoger entre varios colchones**, ponlos todos en el **mismo** grupo. En **Precio extra** pon
     cuánto sube el combo si escoge ese (0 si no sube nada).
   - Si el combo lleva **más de una pieza igual** (un camarote con tres colchones), crea **un grupo por cada una**.
6. **Guardar.** Un combo nuevo no sale en la tienda en línea hasta que lo publiques.

Qué hay que saber: las piezas (la cama y el colchón) tienen que existir ya como productos y estar a la venta; un combo
no puede llevar otro combo; el combo no tiene existencias propias (se cuentan la cama y el colchón); y **no se escribe el
precio de cada pieza**: Odoo reparte el precio del combo entre ellas.

**Cómo se vende.** En la cotización se agrega el combo como cualquier producto. Si tiene opciones, Odoo pregunta cuál
colchón. Salen **una línea por la cama y otra por el colchón**, con su parte del precio y el ITBMS; la línea del combo
queda en $0.00 porque el precio ya está repartido en las piezas (así suma exacto: 146.99 → 90.82 + 56.17). El precio no se
cambia a mano: se rebaja con el descuento, con el mismo tope de la vendedora. Al entregar, sale de la bodega la cama y el
colchón. La factura lleva el nombre del combo como título y las dos piezas debajo.

**Cargar los combos de Cowork.** El archivo `combos.csv` se sube en **Ajustes › Cargar datos del sistema anterior ›
Combos de cama y colchón**, **después** de los productos: primero «Revisar» (no cambia nada), se lee el informe y después
«Cargar». Solo enlaza camas y colchones que ya están; si falta una, ese combo no se carga y el informe dice cuál. La
casilla **«Armar los combos desde su nombre»** sirve mientras tanto: lee cada «COMBO … + COLCHÓN …» y arma los que tienen
una sola cama y un solo colchón posibles; los dudosos solo se listan. El formato del archivo y todas las reglas están en
[MIGRACION.md › Combos de cama y colchón](MIGRACION.md#combos-de-cama-y-colchón-dcasa_migracioncombospy-reglas_combospy).

## Código público de cada producto (el que ve el cliente)

Pedido de la dueña: «Nosotros manejamos códigos que vienen de los proveedores. Pero nuestro sistema debería asignarle
automáticamente un número a cualquier producto nuevo […]. El cliente no tiene que conocer nuestros códigos actuales de
proveedores.» Ahora cada producto tiene **dos códigos distintos** y no se mezclan:

| | Referencia interna | **Código público** |
|---|---|---|
| Ejemplo | el del proveedor (`XHT022-T-W`…) | `DC-K7M4PX` (así se ve; cada producto tiene el suyo) |
| Quién lo pone | tú o el importador, a mano | **el sistema, solo**, al crear el producto |
| Quién lo ve | solo la tienda (Odoo, bodega) | **el cliente**: ficha de la tienda, WhatsApp, Juan |
| ¿Cambia? | cuando quieras | **nunca** (el cliente ya pudo guardarlo) |

- **Cómo es:** `DC-` y 6 símbolos al azar. Los símbolos son números del 2 al 9 y letras **sin vocales y sin L** (no hay
  `0`, `O`, `1`, `I`, `L`, que se confunden, ni palabras que salgan por casualidad). Siempre lleva al menos una letra,
  así nunca se parece a una etiqueta numerada del rollo (`DC0001`, ver [BARRAS.md](BARRAS.md)): **son cosas distintas**.
  Hay más de 480 millones de combinaciones y no se repite jamás, ni con los productos archivados.
- **Cuándo se pone:** al crear **cualquier** producto, venga de donde venga: a mano en Odoo, la carga del catálogo, el
  importador, Brian, un combo o al duplicar un producto (la copia recibe otro código). No hay que hacer nada.
- **Los más de 600 que ya existían** (archivados y combos incluidos) recibieron su código al actualizar el sistema.
  Es seguro repetirlo: no cambia ninguno que ya tenga código y si dos códigos chocan, sortea otro.
- **Un producto con medidas o colores** (Twin, Full, Queen, King) tiene **un solo código**: es el del mueble. La medida
  se dice aparte, como siempre («la DC-K7M4PX en Queen»).
- **Dónde se ve en la oficina:** en la ficha del producto, junto a la referencia interna; como columna en la lista de
  Productos (se puede esconder desde el selector de columnas); y se **busca** escribiéndolo en el buscador de Productos,
  en el campo «Producto» de una cotización, en el Escáner y en Brian. Sirve en mayúsculas o minúsculas, con o sin guion,
  y también un pedazo («K7M4»). Así la vendedora encuentra el mueble cuando el cliente le dice el código. (La lista
  aparte de «Variantes» de Inventario no lo busca todavía: se usa Productos.)
- **Si de verdad hace falta cambiarlo:** solo un administrador, en la ficha del producto, con el botón **Regenerar**
  junto al código (pide confirmar). El código viejo deja de servir y queda anotado en el historial del producto.
- **Qué ve el cliente en el sitio:** «Código: DC-K7M4PX» debajo del nombre en la ficha; el botón de WhatsApp de la ficha
  ya manda el nombre del mueble **con su código público**; en Black Weekend, igual. La referencia del proveedor **ya no
  sale** en ningún lado del sitio: antes se filtraba, sin verse escrita, en la dirección de la página
  (`/shop/xht022-t-w-cama-…`), en el mensaje de WhatsApp, en el nombre y el texto alternativo de las fotos y en los datos
  para Google. Las direcciones viejas siguen funcionando (llevan a la nueva). El buscador de la tienda también encuentra
  un producto por su código público.
- **Juan** (el asistente de los clientes) dice el código público; si el cliente trae el del proveedor (de una foto vieja),
  igual lo entiende.
- **QR:** la dirección `https://dcasapty.com/codigo/DC-K7M4PX` abre la ficha del producto en la tienda. Es lo que debe
  llevar el QR que se imprima para el cliente (cotizaciones, etiquetas): al escanearlo con el celular se abre el
  mueble. Si el producto no está publicado, o el código ya no existe, lleva a la tienda. El método
  `product.template._dcasa_url_codigo_publico()` da esa dirección completa. (No confundir con el QR de uso interno de los
  documentos —factura, cotización, compra, entrega—, que abre el documento en el sistema para el equipo: ver la sección
  «Código QR y código público en la factura y la cotización».)
- **Documentos impresos** (cotización, factura, nota de entrega): con el interruptor de la empresa **«Mostrar el código
  público de los productos…»** (apagado de fábrica) su columna «Código» muestra el código público en lugar de la
  referencia del proveedor. Cómo funciona y qué cambia: la sección siguiente.

Detalle técnico: el campo `dcasa_codigo_publico` y su sorteo viven en `dcasa_base/models/codigo_publico.py` (es el
único módulo que ven a la vez la tienda y los documentos); lo de la tienda está en `website_dcasa/models/producto.py`;
el relleno de lo que ya existía, en `dcasa_catalogo/migrations/19.0.1.10.0/`. Pruebas: `dcasa_catalogo/tests/test_codigo_publico.py`,
`website_dcasa/tests/test_codigo_publico_web.py`, `dcasa_barras/tests/test_codigo_publico.py` y
`dcasa_conversaciones/tests/test_herramientas.py` (clase `TestCodigoPublicoEnJuan`).

## Código QR y código público en la factura y la cotización

Dos interruptores de la empresa, en *Ajustes › Empresas › D'CASA Panamá › pestaña «Documentos D'CASA»*, sección
**«Código QR y código público»**. Los dos vienen **apagados** y **apagados no cambian nada**: la factura, la nota de
crédito, la cotización, el pedido y la nota de entrega salen idénticos, píxel por píxel, a como la dueña los aprobó (un
test compara el HTML de cada uno contra el aprobado, `dcasa_invoice/tests/aprobado/`, y falla si alguien toca las
plantillas sin querer). **Se encienden solo después de que la dueña apruebe una imagen del antes y el después.**

| Interruptor | Qué cambia al encenderlo |
|---|---|
| **Mostrar el código QR en la factura y la cotización** | Un QR pequeño de **uso interno** (unos 2 cm, plano, azul marino, con la nota «Uso interno») en la factura, la nota de crédito, la cotización/pedido (a la derecha de los textos de garantía, cambios y términos) y la nota de entrega (al final, a la derecha). El equipo lo escanea y se abre ese documento en el sistema. No lleva datos del cliente. No se mueve nada más. Detalle: [BARRAS.md](BARRAS.md#qr-de-los-documentos-uso-interno). |
| **Mostrar el código público de los productos en la factura y la cotización, en lugar del código del proveedor** | La columna «Código» de la factura, la cotización/pedido y la nota de entrega muestra el **código público** (`DC-K7M4PX`) en lugar de la referencia del proveedor. Un producto sin código público (flete, servicios) deja la celda **vacía**: nunca se muestra el del proveedor. En la nota de entrega, cada producto sale «[DC-K7M4PX] Nombre» (y se quita la referencia de la descripción de la entrega). Las cotizaciones y facturas **nuevas** dejan de guardar «[referencia] Nombre» en el nombre de la línea (lo que ve el cliente en el portal y en los correos). |

Lo que **no** cambia, a propósito:

* El **pedido de compra** lleva su QR **siempre** (lo pidió la dueña); no tiene interruptor porque no toca la factura. Su
  texto sigue con la referencia del proveedor (es el documento del proveedor).
* La **factura electrónica de la DGI** (`dcasa_fe_pa`: CUFE y QR de la DGI) y las **etiquetas en rollo** (`DC0001`) no se
  tocan. Este QR de uso interno es otra cosa que el QR de la DGI y que el `/codigo/DC-K7M4PX` del producto.
* Las pantallas de la oficina siguen mostrando y buscando la **referencia del proveedor** («[IM-2001] Colchón…»): el
  equipo la necesita para pedir, contar y encontrar el producto.
* Las cotizaciones y facturas **ya hechas** conservan el nombre de línea que guardaron («[IM-2001] Colchón…»). Al
  **imprimir** se limpia igual (con el interruptor encendido ya no sale la referencia); lo que no se reescribe es el texto
  guardado, que el cliente vería en el portal de un pedido viejo.

Al encender el segundo interruptor conviene revisar una factura y una cotización de cada tipo (con flete, con combo, con
un producto sin código público). La nota de entrega toma el nombre del producto de la propia entrega.

Detalle técnico: los interruptores son `res.company.dcasa_mostrar_qr_documentos` y `dcasa_mostrar_codigo_publico`
(`dcasa_invoice/models/res_company.py`); la columna sale de `lineas.codigo_a_imprimir`; el nombre de la línea, de
`product.product.get_product_multiline_description_sale` y `account.move.line._compute_name`
(`models/producto.py`, `models/account_move_line.py`); la nota de entrega, de `stock.picking._dcasa_para_imprimir` y el
contexto `dcasa_codigo_publico` (`models/stock.py`). Pruebas: `dcasa_invoice/tests/test_documentos_intactos.py` (apagado =
idéntico), `test_qr_documentos.py`, `test_codigo_publico_documentos.py`, `test_documento_ruta.py` y `test_qr_paquete.py`.

## Nota de entrega fácil de leer (la de bodega)

Pedido de la dueña (2026-10-15): en bodega hay personas con dislexia, autismo, dificultad de lectura o que dominan otro
idioma, y una nota difícil de entender es una mercancía equivocada. Un interruptor de la empresa, en *Ajustes › Empresas
› D'CASA Panamá › pestaña «Documentos D'CASA»*, sección **«Nota de entrega para bodega»**: **«Nota de entrega fácil de
leer»**. Viene **apagado**: apagado, la nota de entrega sale idéntica a como la dueña la aprobó (el mismo test del HTML
aprobado, `test_documentos_intactos.py`). **Se enciende cuando la dueña apruebe una imagen de cómo queda.**

Encendido, el cuerpo de la nota (la cabecera con la placa y el pie no cambian) es otro:

| Qué | Cómo sale |
|---|---|
| Arriba | «Nota de entrega» con el número, y en tres cuadros grandes el **pedido**, la **factura** (para compararla) y la **fecha** (dd/mm/aaaa, hora de Panamá). Sin pedido o sin factura, una raya (—). |
| Tres pasos | «1 Busca la foto · 2 Cuenta las piezas · 3 Marca el cuadro». Siempre los mismos, siempre en el mismo lugar. |
| Cada producto | Una fila con cuatro cosas siempre en el mismo orden: **casilla** para marcar, **foto**, **nombre** y **código** en letra grande, y la **cantidad**. Un producto sin foto sale con un recuadro punteado que dice «Sin foto». |
| La cantidad | Un **número** (blanco sobre azul; **solo el número**, sin «unidades»: la medida solo se escribe si no es la unidad, como metros) y **un dibujito por pieza** (la foto chica del producto, o una caja si no hay foto), hasta 10; con más, diez y un «+». Una cantidad con decimales no se dibuja. |
| Lo que falta | En una entrega ya hecha a medias, la fila dice «Faltan N» y debajo, en «Falta entregar después», lo pendiente (sin casilla). |
| Abajo | **Total de piezas** y dos rayas grandes: «Sacó de bodega» y «Recibió» (o la firma, si se firmó). |

**Cabe en una hoja carta, igual que la factura.** La nota se aprieta sola según cuántos productos lleva (`entrega_facil.densidad`):
hasta 4, holgada; de 5 a 7, mediana; de 8 en adelante, compacta. Con **10 productos** (con su foto, su número y su casilla) y el QR
encendido sigue entrando en una sola hoja (lo vigila `test_diez_productos_con_foto_y_el_qr_caben_en_una_sola_hoja_carta`); con más,
sigue en la hoja siguiente con el encabezado repetido. El QR de uso interno, si está encendido, va **a la derecha del total y de las
rayas de firma**, no en una fila aparte, para no quitarle lugar a los productos.

Cuidados de lectura: letra Inter sin adornos y grande, alineada a la izquierda, sin cursivas, subrayados ni mayúsculas
largas; frases cortas y literales; el color nunca es lo único que informa (la casilla, los números y los dibujitos
también lo dicen); el amarillo solo toca el azul. El código sale como en la factura: el del proveedor o, con
«Mostrar el código público…» encendido, el público (`DC-K7M4PX`): la referencia del proveedor nunca se mezcla. El QR de uso
interno, si está encendido, sigue al final. Sirve igual en «Imprimir documentos» y «Imprimir todo».

Detalle técnico: el campo es `res.company.dcasa_entrega_facil`; las líneas salen de `stock.picking._dcasa_lineas_entrega_facil`
(`models/stock.py`; lo repetido se suma por producto y unidad) y las reglas puras (cuántos dibujitos, cómo se escribe una
cantidad) de `models/entrega_facil.py`; la plantilla es `views/report_entrega_facil.xml` y sus estilos están al final de
`static/src/scss/report_dcasa.scss` (sin flex ni grid: wkhtmltopdf es antiguo). Pruebas: `tests/test_entrega_facil.py`.
Pendiente: la lectura por QR de la nota (la dueña la quiere más adelante) y, si hace falta, una segunda línea en otro idioma.

## Códigos de barras

Los productos del catálogo no traen código de barras (los muebles de proveedor casi nunca lo tienen). Se asignan con las
etiquetas numeradas de un rollo, desde Inventario › Escáner › Asignar; el Escáner también encuentra un producto por su
referencia interna. Todo está en [BARRAS.md](BARRAS.md).

## Nombres en MAYÚSCULAS y productos repetidos (F5, 2026-10-22)

Decisión de la gerencia (F5): **nombres de productos en MAYÚSCULAS** y **unificar los repetidos**. Nada se cambia a
escondidas:

* **Lo nuevo** (`dcasa_catalogo/models/nombres_productos.py`): el nombre de un producto se guarda en mayúsculas al
  crearlo o cambiarlo, venga de donde venga (la ficha, la importación del Excel con Brian, el catálogo, la creación
  rápida en una línea). Solo cambian las letras (con sus tildes: «Sofá» → «SOFÁ») y se juntan los espacios repetidos.
* **Lo que ya estaba:** **Ventas › Productos › Nombres en MAYÚSCULAS** (Gerencia) muestra «así quedarán estos N
  nombres» (antes → después) y un botón los cambia, en cada idioma guardado y solo si siguen como se vieron.
* **Repetidos** (`productos_repetidos.py`): **Ventas › Productos › Productos repetidos** lista los productos de fichas
  distintas con el **mismo código** (sin importar mayúsculas, guiones ni espacios), el **mismo código de barras** (o el
  código de barras de uno es la referencia del otro) o el **mismo nombre** (sin mayúsculas, tildes ni signos).
* **Unir** (`unir_productos.py`): desde la fila, «Unir…»: eliges cuál queda y cuál se archiva y la pantalla dice antes qué
  va a pasar. No deja unir si hay algo a medias con la que se archiva (entrega o recepción sin terminar, cotización o
  compra abierta), si las dos tienen tamaños o colores (se une una ficha de un solo producto a una medida de otra), con
  lote o serie, unidades distintas o el producto del descuento. Al unir: las **existencias** pasan con un ajuste de
  inventario por cada lado, como Gerencia y con su motivo («Unificación de productos repetidos: A → B»); los **precios de proveedor**, las **piezas de combo**, las
  **reglas de tarifa** y los **premios de Socios** pasan a la que queda; las **fotos** se suman (sin repetir); el
  **código de barras** y la **referencia** pasan si la que queda no los tiene. Las **ventas, facturas y movimientos
  viejos no se reescriben**: siguen en la ficha archivada (la que queda la lista en la pestaña «Fichas unidas»). Las dos
  quedan con una nota de quién unió qué.
* **Lo que no cambia:** buscar no distingue mayúsculas (el sitio, Juan, Brian y el Escáner encuentran igual). Los
  importadores (inventario anterior, precios del sistema anterior) buscan el nombre sin importar mayúsculas.
* **Lo que ve el cliente va en formato título** (decisión de la dueña, 2026-10-22: «Lo que ve el cliente: "Cama Queen
  Tapizada", y solo por dentro queden en MAYÚSCULAS»). La regla vive en un solo lugar, `dcasa_base/nombres.py`
  (`nombre_para_cliente`): cada palabra con su primera letra en mayúscula, con tildes y Ñ («Baúl», «Muñeca»); los
  tamaños igual («King», «Queen», «Twin», «Full»); preposiciones, artículos y conjunciones en minúscula salvo al empezar
  («Cama de Metal con Baúl»); se dejan como están los códigos y lo que lleva números («DR-1024», «4/6», «3/4»,
  «[DC-K7M4PX]»), la marca «D'CASA», las siglas («MDF», «PVC», «TV», «LED») y lo que alguien ya escribió con minúsculas;
  las medidas quedan «160 x 200 cm». Dónde se aplica: la tienda (tarjetas, ficha, título de la pestaña y al compartir,
  buscador, carrito y pago, Black Weekend y el inicio, datos para Google), el portal del pedido y Mi cuenta, lo que dice
  Juan (fichas, opciones y la cotización) y el pie de foto que la vendedora le manda, la confirmación del pedido y el
  correo del carrito abandonado (`dcasa_correo/nombres_correo.py`), la cotización, la factura y la nota de entrega en
  PDF (`dcasa_invoice`) y los títulos del catálogo de Meta (`reglas_meta.titulo`, la misma regla). Las pantallas
  internas, Brian, el pedido de compra al proveedor y la factura electrónica siguen con el nombre guardado. Pruebas:
  `dcasa_base/tests/test_nombres_cliente.py` y una por cada lugar (`website_dcasa`, `dcasa_invoice`, `dcasa_correo`).
  La cotización, la factura y la nota de entrega aprobadas (`dcasa_invoice/tests/aprobado/`) cambian solo en los
  nombres; el antes y el después están en `docs/auditoria/f5-formato-titulo/`. Ojo: el título grande de la ficha
  usa la letra de titulares de la marca (Anton, en caja alta por estilo), así que ahí se sigue viendo en mayúsculas;
  la miga de pan, las tarjetas, el carrito y lo demás ya se leen en formato título.
* **Brian:** `productos_repetidos`, `nombres_por_pasar_a_mayusculas`, `pasar_nombres_a_mayusculas` (pide permiso) y
  `unir_productos` (pide permiso). Pruebas: `dcasa_catalogo/tests/test_productos_limpios.py`.

## Busca con una foto

Pedido de la dueña (2026-11-13), al verlo en la web de un competidor: «lo de buscar por foto también». Módulo
`dcasa_buscar_foto`; **nace encendido**. Se apaga y se ajusta en *Sitio web › Busca con una foto* (Gerencia y
administradores; también en la Guía).

**Para el cliente.** Un ícono de cámara **dentro de la caja de búsqueda**, justo antes de la lupa de enviar, en todas
las cajas que buscan productos: la de la cabecera (la abre la lupa de la computadora y la del celular), la del menú del
celular y la barra de `/shop`. Va en el sitio que deja el lote 1 de la web para eso
(`website_dcasa.buscador_botones_extra`, ver abajo); en el celular la barra de `/shop` ya tiene su propia fila, así que
la cámara no le quita espacio a lo que se escribe (a 360, 390 y 430 px cabe «colchon queen»). Abre el selector del
teléfono (tomar la foto o elegir una de la galería; sirve una captura de Instagram). El navegador achica la foto (lado
mayor de 1024 px, JPEG) y muestra «Buscando muebles parecidos…». La respuesta es la página `/shop/foto`, como el
catálogo: «Esto se parece a tu foto», las tarjetas de la portada (foto grande, precio «+ ITBMS», «Agregar» o «Elegir» y
el WhatsApp del mueble) y, abajo, la franja color hueso «¿No es lo que buscas?» con el botón azul «Escríbenos por
WhatsApp» (el mensaje ya escrito le pide mandar la foto: allí la lee Juan). «Recargar» no reenvía la foto (la dirección
queda en `/shop/foto`, la página para empezar).

**Por dentro** (`models/buscar_foto.py`):

1. `POST /shop/foto` con CSRF (el token se pide fresco a `/dcasa/borde/csrf`: la página puede venir de la caché del
   borde). La foto viaja en base64 en un campo de **texto** del formulario (Werkzeug lo tiene en memoria; un archivo
   de más de 500 KB lo escribiría en un temporal). Se valida por sus **bytes**: JPEG, PNG o WebP, de 1 byte a
   **1,5 MB** (igual que el Worker); la petición entera, como mucho ~2,1 MB (`max_content_length` de la ruta: más
   grande, 413 sin leerla).
2. **A lo sumo 3 búsquedas a la vez por proceso de Odoo** (un semáforo sin espera): la cuarta recibe «Ahora no podemos»
   al instante, en vez de dejar otra petición esperando al Worker.
3. **Topes**, antes de gastar IA (cambiables en la pantalla; 0 = cerrado): **10 por visitante en una hora**, **30 por
   conexión en una hora** y **200 en total por día** (hora de Panamá). El cupo se reserva en una **transacción corta
   aparte, confirmada antes de llamar al Worker**: bajo un cerrojo de PostgreSQL (`pg_advisory_xact_lock`, en READ
   COMMITTED) se cuentan las búsquedas y, si hay cupo, se anota la fila. Así cinco pedidos al mismo tiempo con tope 1
   dejan pasar uno solo, y lo que reviente después (en el Worker o al buscar) igual queda contado
   (`scripts/revision_rvf_carrera_foto.py` lo comprueba con transacciones de verdad: `odoo-bin shell -d <base> <
   scripts/revision_rvf_carrera_foto.py`, nunca en producción). La fila (`dcasa.buscar.foto.uso`) guarda la hora, el
   resultado y, solo hasta el día siguiente, dos **huellas**: de la sesión y de la **conexión** (la IPv4 entera, o la
   red /64 de una IPv6, que es lo que recibe un cliente: lo mismo que cuenta el borde), hechas con una **sal al azar del
   día** (`dcasa.buscar.foto.sal`). Es una huella que no dice quién eres y se borra al día siguiente; la sal también (el
   cron diario borra las de antes de ayer) y sin ella ya no se puede volver a calcular; la fila entera, a los 90 días.
   No se cuenta por la /24: en Panamá muchos clientes de un mismo operador móvil la comparten (y el CGNAT), y chocarían
   entre ellos. Aun así, varios teléfonos pueden salir por la misma IPv4 del operador: por eso el tope por conexión es
   más alto que el del visitante.
   El borde, además, frena ráfagas: 6 por minuto por conexión (la IPv4, o la /64 de la IPv6; cubeta `foto` de
   `edge/src/bots.ts`); al pasarse vuelve a `/shop/foto?espera=1` con el aviso de la tienda, no con un texto suelto.
4. **Lectura** en el Worker de Juan, `POST /odoo/buscar-foto` con `JUAN_URL` y `JUAN_WORKER_TOKEN` (como las pantallas
   de Juan; Odoo espera **15 s** y el Worker contesta antes de 12). El Worker usa **el mismo lector** de las
   conversaciones (`juan/src/motor/vision.ts`, solo importado) y devuelve **solo el registro cerrado**: tipo, hasta 3
   códigos con patrón estricto, categoría y medida de una lista, ¿parece pago?, ¿parece identidad? Odoo lo vuelve a
   pasar por las listas cerradas, revisando el tipo de cada campo (una lista o un diccionario donde va un texto se
   descarta: nada mal formado revienta). Ningún texto libre de la imagen llega a la página: solo «Lo que vimos: Cama ·
   Queen» (etiquetas fijas) o «Lo encontramos por el código que se ve en tu foto».
5. **Comprobantes y cédulas no se buscan**: tipo comprobante o identidad, o cualquier señal de pago o de identidad
   (también si el modelo no la dice: lo prudente) → «Esa foto parece un documento; para buscar, sube la foto de un
   mueble». No se muestra nada parecido ni lo que se vio. Lo que no es un mueble → «No reconocimos un mueble en tu foto».
6. **Búsqueda, solo entre lo publicado** (`website._dcasa_dominio_publicado`): primero por el código leído (el código
   público `DC-…` o la referencia exacta, con la misma regla que `buscar_productos` de Juan; la referencia del
   proveedor nunca se muestra); si no hay código, por categoría y medida con las mismas palabras y la misma puntuación
   que la búsqueda de Juan («cama queen»; si con la medida no hay nada, «cama»; sofá también busca «sala»; clóset,
   «ropero» y «armario»). Hasta 12 productos. Sin nada: «No encontramos algo parecido en la tienda en línea».
7. Si no se puede leer (sin Worker, lectura de imágenes apagada, sin cupo de IA, caído o lento), si ya hay 3 a la vez o
   si se pasó un tope: «Ahora no podemos buscar por foto; búscalo por nombre o escríbenos por WhatsApp», con la caja de
   búsqueda por nombre a mano. Nunca un error de servidor.

**La foto nunca se guarda**: ni en Odoo (ningún modelo, adjunto, sesión ni mensaje), ni en R2, ni en los registros
(logs) de Odoo o del Worker, ni en el Worker (que solo anota el gasto: tokens y dólares). Las pruebas lo verifican
buscando la foto (y una marca que trae adentro) en todas las columnas de la base, en la sesión y en el registro
(`dcasa_buscar_foto/tests/test_buscar_foto.py`, `juan/test/odoo-panel-buscar-foto.test.ts`).

**Costo: un techo propio, aparte de Meta.** La lectura la cobra **Cloudflare** (Workers AI,
`@cf/meta/llama-4-scout-17b-16e-instruct`, US$0,27 por millón de tokens de entrada y US$0,85 de salida, leído el
2026-11-13; integrado en `juan/src/motor/precios.ts` porque `precios_ia` de Odoo solo trae los modelos de la
conversación; si Workers AI no dice los tokens, se anota una estimación alta). Por eso:

* Se anota en el Worker como `cloudflare:lector-de-fotos`, **fuera** del gasto de Juan: no suma en su tope del mes, en
  «Por pagar a Meta», en el botón «Pagar», en la diferencia con lo que cobró Meta ni en las «respuestas». *Conversaciones
  › Costos de IA* lo muestra en su propio renglón, «Cloudflare: lector de fotos», con cuántas fotos. (El lector de
  imágenes de los chats no anota gasto, desde antes: nunca ensució el saldo con Meta. Si algún día lo anota, cualquier
  `@cf/…` cae en la misma cuenta aparte.)
* **Techo del mes de la foto**: *Sitio web › Busca con una foto › Gasto de IA de la foto en el mes*, **5 USD de
  fábrica** (0 = no se leen fotos). Lo aplica el Worker (Odoo se lo manda en cada búsqueda, `tope_mes_usd`).
* **Nunca le quita IA a las conversaciones**: con el gasto del mes de Juan por encima del **80 %** de su tope, no se lee
  ninguna foto.
* En los dos casos: «Ahora no podemos buscar por foto». La pantalla cuenta cuántas no se pudieron leer.

**Privacidad.** `/privacidad` gana el párrafo «Busca con una foto» (sección de inteligencia artificial, ancla
`#busca-con-una-foto`) y su fecha de actualización. Lo que se publica no lleva marcas de borrador; **antes de desplegar,
lo aprueba la dueña** (y el abogado si ella quiere): es un texto propuesto hasta entonces.

**Lo que no hace (todavía).** No afina por color ni estilo: el lector no los devuelve. Se puede sumar como dos
enumeraciones cerradas más en `vision.ts` (por ejemplo `color` ∈ blanco, negro, gris, beige, café, madera… y `estilo`)
que `normalizarLectura` deja pasar o pone en `null`; Juan no cambia porque `conversacion.ts` solo lee códigos, categoría
y medida, y aquí se sumaría la palabra del color a la búsqueda («cama queen gris»). Se dejó para después del cambio de
`vision.ts` que está en curso (qué cuenta como comprobante), para no pisarlo. Tampoco manda `Search` al píxel de Meta
(ver `docs/META_EVENTOS.md`).

**Brian:** no lleva herramienta: es una función de la tienda para el cliente, su único ajuste es un interruptor con
topes que Gerencia cambia en una pantalla, y cuántas búsquedas hubo (y su costo) ya se ve ahí y en Costos de IA.

**Pruebas:** `dcasa_buscar_foto/tests/` (la ruta con el Worker simulado, la cámara en cada caja, con el editor del
sitio abierto, los topes, el semáforo, el interruptor, la limpieza, las funciones puras y `test_revision_rvf.py`, las de
la revisión adversarial, con la caja de `/shop` medida en Chrome a 360, 390 y 430 px), `dcasa_base/tests/test_red.py`
(la llave de la conexión), `scripts/revision_rvf_carrera_foto.py` (las carreras), `juan/test/odoo-panel-buscar-foto.test.ts`
y `juan/test/revision-rvf-*.test.ts` (el punto de entrada, el techo y la reserva del 80 %), `juan/test/motor/global.test.ts`
(lo de Cloudflare aparte) y `edge/test/buscar-foto.test.ts`, `edge/test/revision-rvf-buscar-foto.test.ts` (el freno de
ráfagas por /64 y que nada de esto se guarde en la caché del borde).

## La tienda en línea: buscar, la ficha y lo que Google no muestra

Lote 1 de la web, aprobado por la dueña el 2026-11-13 («Sí, arranca el lote 1»). Capturas de antes y después (Odoo
local con datos de prueba, 1366 y 390 px) para su visto bueno antes de producción.

* **Buscar.** La lupa de la cabecera abre una caja que busca **en el catálogo** (`/shop?search=…`): los resultados se
  ven como la tienda (fotos grandes, precio con «+ ITBMS» y el mismo botón de agregar). La lista que sale mientras se
  escribe se queda, solo con productos. En el **celular la lupa está a la vista, junto al carrito** (antes la búsqueda
  estaba escondida dentro del menú), con 44 px de área táctil, y abre la misma caja. La búsqueda vieja de Odoo
  (`/website/search`, una lista con fotos chiquitas) lleva al catálogo con lo que se buscó.
  `website_dcasa/views/buscador_templates.xml`, `controllers/main.py` (`BuscadorDcasa`).
* **La barra de búsqueda de `/shop` en el celular** va sola en su fila, a lo ancho, con el mismo texto de ayuda
  («Busca un mueble», más corto para que no se corte en el cajón del celular; en una categoría, el «Buscar en …» de Odoo); «Ordenar por» y «Filtros» quedan en la fila
  de abajo. Antes las tres iban en una fila y la caja quedaba de ~125 px: no se leía el texto de ayuda ni cabía un
  botón más dentro (la cámara de «Busca con una foto»). En la computadora no cambia.
* **Una tilde no es otra búsqueda.** Odoo, cuando no hallaba la palabra exacta, buscaba la más parecida y avisaba «Su
  búsqueda "sofa" no coincidió con nada. Se muestran los resultados para "sofá"». Si la diferencia es solo de tildes o
  mayúsculas, ahora salen los resultados sin ese aviso (en el catálogo, en la lista mientras se escribe y en la búsqueda
  general). Si de verdad es otra palabra, el aviso queda en tuteo: «No encontramos "sofas". Te mostramos lo que hay de
  "sofá"». `website_dcasa/models/buscador.py` (`_search_with_fuzzy`).
* **Sin resultados:** «No encontramos "…"», las categorías de «Compra por espacio» que tienen algo publicado y
  **«Escríbenos por WhatsApp»** con lo que buscó ya escrito («Hola D'CASA, busco: …»). Sin el rango de precio de
  «$ 0.00» de Odoo. Escribir sin nada y dar Enter lleva al catálogo entero.
* **`/catalogo` y `/tienda`** llevan al catálogo con un 301 (lo que venga después del «?», como una búsqueda o una
  campaña, se conserva).
* **Carrito vacío** en la voz de la marca: «Tu carrito está vacío», «Mira el catálogo y agrega lo que te guste», los
  botones **«Ver el catálogo»** y «Escríbenos por WhatsApp» (el botón flotante no sale en el carrito). «Reordenado
  rápido» (traducción de Odoo) no se le muestra a quien no tiene cuenta; con cuenta se llama **«Volver a pedir»**. El
  botón sigue en la página aunque no se vea: el JavaScript del carrito de Odoo lo usa al cambiar cantidades.
* **La foto de la ficha en grande.** Es el visor de Odoo («Zoom al hacer clic», que el módulo deja siempre encendido):
  se abre al tocar la foto o la **lupa redonda** que ahora está sobre la foto. Con el dedo: un toque acerca (2,5 veces;
  el de Odoo acercaba poco, pensado para el ratón) y otro la deja como estaba, **dos dedos acercan** (hasta 4 veces) y,
  ya acercada, **un dedo la mueve**. La X para cerrar es un círculo navy de 44 px que se ve también sobre una foto
  blanca. `website_dcasa/static/src/js/foto_grande.js`.
* **Disponibilidad en la ficha:** «Disponible», «Quedan pocas» o «Agotado», **nunca el número**, en la misma línea del
  precio, a la derecha de «+ ITBMS» (si no cabe, baja justo debajo). En el celular se ve al abrir la ficha, sin bajar y
  sin que la tape la barra fija de «Agregar al carrito»: para eso la ficha tiene menos aire arriba de la foto y entre
  la foto, el nombre y el precio, y a 360 px la barra fija va en una sola fila (sin el ícono del carrito). Medido con
  un nombre de tres líneas y foto cuadrada en 360×800, 390×844 y 430×932
  (`dcasa_catalogo/tests/test_disponibilidad_celular.py`); en una pantalla más baja (360×740) un nombre de tres
  líneas deja la etiqueta unos 20 px debajo de la barra.
  * Es **la misma regla que usa Juan**, y vive en un solo lugar: `dcasa_base/disponibilidad.py`
    (`etiqueta_existencias`: agotado con 0 o menos; «pocas» de 1 al umbral del producto, 5 si no se cambió;
    disponible si hay más o si el producto no controla inventario). Juan, el catálogo de Meta (`nivel_existencias`) y
    el Escáner (`dcasa_barras`) la importan de ahí; antes cada uno tenía su copia.
  * Las unidades que cuentan son las **libres** (en existencia menos lo reservado) de la medida elegida, o de todas si
    no hay medida: `product.template._dcasa_disponibilidad` (`dcasa_catalogo/models/product.py`), el mismo método que
    usa Juan (`_j_existencias`). Al cambiar de medida en la ficha, la etiqueta cambia sola
    (`dcasa_catalogo/static/src/js/disponibilidad.js`).
  * **Comprar o no comprar no cambia:** un producto «Agotado» que la tienda deja vender (existencias sin confirmar,
    `allow_out_of_stock_order`) se sigue pudiendo agregar al carrito. Los mensajes de Odoo «N en existencia» (daría el
    número) y su «Agotado» genérico (repetiría la etiqueta) no se muestran.
  * **La ficha guardada en el borde se refresca:** todo cambio de existencias (recepción, venta entregada, ajuste,
    reserva) deja la marca de `dcasa_tienda_borde` (`stock.quant`) y el borde da por viejas las páginas guardadas; y,
    además, al abrir la ficha Odoo vuelve a pedir la información de la combinación y la etiqueta se pinta con la de
    ese momento, aunque la página venga del borde.
  * Los datos para Google siguen **sin** disponibilidad (`PUBLICAR_DISPONIBILIDAD = False` en
    `website_dcasa/controllers/main.py`): eso es otra decisión.
* **Medidas:** ya existían como dato (`dcasa_medidas`, de `data/fichas.json`: las impresas en la foto del proveedor) y
  la ficha ya las mostraba. En la copia local de la base, 144 de los 229 productos publicados las tienen; **ninguno de
  los colchones** (tampoco el DR-1033): no se inventó ninguna.
* **Lo que Google no muestra:** `/web/login`, `/web/signup` y `/web/reset_password` llevan `noindex` (Google mostraba
  «Login - D'CASA Panamá» con el texto de la web vieja) y los resultados de búsqueda `noindex, follow`, en la cabecera
  `X-Robots-Tag` y en `<meta name="robots">`; ninguna está en el mapa del sitio y el borde no cambia esa cabecera
  ([OPERACION.md](OPERACION.md#tienda-rápida-caché-de-páginas-en-el-borde)). Los datos estructurados de la portada
  dicen **un solo logo** (`/web/image/website/1/logo`, el de la cabecera; antes también `/logo.png?company=1`).
* **Un sitio para botones extra en la caja de búsqueda** (hoy lo usa la cámara de «Busca con una foto»): la plantilla vacía
  `website_dcasa.buscador_botones_extra`, dentro de la caja, justo antes de la lupa de enviar. La llaman todas las cajas
  de búsqueda del sitio (la de la cabecera, la del menú del celular y la barra de `/shop`); quien agrega un botón la
  hereda con `position="inside"` y tiene a mano `search_type` («products» en la cabecera y en `/shop`), `action` y
  `search`. Va dentro de un `<span class="o_dcasa_buscador_extra">` que no dibuja caja (`display: contents`): sin él,
  con el editor del sitio abierto (quien puede editar el sitio) Odoo dejaba sus marcas de edición en el `t-call` y
  toda página con la cabecera daba error 500. Al heredar esta plantilla, el botón va **dentro** de ella, no con un
  `t-call` suelto metido por `xpath` en la caja de Odoo.

**Contrato visual:** la lupa cambia la cabecera del celular a propósito; las cinco referencias de 390 px
(`website_dcasa/tests/referencia/cabecera-*-390.webp`) se regeneraron con `scripts/actualizar_referencias_visuales.sh`.
Las de 1440 px y las del hero no cambiaron de diseño y quedan las de antes. El contrato de estilos no cambió.

Pruebas: `website_dcasa/tests/test_buscador.py` (reglas, Google, mapa del sitio, logo, /catalogo, búsqueda, tilde, sin
resultados, carrito, foto, sitio para botones), `test_buscador_movil.py` (en Chrome como teléfono a 360, 390 y 430 px:
la lupa junto al carrito sin romper la cabecera y los gestos del visor), `dcasa_catalogo/tests/test_disponibilidad_ficha.py`
y `dcasa_base/tests/test_disponibilidad.py`; en el borde, `edge/test/paginas.test.ts`.

## Visítanos: horario y mapa, y opiniones de los productos

Lote 2 de la web, aprobado por la dueña el 2026-11-13. Capturas (Odoo local con datos de prueba, 390 y 1366 px) para su
visto bueno antes de producción.

* **Horario en Visítanos.** Una tabla de días y horas («Lunes a sábado · 9:00 a. m. a 6:00 p. m.», «Domingo · 9:00 a. m.
  a 5:00 p. m.») y una franja corta en el pie de todas las páginas («Horario de la tienda»). Sale de **un solo
  lugar**: el horario de los **Ajustes de Juan** (`horario_inicio`, `horario_fin`, `horario_fin_domingo` y los días; el mismo que usa Juan).
  `website_dcasa` no depende de `dcasa_conversaciones`: deja el gancho `website._dcasa_horario_tienda()`
  (`website_dcasa/models/horario_tienda.py`, vacío = no se muestra nada, no se inventa) y `dcasa_conversaciones` lo
  llena (`models/horario_sitio.py`). Un día apagado sale «Cerrado»; un domingo sin hora propia se junta con la semana.
  **No hay feriados**: no se inventan. La migración `dcasa_conversaciones` 19.0.1.5.0 pone el horario que dio la dueña
  solo si los ajustes seguían con los de fábrica (8 a 17 todos los días); si alguien ya puso otro, no se toca. Ojo: es
  también el horario laboral de Juan (seguimientos, avisos y reparto se mueven con él). Al cambiarlo, el borde renueva
  las páginas ([OPERACION.md](OPERACION.md#tienda-rápida-caché-de-páginas-en-el-borde)).
  * **El constructor del sitio no lo congela.** El pie (`#footer`) es una zona que el constructor guarda: al salir del
    editor, Odoo escribe en la vista el HTML **ya dibujado** de esa zona (`ir.ui.view.save`), así que algo dinámico
    adentro quedaría como texto fijo y un cambio en los Ajustes de Juan ya no se vería (se comprobó con una prueba:
    pasaba). Por eso el horario va en su **propia franja, fuera de `#footer`** (vista `website_dcasa.pie_horario`,
    debajo de las columnas), y la franja, la tabla de Visítanos y el recuadro del mapa llevan `t-ignore="true"`: sin las
    marcas del editor, el constructor no los toca ni los guarda. El mapa, además, se quita solo al abrir el editor (se
    pone con `insert()` de la interacción), así que el `<iframe>` de Google nunca queda escrito en una vista.
  * **La caché de páginas de Odoo** (la portada y demás páginas del sitio, hasta 1 h para el visitante) incluye el
    horario en su llave (`website_dcasa/models/website_page.py`): al cambiarlo, Odoo dibuja la página de nuevo.
* **El mapa de Google solo con permiso.** Visítanos ya no carga el `<iframe>` de Google al abrir (Google guarda cookies).
  Trae un recuadro «El mapa es de Google y puede guardar cookies en tu navegador» con **«Ver el mapa»**. El mapa se carga
  solo si quien visita ya aceptó las cookies opcionales en el aviso del sitio (la cookie `website_cookies_bar` con
  `optional: true`, lo mismo que mira el píxel de Meta en `dcasa_meta_eventos`), si las acepta después en el aviso o si
  toca el botón. La decisión la toma el navegador (`website_dcasa/static/src/js/mapa.js`) porque la página la guarda el
  borde y es la misma para todos. «Abrir la ruta en Google Maps» (con `LATITUD` y `LONGITUD`) sigue igual.
* **Opiniones de los productos: reales y aprobadas.** Modelo propio pequeño, `dcasa.resena`
  (`website_dcasa/models/resena.py`); las calificaciones de Odoo («Discusión y valoración») siguen apagadas.
  * **Quién opina:** el cliente con sesión en **Mi cuenta › Tus opiniones** (`/mi-cuenta/opiniones`), solo de un producto
    que está en una factura suya publicada y **pagada por completo** (`payment_state` «paid» o «in_payment»; un abono a
    medias no), que se ve en la tienda y que no sea un servicio (el flete). Una opinión por cliente y producto. Estrellas
    de 1 a 5 y texto opcional de hasta 1,000 letras. El anónimo no opina; quien no compró, tampoco.
  * **Invitación:** en el correo de la factura **pagada por completo** (`dcasa_correo`, plantilla `plantilla_factura`,
    rama «pagada»): «¿Qué tal tu compra? Cuéntanos en Mi cuenta › Tus opiniones», solo si de esa factura le queda algo
    por opinar. Nunca en el correo de un abono. Además, Mi cuenta lo ofrece en el Inicio («¿Qué tal tu compra?») y en
    Compras.
  * **Aprobar:** **Ventas › Hoy › Opiniones por aprobar** (Gerencia y administradores; en la Guía, «Publicar las
    opiniones que dejaron los clientes»): «Publicar» o «No publicar». Nadie las crea ni cambia lo que dijo el cliente.
  * **En la ficha:** debajo del código público, las estrellas con el promedio y cuántas («4.5 · 2 opiniones»), que
    llevan a la sección «Opiniones de quienes lo compraron» (primer nombre e inicial del apellido, estrellas, mes y
    texto; hasta 20, de la más reciente). Solo las publicadas: **cero publicadas = no sale nada**.
  * **Google:** `aggregateRating` (promedio, cuántas, de 1 a 5) en los datos de la ficha solo con las publicadas; sin
    ninguna, no va. Se quita siempre el de Odoo.
  * **El borde:** publicar, esconder o borrar una publicada renueva esa ficha.

Pruebas: `website_dcasa/tests/test_visitanos.py` (horario, pie, el mapa en Chrome sin permiso, con «Solo las
necesarias», al tocar, con cookies aceptadas y al aceptar el aviso: sin permiso el navegador no le pide nada a Google),
`dcasa_conversaciones/tests/test_horario_sitio.py`, `website_dcasa/tests/test_resenas.py` (quién opina, permisos: un
portal que no compró no opina, un portal o una vendedora no aprueban, lo no aprobado no se ve; ficha y
`aggregateRating`), `dcasa_mi_cuenta/tests/test_opiniones.py` (el formulario como el navegador, con cuenta y con PIN) y
`dcasa_correo/tests/test_opinar.py` (la invitación).
