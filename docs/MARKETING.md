# Marketing y fotos de productos (`dcasa_marketing`)

Pedido de la dueña (2026-10-22):

> «Un problema terrible es poder ver la foto de un producto: si se pasa el mouse por encima de una imagen se agranda un
> poco pero sigue siendo muy pequeña; al hacer clic en ella debería poderse ver, editar, recortar o reemplazar con mucha
> facilidad.» · «El agregar las fotos, ver las imágenes es muy poco intuitivo y limitado.» · «Créame un botón de
> Marketing: los productos por categoría con mayor y menor stock, los más vendidos, y poder ver en la semana, 15 días o
> el mes los productos con mayor movimiento y los más quietos; allí mismo un apartado para buscar fácil un producto y
> subirle sus fotos de forma fácil y rápida y poder ordenarlas.»

## Para la dueña (en corto)

**Ver una foto en grande.** Toca la foto del producto (en la ficha, en la lista o en las tarjetas de Productos, y en el
Escáner). Se abre casi a pantalla completa. Pasas a las otras fotos con las flechas, deslizando el dedo o con las teclas
← →; la acercas pellizcando (celular), con la rueda del mouse, con doble toque o con los botones de la lupa.

**Cambiarla** (si puedes editar el producto): abajo están **Reemplazar** (elegir un archivo; en el celular también
**Tomar otra** con la cámara), **Recortar** (libre, cuadrada, horizontal o vertical), **Girar**, **Hacer principal**,
**Quitar** (pregunta antes) y **Descargar**. Quien no puede editar el producto solo ve y descarga.

**Subir varias y ordenarlas.** En esa misma ventana toca **Todas**: ves todas las fotos grandes; **Elegir fotos** deja
marcar varias de una vez (en la computadora también puedes arrastrarlas desde una carpeta). La primera es la principal:
ordénalas arrastrando (en el celular, deja el dedo un momento sobre la foto y muévela) o con las flechitas de cada foto.
En la pestaña **Ventas** del producto está el mismo acceso: **Fotos del producto**.

**Marketing** (app propia y acceso en el Inicio; es de Gerencia). Arriba eliges **Semana**, **15 días** o **Mes** y, si
quieres, una **categoría**; todo se filtra con eso:

- **Stock**: los que más y los que menos tienen (los agotados se cuentan aparte: no se pueden empujar).
- **Más vendidos**: unidades vendidas en el periodo.
- **Mayor movimiento**: lo que más se vendió o salió de la bodega.
- **Más quietos**: con stock y sin ventas ni salidas en el periodo; primero los que nunca se vendieron y los que llevan
  más tiempo sin venderse. «Ver los N en Productos» abre la lista completa.
- **Fotos**: busca el producto por nombre, código o código de barras (el lector también sirve: si sale uno solo, se abre
  solo) y súbele sus fotos ahí mismo. Se marcan los que no tienen foto y los que tienen una sola.
- **Lista para campañas**: abre la lista de Productos que ya ordena por stock, precio y categoría.

## Cómo se cuenta cada cifra

Nada se estima ni se inventa: todo sale de la base (`addons/dcasa_marketing/models/marketing.py`).

| Sección | Qué cuenta |
|---|---|
| Periodo | Semana, 15 días y Mes son los **últimos 7, 15 y 30 días corridos**, hoy incluido (hora de Panamá). Corridos, no «desde el lunes» o «desde el día 1»: así lo quieto no depende del día del mes en que se mira. |
| Categoría | El **tipo**, el mismo de «Unidades vendidas por tipo» del Inicio: la categoría de primer nivel bajo la raíz (`Muebles / Salas / …` → «Salas»; una raíz sin padre, como «Colchones y box», es su propio tipo). Los productos sin categoría salen juntos en «Sin categoría». |
| Productos que entran | Activos, a la venta y que no son servicios (el flete no cuenta). |
| Más / menos stock | `dcasa_stock` (el «A la mano» guardado en el producto, de dcasa_catalogo). «Menos stock» deja fuera lo agotado, igual que el favorito «Menor stock primero». Hasta 8 por lista; con pocos productos cada uno sale en una sola (la mitad de arriba y la de abajo). |
| Más vendidos | Unidades de las **facturas de cliente publicadas** del periodo, la misma base con la que abre el Inicio de Gerencia («Facturado», `BASE_POR_DEFECTO`): las notas de crédito restan; sin servicios ni anticipos (`dcasa.tablero._filas` y `_unidades_por_producto`). |
| Mayor movimiento | Vendidas (lo de arriba) y **entregadas**: salidas hechas de una ubicación interna a clientes, menos lo que los clientes devolvieron. Una venta que se factura y se entrega cuenta **una vez**: el movimiento es lo mayor de las dos cifras, no la suma. |
| Más quietos | Con stock (`dcasa_stock > 0`) y **sin ventas ni entregas** en el periodo. Orden: primero los que nunca tuvieron una factura en Odoo, luego los de última venta más vieja; a igualdad, el de más stock. |
| Fotos | «Sin foto» = sin foto principal; «Una sola» = con principal y sin ninguna foto extra. No hay una cifra de «pocas» inventada: se dice cuántas tiene cada uno. |

## Las fotos por dentro

`addons/dcasa_marketing/models/fotos.py` (métodos `dcasa_fotos*` de `product.template`):

