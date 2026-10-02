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

## Pedido LTSC-07 (`up media/Catalogo_LTSC-07_Precios_PRODUCTOS_NUEVOS.xlsm`)

Generado por `scripts/importar_catalogo.py`. Productos nuevos: **35** (38 filas del Excel). Con variantes de color (un producto por código, misma cifra en cada color y su foto propia): `908K` (Beige, Negro, Gris), `908Q` (Beige, Negro).

Precios SIN ITBMS y terminados en .99 (se conserva la parte entera). Las columnas «Total con ITBMS» del Excel no se usan. Un combo vacío en el Excel no se crea.

### Códigos que ya estaban en el catálogo: producto aparte

- `Y0300300` ya está en el catálogo («Cama queen negra, cabecero con alas en chevron», $159.99); el pedido LTSC-07 dice $129.99. El que estaba no se toca; las unidades del pedido son el producto aparte **`Y0300300-LTSC07`**.

### Precios (Excel → precio cargado)

| Producto | Cama sola | Combo (Excel → cargado) |
|---|---|---|
| `888K` | 259.99 → **259.99** | First Class 469.98 → Combo con colchón First Class $469.99 |
| `888Q` | 219.99 → **219.99** | Dulce Sueños 378.66 → Combo con colchón Dulce Sueños $378.99 |
| `908K` | 229.99 → **229.99** | First Class 439.98 → Combo con colchón First Class $439.99 |
| `908Q` | 159.99 → **159.99** | Dulce Sueños 318.66 → Combo con colchón Dulce Sueños $318.99 |
| `803K` | 179.99 → **179.99** | First Class 389.98 → Combo con colchón First Class $389.99 |
| `809Q` | 139.99 → **139.99** | Dulce Sueños 298.66 → Combo con colchón Dulce Sueños $298.99 |
| `811Q` | 139.99 → **139.99** | Dulce Sueños 298.66 → Combo con colchón Dulce Sueños $298.99 |
| `811K` | 199.99 → **199.99** | First Class 409.98 → Combo con colchón First Class $409.99 |
| `822F` | 99.99 → **99.99** | Imperial 186.64 → Combo con colchón Imperial $186.99 |
| `823Q` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `823F` | 119.99 → **119.99** | Imperial 206.64 → Combo con colchón Imperial $206.99 |
| `825K` | 159.99 → **159.99** | First Class 369.98 → Combo con colchón First Class $369.99 |
| `825Q` | 119.99 → **119.99** | Dulce Sueños 278.66 → Combo con colchón Dulce Sueños $278.99 |
| `903F` | 139.99 → **139.99** | Imperial 226.64 → Combo con colchón Imperial $226.99 |
| `6877F` | 99.99 → **99.99** | Imperial 186.64 → Combo con colchón Imperial $186.99 |
| `6220Q` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0200100` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0200200-Q` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0200300` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0200101` | 119.99 → **119.99** | Imperial 206.64 → Combo con colchón Imperial $206.99 |
| `Y0200201` | 119.99 → **119.99** | Imperial 206.64 → Combo con colchón Imperial $206.99 |
| `Y0200301` | 119.99 → **119.99** | Imperial 206.64 → Combo con colchón Imperial $206.99 |
| `Y0300200` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0300300-LTSC07` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0300400` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0400100-Q` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0400200-Q` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0400300-Q` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0400400-Q` | 129.99 → **129.99** | Dulce Sueños 288.66 → Combo con colchón Dulce Sueños $288.99 |
| `Y0400301` | 119.99 → **119.99** | Imperial 206.64 → Combo con colchón Imperial $206.99 |
| `Y0400101-F` | 119.99 → **119.99** | Imperial 206.64 → Combo con colchón Imperial $206.99 |
| `Y0400201-F` | 119.99 → **119.99** | Imperial 206.64 → Combo con colchón Imperial $206.99 |
| `N-F10018-Q-BK` | 69.99 → **69.99** | Dulce Sueños 228.66 → Combo con colchón Dulce Sueños $228.99 |
| `HK-BF-022-N-F-1-W` | 109.99 → **109.99** | Imperial 196.64 → Combo con colchón Imperial $196.99 |
| `HK-BF-022-N-K-1-W` | 159.99 → **159.99** | First Class 369.98 → Combo con colchón First Class $369.99 |

### Fotos de la carpeta: a qué producto fue cada una

Primera foto = principal; las demás, a la galería (fotos «con colchón» al final).

