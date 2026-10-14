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

Un combo junta la cama y el colchón en **un solo producto con un solo precio**. Es el tipo **Combo** que ya trae Odoo
(no se instala nada). Los combos de la web siguen con su línea «Combo con colchón … + ITBMS» de arriba: esto es para
**vender** el combo en una cotización, una entrega y una factura.

**Crear o cambiar uno a mano** (también está en la Guía: «Crear o cambiar un combo de cama y colchón»):

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
[MIGRACION.md › Combos de cama y colchón](MIGRACION.md#combos-de-cama-y-colchón).

## Códigos de barras

Los productos del catálogo no traen código de barras (los muebles de proveedor casi nunca lo tienen). Se asignan con las
etiquetas numeradas de un rollo, desde Inventario › Escáner › Asignar; el Escáner también encuentra un producto por su
referencia interna. Todo está en [BARRAS.md](BARRAS.md).
