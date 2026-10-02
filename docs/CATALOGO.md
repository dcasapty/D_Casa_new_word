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