- `6220Q Cama tapizada Queen – rosado 205 × 151 × 110 cm.jpg` → **6220Q** (`6220Q_1.jpg`): por código — código 6220Q.
- `803K - Cama tapizada King – gris - 213 × 163 × 125 cm.jpg` → **803K** (`803K_1.jpg`): por código — código 803K.
- `823Q Cama tapizada Queen – marrón 215 × 152 × 120 cm.jpg` → **823Q** (`823Q_1.jpg`): por código — código 823Q.
- `903F Cama tapizada Full – gris 193 × 135 × 120 cm.jpg` → **903F** (`903F_1.jpg`): por código — código 903F.
- `908K - Cama tapizada King – beige - 203 × 193 × 123 cm con colchon.jpg` → **908K** beige (`908K-beige_3.jpg`): por código — código 908K, color beige.
- `908K - Cama tapizada King – beige - 203 × 193 × 123 cm.jpg` → **908K** beige (`908K-beige_1.jpg`): por código — código 908K, color beige.
- `908K - Cama tapizada King – negro 203 × 193 × 123 cm.webp` → **908K** negro (`908K-negro_1.jpg`): por código — código 908K, color negro.
- `908K Cama tapizada King – Gris 203 × 193 × 123 cm.jpg` → **908K** gris (`908K-gris_1.jpg`): por código — código 908K, color gris.
- `908K Cama tapizada King – beige 203 × 193 × 123 cm.png` → **908K** beige (`908K-beige_2.jpg`): por código — código 908K, color beige.
- `908K Cama tapizada King – negro 203 × 193 × 123 cm.jpg` → **908K** negro (`908K-negro_2.jpg`): por código — código 908K, color negro.
- `908Q - Cama tapizada Queen – beige 203 × 152 × 123 cm.jpg` → **908Q** beige (`908Q-beige_1.jpg`): por código — código 908Q, color beige.
- `908Q Cama tapizada Queen – negro 203 × 152 × 123 cm.jpg` → **908Q** negro (`908Q-negro_1.jpg`): por código — código 908Q, color negro.
- `Cama tapizada Full – beige 193 × 135 × 110 cm.jpg` → **6877F** (`6877F_1.jpg`): por descripción — Full · beige · 193×135×110 → única fila del Excel: 6877F.
- `Cama tapizada Full – blanco 193 × 135 × 110 cm.jpg` → **822F** (`822F_1.jpg`): por descripción — Full · blanco · 193×135×110 → única fila del Excel: 822F.
- `Cama tapizada Full – gris 193 × 135 × 120 cm.jpg` → **823F** (`823F_1.jpg`): decisión revisada a mano — en el Excel 823F y 903F son «Full – gris 193 × 135 × 120 cm»; 903F ya tiene su foto con código (cabecero de botones con piecera) y esta muestra el cabecero de canales con alas de la foto del Excel de 823F.
- `Cama tapizada King – rosado 205 × 193 × 110 cm.jpg` → **825K** (`825K_1.jpg`): por descripción — King · rosado · 205×193×110 → única fila del Excel: 825K.
- `Cama tapizada Queen – beige 213 × 158 × 120 cm.jpg` → **811Q** (`811Q_1.jpg`): decisión revisada a mano — en el Excel 809Q y 811Q son «Queen – beige 213 × 158 × 120 cm»; esta foto tiene el cabecero de canales verticales de la foto del Excel de 811Q (la de 809Q es de cabecero curvo con alas).
- `Cama tapizada Queen – beige 213 × 199 × 125 cm.jpg` → **811K** (`811K_1.jpg`): decisión revisada a mano — el nombre dice Queen, pero 213 × 199 × 125 cm son las medidas de 811K (King – beige) y ninguna Queen del Excel las tiene; es casi la misma imagen que la de 811Q.
- `Cama tapizada Queen – crema 205 × 151 × 110 cm.jpg` → **825Q** (`825Q_1.jpg`): por descripción — Queen · crema · 205×151×110 → única fila del Excel: 825Q.
- `HK-BF-022-N-F-1-W.jpg` → **HK-BF-022-N-F-1-W** (`HK-BF-022-N-F-1-W_1.jpg`): por código — código HK-BF-022-N-F-1-W.
- `HK-BF-022-N-K-1-W.jpg` → **HK-BF-022-N-K-1-W** (`HK-BF-022-N-K-1-W_1.jpg`): por código — código HK-BF-022-N-K-1-W.
- `N-F10018-Q-BK.jpg` → **N-F10018-Q-BK** (`N-F10018-Q-BK_1.jpg`): por código — código N-F10018-Q-BK.
- `Y0200100 Cama tapizada Queen – cuero marrón  205 × 151 × 110 cm.jpg` → **Y0200100** (`Y0200100_1.jpg`): por código — código Y0200100.
- `Y0200101 Cama tapizada Full – cuero marrón 193 × 135 × 110 cm.webp` → **Y0200101** (`Y0200101_1.jpg`): por código — código Y0200101.
- `Y0200200-Q Cama tapizada Queen – cuero negro.jpg` → **Y0200200-Q** (`Y0200200-Q_1.jpg`): por código — código Y0200200-Q.
- `Y0200201 -Full cuero negro 193×135×110 cm.jpg` → **Y0200201** (`Y0200201_1.jpg`): por código — código Y0200201.
- `Y0200300 Cama tapizada Queen – cuero gris.jpg` → **Y0200300** (`Y0200300_1.jpg`): por código — código Y0200300.
- `Y0200301 -Full cuero gris 193×135×110 cm.jpg` → **Y0200301** (`Y0200301_1.jpg`): por código — código Y0200301.
- `Y0300200  Cama tapizada Queen – lino gris claro 205 × 151 × 110 cm.jpg` → **Y0300200** (`Y0300200_1.jpg`): por código — código Y0300200.
- `Y0300300  Cama tapizada Queen – lino negro 205 × 151 × 110 cm.jpg` → **Y0300300-LTSC07** (`Y0300300-LTSC07_1.jpg`): por código — código Y0300300.
- `Y0300400  Cama tapizada Queen – lino marron 205 × 151 × 110 cm.jpg` → **Y0300400** (`Y0300400_1.jpg`): por código — código Y0300400 (ojo: el archivo dice «lino» y el Excel «tela»).
- `Y0400100-Q Cama tapizada Queen – lino gris oscuro 205 × 151 × 110 cm.jpg` → **Y0400100-Q** (`Y0400100-Q_1.jpg`): por código — código Y0400100-Q.
- `Y0400101-F Cama tapizada Full – lino gris oscuro 193 × 135 × 110 cm.jpg` → **Y0400101-F** (`Y0400101-F_1.jpg`): por código — código Y0400101-F.
- `Y0400200-Q Cama tapizada Queen – lino gris oscuro 205 × 151 × 110 cm.jpg` → **Y0400200-Q** (`Y0400200-Q_1.jpg`): por código — código Y0400200-Q (ojo: el archivo dice «gris oscuro» y el Excel «gris claro»).
- `Y0400201-F Cama tapizada Full – lino gris claro 193 × 135 × 110 cm.jpg` → **Y0400201-F** (`Y0400201-F_1.jpg`): por código — código Y0400201-F.
- `Y0400300-Q  Queen tela marron205×151×110 cm.jpg` → **Y0400400-Q** (`Y0400400-Q_1.jpg`): decisión revisada a mano — el nombre dice Y0400300-Q, pero esa fila es «tela negra» y ya tiene su foto «tela negra»; la cama de esta foto es marrón y la Queen «tela marrón» de la misma serie (Y04…-Q) es Y0400400-Q, que no tenía foto (Y0300400 tiene la suya).
- `Y0400300-Q  Queen tela negra 205×151×110 cm.jpg` → **Y0400300-Q** (`Y0400300-Q_1.jpg`): por código — código Y0400300-Q.
- `Y0400301 Cama tapizada Full – tela negra 193 × 135 × 110 cm.jpg` → **Y0400301** (`Y0400301_1.jpg`): por código — código Y0400301.
- `image_20261001_183440-ahora-esta-cama-tapizada-queen-en-color-beige-213.jpg` → **809Q** (`809Q_1.jpg`): decisión revisada a mano — el nombre dice «queen … beige 213» (809Q u 811Q); cabecero curvo con alas, como la foto del Excel de 809Q.

