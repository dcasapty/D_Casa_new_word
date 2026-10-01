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
