# Catálogo real

De dónde sale lo que se vende en Odoo (inventario, ventas y tienda web: es el mismo producto).

## Fuentes

- `up media/DCASA_listado_productos.xlsx`, hoja «Productos»: código, nombre, precio
  **sin ITBMS** («+ITBMS»), precios por tamaño, combo/el par, existencias y observaciones.
- `up media/*.png`: fotos originales. **El nombre es el código**: `CODIGO.png` o
  `CODIGO_1.png`, `CODIGO_2.png`… (varias fotos del mismo producto). Una `/` del código
  se escribe `-` en el archivo. No van en la imagen Docker (`.dockerignore`).

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

Con un Excel o fotos nuevas: `python scripts/importar_catalogo.py` (necesita `openpyxl` y
`Pillow`), commit, y en la base `odoo-bin shell` →
`from odoo.addons.dcasa_catalogo.catalogo import cargar_catalogo; cargar_catalogo(env); env.cr.commit()`.
Solo crea los códigos que falten: lo que se cambió en Odoo (precios, fotos, textos) no se pisa.

## Regla de precios: todo termina en .99

Decisión de la dueña (2026-10-02): **todo precio termina en .99**. Se conserva la parte entera
y los centavos pasan a .99: 318.66 → 318.99, 439.98 → 439.99, 186.64 → 186.99; 129.99 queda
igual. Vale para el precio del producto y para los de combo, siempre **sin ITBMS**.
Código: `reglas.precio_terminado_en_99` (con tests en `tests/test_pedido_ltsc07.py`).

## Pedidos nuevos cargados como la mercancía inicial (LTSC-07)

El pedido LTSC-07 (`up media/Catalogo_LTSC-07_Precios_PRODUCTOS_NUEVOS.xlsm`, hoja «Catálogo
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
- **Fotos** (`up media/`, las que no son de la carga inicial; .jpg/.png/.webp), en este orden
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