### Fotos dudosas que no se usaron

- Ninguna.

### Productos con la foto del Excel (no había foto en la carpeta)

- `888K` (fila 5)
- `888Q` (fila 6)

### Otras dudas del Excel

- La foto incrustada que empieza en la fila 37 del Excel termina en la fila 38: se tomó como foto de la fila 38.
- La foto incrustada que empieza en la fila 38 del Excel termina en la fila 39: se tomó como foto de la fila 39.
- `Y0200100`: en «Medidas» el Excel dice «Queen» (no son medidas): la ficha sale sin medidas.
- `Y0200200-Q`: en «Medidas» el Excel dice «Queen» (no son medidas): la ficha sale sin medidas.
- `Y0200300`: en «Medidas» el Excel dice «Queen» (no son medidas): la ficha sale sin medidas.
- `Y0400201-F`: en «Medidas» el Excel dice «Full» (no son medidas): la ficha sale sin medidas.
- `N-F10018-Q-BK`: el Excel dice «205 × 151 × 110 cm»; base metálica sin cabecero con 110 cm de alto (las mismas medidas que las camas tapizadas Queen): no se publican hasta que la dueña las confirme.
- `HK-BF-022-N-F-1-W`: en «Medidas» el Excel dice «Full» (no son medidas): la ficha sale sin medidas.
- `888Q`: la descripción del Excel no trae color («Cama tapizada Queen»); 888K sí dice beige. Sale sin color en el nombre.
- `822F` y `HK-BF-022-N-F-1-W` son los dos «Full – blanco». La foto sin código «Full – blanco 193 × 135 × 110» fue a 822F porque solo 822F tiene esas medidas en el Excel; HK-BF-022-N-F-1-W tiene su propia foto con código.
- `908K` beige: sus tres fotos son casi la misma imagen (una dice «con colchón»); quedan las tres en ese color, la de «con colchón» al final.
- `811Q` y `811K` quedan con casi la misma imagen (los nombres de archivo dicen 213 × 158 y 213 × 199): confirmar que 811K es esa cama.
- La foto incrustada en el Excel de `822F` muestra una cama de color tostado, no blanca: la foto de la carpeta («Full – blanco») sí es blanca. Confirmar el color con la mercancía.

