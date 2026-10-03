# Inventario del sistema anterior — informe de carga

Fuente: 7 capturas de Inventario → Productos del Odoo anterior (`up media/inventario-anterior/`),
transcritas a `inventario_anterior.csv` con dos lecturas independientes por captura (idénticas en
las 535 filas). Suma de «a la mano» por página: 565 · 490 · 627 · 125 · 806 · 832 · 664
(coincide con el LEEME).

La carga la hace `dcasa_catalogo` (migración 19.0.1.7.0 y alta de base nueva) con
`cargar_inventario_anterior`; este informe sale de las mismas reglas (`reglas.planificar_inventario`)
cruzadas con `data/catalogo.json` y las fotos de `static/img/productos`.

## Resumen

| Grupo | Filas |
| --- | ---: |
| Filas transcritas | 535 |
| No se importan (Descuento, Propinas, «X COLCHÓN … PARA COMBO») | 4 |
| Código repetido en el CSV (solo entra la primera aparición) | 1 |
| Ya estaban en el catálogo → se actualizan existencias, costo y precio | 147 |
| Productos nuevos | 383 |
| · de ellos, combos «… + COLCHÓN» (sin publicar) | 49 |
| · con foto (publicados en la web) | 6 |
| · sin foto (en inventario, sin publicar; lista en el Excel) | 328 |
| Existencias negativas → entran en 0, para conteo físico | 7 |
| Unidades que entran al almacén | 4129 |
| Dudas de lectura anotadas en el CSV | 11 |

## Existencias negativas (entran en 0; conteo físico pendiente)

- `N-F10018-F-BK` BOX SPRING DE METAL SENCILLO TAMAÑO FULL / N-F10018-F-BK — a la mano -3
- `PB43-F` CAMA FULL COLOR BLACK WITH FLOWER PATERN — a la mano -1
- `YMO-003` CAMA FULL DE METAL COLOR NEGRO — a la mano -5
- `BBCA SKU # 15621925` CAMA QUEEN COLOR GREY BBCA BBCA SKU # 15621925 — a la mano -2
- `DS090208` MESA DE NOCHE MORANDI PINE+ WHITE, 2 GAVETAS 32 CM. DS090208 — a la mano -1
- `CHCH070201` MUEBLE DE TV NORDIC MAPLE CON PUERTA LATERAL 120cm CHCH070201 — a la mano -1
- `YOYU020303` MUEBLE ZAPATERA 103X121.5X17 YOYU020303 — a la mano -7

El LEEME hablaba de 8 negativos; en las dos lecturas salen 7 y las sumas por
página cuadran con las capturas, así que el octavo seguramente era un conteo a ojo. Queda anotado
como duda para la dueña.

## Combos «… + COLCHÓN» (productos sin publicar, costo 0 en el sistema anterior)