- **Cuáles son.** La principal es `image_1920` del producto (ficha, listas, cotizaciones, tienda). Las demás son las
  «Imágenes extra» de la tienda (`product_template_image_ids`, el `product.image` de website_sale, por su `sequence`).
  La pantalla las trata como una fila: la primera es la principal. Los videos de la tienda no son fotos: no salen ni se
  tocan, y quedan al final.
- **Ordenar** cambia el `sequence` de las extra; solo si cambia la principal se intercambian dos fotos (la elegida pasa
  al producto y la vieja ocupa su lugar). **Quitar la principal** sube la siguiente.
- **Calidad.** Se guarda el archivo que sube la persona; Odoo lo deja en 1920 px como máximo y saca los tamaños chicos.
  **Girar y recortar se hacen en el servidor** sobre la foto guardada más grande, con la orientación de la cámara ya
  aplicada (la misma que ve el navegador), y se guardan en su mismo formato (JPEG a calidad 95, como Odoo; PNG sin
  pérdida); el navegador solo manda el rectángulo. El recortador es el **Cropper.js que ya trae Odoo**
  (`html_editor.assets_image_cropper`).
- **Límites técnicos** (no del negocio): JPG, PNG, WebP o GIF; hasta 25 MB y 50 megapíxeles por foto; 10 por llamada (la
  pantalla las sube de a una, con su avance). Una foto HEIC del iPhone elegida en la computadora se rechaza con un aviso
  (el celular la convierte solo a JPG).
- **Adjuntos en R2:** las fotos son adjuntos como siempre (`dcasa_adjuntos_r2`); la tienda las sirve por `/dcasa/img`
  (website_dcasa), que se renueva sola cuando cambia el contenido.

La pantalla (`static/src/js/fotos_dialogo.js`) es una ventana de Odoo de tamaño completo con tres modos (Ver, Todas,
Recortar); la foto que se toca es el widget `dcasa_foto_producto` (ficha, lista y tarjetas de `product.template`), el
botón de la pestaña Ventas es el widget `dcasa_galeria_fotos`, y el Escáner se parcha para abrirla
(`escaner_fotos.js`). Ordenar arrastrando usa `useSortable` de Odoo (en el celular, con un toque largo).

## Permisos

- **Ver** las fotos en grande y descargarlas: cualquier usuario interno que vea el producto.
- **Cambiarlas**: quien puede **editar ese producto** (`has_access('write')` en `product.template`, comprobado en el
  servidor en cada método antes de cualquier `sudo`): hoy Gerencia, administradores y la Vendedora. Las extra se
  escriben con `sudo` después de esa comprobación, porque Odoo solo deja escribir `product.image` a Ventas
  administrador y a los editores del sitio. Quien solo ve productos (p. ej. bodega sin Ventas) recibe `AccessError`
  aunque llame a mano. La regla está en un solo lugar: `_dcasa_exigir_editar_fotos`.
- **Marketing**: Ventas administrador (Gerencia) y administradores, igual que Estadísticas (son las ventas de toda la
  tienda). El servidor lo exige (`dcasa.marketing._exigir`); el menú y el acceso del Inicio usan los mismos grupos. No
  existe un rol «Marketing»: si se crea, se agrega a `GRUPOS` en `marketing.py` y al menú.
- Lista blanca RPC: las 11 entradas de `dcasa_marketing` en `dcasa_base/tests/test_superficie_rpc.py`.

## Brian

`movimiento_de_productos` (Gerencia y administradores) y `fotos_que_faltan` (interno), con las mismas cifras de la
pantalla. Detalle y ejemplos en [BRIAN.md](BRIAN.md) › «Marketing y fotos».

## Pruebas

- `tests/test_fotos.py`: subir varias (la primera es la principal), reemplazar, ordenar (con y sin cambio de principal),
  principal, quitar, girar y recortar en el servidor (también con la orientación EXIF del celular), formatos y tamaños,
  videos al final, claves de otro producto, y quién puede cambiar las fotos (Vendedora sí; bodega solo ve; portal nada).
- `tests/test_marketing.py`: periodos, más vendidos (con nota de crédito), movimiento (vendido y entregado cuentan una
  vez; devoluciones), quietos (orden por última venta), stock por categoría (sin agotados), subcategorías como tipos,
  «Sin categoría», fotos que faltan y búsqueda (nombre, código, código de barras, código público), permisos, el acceso
  del Inicio y las dos herramientas de Brian.
- `tests/test_navegador.py` (390×844 y 1440×900): visor (zoom con botón, pellizco y doble toque; flecha y deslizar),
  reemplazar, girar, recortar, principal, galería (subir varias, ordenar con flechas y arrastrando, quitar con
  confirmación), la ficha con la foto nueva al cerrar, sin scroll de costado; quien solo ve; la foto de la lista y del
  Escáner; Marketing (secciones, periodo, categoría, buscar por código, Enter abre la galería y subir).

## Lo que no hace (todavía)

- No hay un rol «Marketing»: lo ven Gerencia y administradores.
- Brian lee Marketing y las fotos que faltan, pero no sube ni cambia fotos (eso se hace en la pantalla).
- Las fotos propias de una variante (un color con su foto) se siguen cambiando en la variante, como en Odoo; el visor
  muestra las del producto.
