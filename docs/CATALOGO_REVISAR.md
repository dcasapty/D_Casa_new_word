# Catálogo: lo que hay que revisar

Generado por `scripts/importar_catalogo.py` a partir de `up media/DCASA_listado_productos.xlsx`.
Nada de esto se adivinó: donde el Excel duda, se tomó la primera ficha y se anota aquí.

- Productos importados: **199** (16 con tamaños como variantes).
- Fotos optimizadas: **323**.
- Existencias: el Excel dice «Sin confirmar» en todos; el inventario arranca en 0 y la web deja comprar igual (se confirma por WhatsApp).

## Precios y fichas en duda

- `SHUQ090405` (Mesa de noche): el Excel trae dos precios, $17.99 y $19.99. Se usó el primero.
- `SHUQ090403` (Mesa de noche): el Excel trae dos precios, $17.99 y $19.99. Se usó el primero.
- `ZQ093403` (Mesa de noche): el Excel trae dos precios, $24.99 y $29.99. Se usó el primero.
- `LXI090407` (Mesa de noche): el Excel trae dos precios, $19.99 y $24.99. Se usó el primero.
- `HYI220725` (Estante de cocina): el Excel trae dos precios, $39.99 y $45.99. Se usó el primero.
- `ZEM-KING` (Cama con baúl): Precio queen mayor que king: revisar.
- `XHT022-F-W` (Cama de felpa): un tamaño viene sin precio y no se creó.
- `81904` (Cama queen): Precio king menor que queen: revisar.

## Sin foto (en inventario, no publicados en la web)

- `ZJ074301` (Mueble de TV)
- `YPN272105` (Estante)
- `YPN272106` (Estante)
- `HYI360745` (Estante Pine)
- `HYI360747` (Estante Pine)
- `HYI360748` (Estante Pine)
- `ZQ130107` (Organizador)
- `CZX100311` (Estante type madera)
- `QH221813` (Estante de cocina)
- `YOYU060107` (Gavetero)
- `XLB271206` (Librero)

## Las fotos muestran otro tipo de mueble que el nombre del Excel

- `A1721G52006041` (cama alta (loft) con escritorio debajo, no camarote de dos camas)
- `JW017509` (escritorio con librero)
- `butterfly-bed-up-bed` (diván (daybed) de metal)
- `up001` (cama tapizada (no se ve estructura de metal))

Nombres web y medidas: `addons/dcasa_catalogo/data/fichas.json` (revisadas foto por foto; las medidas solo cuando están impresas en la foto).
## Decisiones de la dueña (30/09/2026)

- Precios dudosos (dos precios por código): quedan como están (se usa el primero).
- Fotos idénticas en códigos distintos (CHCH070202/203, HYI360702/726, YH1003Fb/FDG, ZQ063605/606): quedan como están.
- Reseñas de Google: quedan como están.