- `(sin código)` COMBO BOX SPRING DE METAL SENCILLO TAMAÑO FULL / N-F10018-F-BK + COLCHON IMPERIAL
- `(sin código)` COMBO CAMA BUTTERFLY BLACK KING + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA BUTTERFLY UP TWIN + COLCHO IMPERIAL
- `(sin código)` COMBO CAMA BUTTERFLY WHITE KING + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA FELPA FULL BEIGE XHT022-F-BG + COLCHÓN IMPERIAL
- `(sin código)` COMBO CAMA FELPA FULL WHITE XHT022-F-W + COLCHÓN IMPERIAL
- `(sin código)` COMBO CAMA FELPA KING WHITE XHT022-K-W + COLCHÓN FIRST
- `(sin código)` COMBO CAMA FELPA QUEEN WHITE XHT022-Q-W + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA FELPA TWIN BEIGE XHT022-T-BG + COLCHÓN IMPERIAL
- `(sin código)` COMBO CAMA FELPA TWIN WHITE XHT022-T-W + COLCHÓN IMPERIAL
- `(sin código)` COMBO CAMA FULL COLOR GREY 2071 / J02HF-BF-2208GF + COLCHON BUEN SUEÑO
- `(sin código)` COMBO CAMA FULL CON ESTANTES 1062010734N + COLCHON IMPERIAL
- `(sin código)` COMBO CAMA FULL CON ESTANTES 1062010751N + COLCHON IMPERIAL
- `(sin código)` COMBO CAMA FULL WHITE HY013-F-WH + COLCHÓN IMPERIAL
- `(sin código)` COMBO CAMA KING COLOR BEIGE 81904-6002 + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR BEIGE BBCA BBCA SKU # 15621914 + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR BEIGE LTSC-01-2806-K-BE + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR BEIGE LTSC-01-6877-K-BE + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR BLAK LTSC-01-2806-K-BL + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR BLAK LTSC-01-6877 K BL + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR BROWN N-F12002-K-BR +COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR DARK GREY 1030934-3 + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR GREY BBCA SKU # 15621926 + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR GREY N-F12002-K-GR + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR LIGHT GREY 1030934-12 + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR LIGHT GREY LTSC-01-2806-K-LG + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR LIGHT GREY LTSC-01-6877-K-LG + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR STONE BBCA BBCA SKU # 15621920 + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING COLOR STONE BBCA SKU # 15621922 + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING CON ESTANTES 1062010753-54N + COLCHON IMPERIAL
- `(sin código)` COMBO CAMA KING DARK GREY 8017-1003-K DG + COLCHÓN FIRST CLASS
- `(sin código)` COMBO CAMA KING GREY CON ESTANTES 1062010736N Y 37N + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA KING IVORY 8017-1003-K IV + COLCHÓN FIRST CLASS
- `(sin código)` COMBO CAMA KING LIGHT GREY 8017-1003-K LG +COLCHÓN FIRST CLASS
- `(sin código)` COMBO CAMA KING WHITE CON ESTANTES 1062010732N Y 33N + COLCHON FIRST CLASS
- `(sin código)` COMBO CAMA QUEEN BLACK / Y0300300 + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA QUEEN BROWN CON ESTANTES 1062010752N + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA QUEEN COLOR BEIGE 1030934-5 + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA QUEEN COLOR BEIGE BBCA BBCA SKU # 15621928 + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA QUEEN COLOR BEIGE BBCA SKU # 15621907 + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA QUEEN COLOR GREY BBCA BBCA SKU # 15621925 + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA QUEEN COLOR GREY BBCA SKU # 15621924 + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA QUEEN COLOR LIGHT GREY 1030934-11 + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA QUEEN COLOR STONE BBCA SKU # 15621930 + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA QUEEN GREY CON ESTANTES 1062010735N + COLCHON DULCES SUEÑOS
- `(sin código)` COMBO CAMA QUEEN IVORY 8017-1002-Q + COLCHÓN DULCES SUEÑOS
- `C-W160969417` COMBO CAMA QUEEN W160969417 + COLCHÓN DULCES SUEÑOS
- `(sin código)` COMBO CAMA TWIN WHITE BF039-T-WH + COLCHÓN IMPERIAL
- `(sin código)` COMBO CAMAROTE TRIPLE 3 TWIN W160969418 + 3 COLCHONES IMPERIAL

## Precios del catálogo actual que cambia el inventario (23)

El inventario anterior manda sobre el precio de los códigos que trae (regla de la dueña). Estos
productos ya estaban en el catálogo con otro precio; si alguno debe quedarse con el del catálogo
(por ejemplo los del pedido LTSC-07, que se fijaron terminados en .99), la dueña lo cambia en Odoo.