## Gráficas de Black Weekend (`up media/115.png` … `153.png`, revisión del 2026-10-02)

39 gráficas de la dueña (1080 × 1350, texto incrustado). Los precios de cama sola y combo coinciden con el pedido LTSC-07 cargado. La web no las usa como foto de producto (texto incrustado: malo para la carga, Google y lectores de pantalla); `115.png`, recortada sin la franja de abajo, es la imagen para compartir de /black-weekend (`addons/website_dcasa/static/src/img/black_weekend/og.jpg`). Las originales se quedan en «up media» (no entran a la imagen de Docker: `.dockerignore`).

### Errores en las gráficas (los corrige la dueña en su arte; el catálogo queda como está)

- `146.png` y `147.png` dicen «Y0400300-Q», pero la cama es MARRÓN: es `Y0400400-Q` (tela marrón). `Y0400300-Q` es la de tela negra. **Confirmado por la dueña el 2026-10-02.**
- `147.png` es la misma gráfica que `146.png` (duplicada).
- `150.png` dice «Y0400101-F», pero la cama es gris CLARO: es `Y0400201-F` (lino gris claro). `Y0400101-F` es la de gris oscuro. **Confirmado por la dueña el 2026-10-02.**
- `152.png` dice «BASE QUEEN HK-BF-022-N-K-1-W $109.99», pero $109.99 y 193 cm son de `HK-BF-022-N-F-1-W` (Full).
- `153.png` dice «BASE QUEEN», pero `HK-BF-022-N-K-1-W` es una cama King ($159.99).
  - La dueña dice (2026-10-02) que la «Base Queen» de la gráfica es correcta. Pendiente: el Excel LTSC-07
    la llama «Cama tapizada King – blanco» con 205 × 193 cm (193 de ancho es medida King). En el
    catálogo sigue como King hasta que la dueña diga cuál de los dos se corrige.
- Todas traen «Promoción de apertura por ¡tiempo limitado!» y el sello de cuotas: la web no los repite (sin urgencia inventada ni financiamiento: descartado por la dueña el 2026-10-02).

### Dudas que las gráficas resuelven (el catálogo ya las tenía bien)

- `809Q` = cabecero curvo con alas (`123.png`); `811Q` = canales verticales (`124.png`). Las fotos del catálogo (`809Q_1.jpg`, `811Q_1.jpg`) coinciden: no estaban invertidas.
- `822F` es crema/blanca (`126.png`), como su foto «Full – blanco» (la foto del Excel se veía tostada).
- `888Q` es crema/beige (`116.png`). El nombre sigue sin color: el Excel no lo dice.
- `Y0400200-Q` es gris claro (`144.png`), como dice el Excel (el nombre del archivo decía «gris oscuro»).

### Selección para la web (`addons/dcasa_catalogo/catalogo.py`: `BLACK_WEEKEND`)

- 888K (115) · 908K negro (118) · 803K (122) · 809Q (123) · 822F (126) · 825K (129) · 6220Q (133) · 6877F (132) · Y0200100 (134) · Y0300300-LTSC07 (141; no el Y0300300 de $159.99) · HK-BF-022-N-K-1-W (153) · N-F10018-Q-BK (151).
- Ventana: lunes 5 a domingo 11 de octubre de 2026, hora de Panamá (decisión de la dueña). Staging la muestra ya (vista previa).