- `YPN272102` BIBLIOTECA 5 REPISAS YPN272102: catálogo $69.99 → inventario $77.99
- `ZJ261301` BIBLIOTECA 80X24X179 ZJ261301: catálogo $59.99 → inventario $55.99
- `Y0300200` CAMA QUEEN LIGHT GREY / Y0300200: catálogo $129.99 → inventario $159.99
- `Y0300400` CAMA QUEEN SIZE LINEAS EN V CON LUCES LED Y ENCHUFE COLOR BROWN / Y0300400: catálogo $129.99 → inventario $160.64
- `Y0200101` CAMA SIZE FULL FRAME WITH DRAWER WITH CHARGE AND LIG BROWN LEATHER / Y0200101: catálogo $119.99 → inventario $179.99
- `A1721G52006041` CAMAROTE FULL 8071F: catálogo $159.99 → inventario $169.99
- `XLB0118616` ESCRITORIO DE ESQUINA 140X80X75 XLB0118616: catálogo $59.99 → inventario $49.99
- `LXI090402` MESA DE NOCHE PURE WARM WHITE, 2 GAVETAS 36X34 CM. LXI090402: catálogo $21.99 → inventario $19.99
- `ZQ093405` MESA DE NOCHE YELLOW FIR + WARM WHITE, 1 GAVETA 40 CM. ZQ093405: catálogo $17.99 → inventario $24.99
- `LXI090408` MESA DE NOCHE YELLOW FIR + WARM WHITE, 2 GAVETAS 36X34 CM. LXI090408: catálogo $21.99 → inventario $19.99
- `CZX100310` MUEBLE ORGANIZADOR 100X60X110 CZX100310: catálogo $59.99 → inventario $54.99
- `HYI220725` MUEBLE ORGANIZADOR 3 REPISAS 100X35X80 HYI220725: catálogo $39.99 → inventario $49.99
- `CZX100304` MUEBLE ORGANIZADOR 68X50X195 BLACK CZX100304: catálogo $45.99 → inventario $44.99
- `CZX100308` MUEBLE ORGANIZADOR 68X50X195 WHITE CZX100308: catálogo $45.99 → inventario $44.99
- `HYI221013` MUEBLE ORGANIZADOR CON PUERTAS 60X40X80 HYI221013: catálogo $59.99 → inventario $55.99
- `HYI360747` MUEBLE PARA JARDIN 100X40X100 HYI360747: catálogo $39.99 → inventario $35.99
- `HYI360748` MUEBLE PARA JARDIN 140X40X100 HYI360748: catálogo $45.99 → inventario $39.99
- `XD025301` MUEBLE ZAPATERA 100X180X32 XD025301: catálogo $80.64 → inventario $89.99
- `DOG020205` MUEBLE ZAPATERA CURCUMA SANDALWOOD 80X102X34 DOG020205: catálogo $49.99 → inventario $65.99
- `YOYU020801` MUEBLE ZAPATERA MORANDI PINE 80X102X34 YOYU020801: catálogo $49.99 → inventario $59.99
- `LXI062906` PEINADORA CREAM WHITE SIN ESPEJO 100cm LXI062906: catálogo $79.99 → inventario $69.99
- `LXI063101` PEINADORA WARM WHITE CON ESPEJO REDONDO 60cm LXI063101: catálogo $39.99 → inventario $45.99
- `RUY230612` ZAPATERA 8 NIVELES SANDALWOOD 102X120X26 RUY230612: catálogo $35.99 → inventario $30.00

## No se importan

- `(sin código)` Descuento
- `TIPS` Propinas
- `(sin código)` X COLCHON IMPERIAL TWIN 2/3 PARA COMBO
- `(sin código)` X COLCHON IMPERIAL TWIN 3/3 PARA COMBO

## Repetidos en el CSV

- `XXI070507` MUEBLE DE TV CEDAR WARM WHITE 180cm XXI070507 — a la mano 0

## Dudas de lectura (columna `dudas` del CSV)

- p1 f12 `YPN272107` BIBLIOTECA 5 REPISAS YPN272107: costo 0.00 en la captura
- p1 f26 `XD271621` BIBLIOTECA DARK WALNUT 6 REPISAS 80X192X32 XD271621: costo 0.00 en la captura
- p2 f51 `803KGR` CAMA KING COLOR GREY 803KGR: costo 6.00 llamativo; confirmado con zoom x3
- p3 f70 `IM-2002` COLCHON IMPERIAL FULL 4/6 BUEN SUEÑO / IM-2002: pronosticado 6 distinto de a la mano 7; confirmado con zoom x3
- p3 f73 `CN10BL00PE03907505P` COLCHONETA TWIN 39X75X5P / CN10BL00PE03907505P: costo (35.06) mayor que precio (34.99); confirmado con zoom x3
- p5 f44 `XXI070507` MUEBLE DE TV BLANCO 220X30X36CM / XXI070507: código XXI070507 repetido en la fila 46 (producto distinto)
- p5 f46 `XXI070507` MUEBLE DE TV CEDAR WARM WHITE 180cm XXI070507: código XXI070507 repetido en la fila 44 (producto distinto)
- p6 f8 `XLB221105` MUEBLE ORGANIZADOR DE COCINA CON CESTAS 80X130X30 XLB221105: costo 0.00 en la captura
- p6 f44 `(sin código)` MUEBLE ZAPATERA 120X102X34 XU023703: sin código; precio de venta aparece en gris en la captura
- p6 f46 `MIK020716` MUEBLE ZAPATERA 120X118.5X24 MIK020716: costo 0.00 en la captura
- p6 f56 `(sin código)` MUEBLE ZAPATERA 80X102X34 XU023701: sin código; precio de venta aparece en gris en la captura

## Fotos

- Fotos asignadas a productos nuevos (archivo que empieza por el código): 6.
- Productos nuevos sin foto: 328 → `docs/inventario-anterior-fotos-faltantes.xlsx`
  (código, nombre, existencias). Entran al inventario sin publicar en la web hasta tener foto.
- En «up media» no hay fotos de códigos del inventario que no estén ya en `static/img/productos`.
