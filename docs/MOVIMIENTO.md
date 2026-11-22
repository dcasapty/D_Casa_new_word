# Movimiento: comparar periodos (`dcasa_marketing`)

Pedido de la dueña (2026-11-22), después de ver Rotación:

> «Continúa con lo que te pedí de poder ver los artículos con mayor y menor movimiento y rotación de forma más precisa
> por tiempos y comparar periodos, o sea, todo con la finalidad de poder hacer campañas de publicidad y de redes
> sociales de forma más práctica y fácil.»

Marketing ya tenía «Mayor movimiento» y «Más quietos» (Semana, 15 días, Mes) y Rotación mide **cuánto lleva cada
producto sin venderse**. Lo que faltaba: poner **dos periodos lado a lado** y ver qué **subió, bajó o se enfrió**, para
decidir qué anunciar. «Movimiento» es esa pantalla.

## Para la dueña (en corto)

**Dónde está.** *Inventario › Movimiento* (Gerencia y administradores), el botón **Comparar periodos** de la pantalla
*Marketing* (también para el rol Marketing) y un enlace en la pantalla *Rotación*.

**Qué haces.**

1. **«1 · ¿Qué periodo miras?»**: últimos 7, 15, 30, 60 o 90 días, este mes, el mes pasado o **«Elegir fechas»**.
2. **«2 · ¿Contra cuál lo comparas?»**: el periodo de justo antes (del mismo largo), el mismo periodo del año pasado o
   **«Elegir fechas»**. Arriba de los resultados la pantalla escribe las fechas exactas de los dos.
3. **«3 · ¿Qué productos quieres ver?»**: *los que más venden*, *los que subieron*, *los que bajaron*, *se enfriaron*,
   *quietos con existencias* o *todos*. Cada botón dice cuántos productos tiene. Debajo, una frase dice para qué sirve
   esa lista. También eliges categoría, buscas por nombre o código y ordenas.

**Qué ves.**

- **El resumen**: unidades vendidas, pedidos (facturas) y productos que se vendieron, ahora y antes, con el cambio en
  %. Gerencia ve además lo **vendido en $** (sin ITBMS).
- **La gráfica**: unidades vendidas por día (o por semana si el periodo pasa de 31 días): línea azul = este periodo,
  gris = el de comparación.
- **Cada producto**: su estado (*Subió*, *Despertó*, *Igual*, *Bajó*, *Se enfrió* o *Quieto*), lo vendido ahora y antes
  (unidades y pedidos), el cambio (+/− y %), las existencias, **para cuántos días alcanza** lo que hay al ritmo de este
  periodo, cuándo se vendió por última vez y si es *ancla*, está *agotado* o *sin foto*. Gerencia ve también lo vendido
  en $ y, en los quietos, el capital parado.

**Para campañas.** Debajo de la lista: **«Crear campaña con los primeros 8»** (Camila arma el correo con esos
productos; solo van los que hay en tienda, con foto y publicados) y **«Ver estos en Productos»** (la lista completa, para
sacar las fotos y publicar en redes). **«Descargar Excel»** trae la lista completa con todas las columnas. Antes de
anunciar un producto, mira que **no esté agotado** y que **le alcance** lo que hay.

## Cómo se cuenta cada cifra

Nada se estima ni se inventa; todo sale de la base (`addons/dcasa_marketing/models/movimiento.py`).

| Cifra | Qué cuenta |
|---|---|
| Ventas | Las **facturas de cliente publicadas** (la misma base de Marketing y Rotación): sin servicios ni anticipos; las notas de crédito restan unidades y dinero. Solo productos activos y a la venta. |
| Un periodo | Días corridos con el **primer y el último día incluidos** (hora de Panamá). «30 días» son hoy y los 29 de antes. |
| El de comparación | **Anterior**: el mismo largo, justo antes (si este va de 23 oct a 21 nov, el otro va de 23 sep a 22 oct). **Año pasado**: el mismo tramo un año antes (un 29 de febrero se cuenta como 28). **Fechas**: las que escribas (no pueden cruzarse con este periodo). |
| Este mes / Mes pasado | *Este mes* va del día 1 a hoy y se compara con **el mismo tramo del mes pasado** (si el mes pasado fue más corto, hasta su último día). *Mes pasado* es el mes completo y se compara con el mes anterior a ese. Si los dos periodos no tienen el mismo largo, la pantalla lo avisa. |
| Límites | Hasta 366 días por periodo; nada del futuro. |
| Pedidos | En cuántas facturas salió el producto: muestra si se mueve seguido o si fue una sola venta grande. Si un producto con más de un color o medida sale en la misma factura, cuenta una vez por variante. El total del resumen cuenta cada factura una sola vez. |
| Estado | Uno por producto: **Subió** (más unidades que antes), **Despertó** (antes no se vendía), **Igual**, **Bajó** (se vende, pero menos), **Se enfrió** (antes se vendía y ahora no) y **Quieto** (con existencias y sin ventas en ninguno de los dos). Sin ventas y sin existencias no sale. Si las devoluciones superan las ventas, cuenta como 0. |
| Cambio % | (ahora − antes) ÷ antes. Si antes no se vendió nada, no hay porcentaje (nunca se divide entre cero). |
| Alcanza para | Existencias ÷ (unidades de este periodo ÷ días del periodo). Sin ventas en este periodo no se calcula. Cuánto pedir y cuándo lo calcula *Compras › Reponer*. |
| Ancla, días sin vender, capital | Los de [Rotación](ROTACION.md). |
| Sin ventas en la comparación | Si en el periodo de comparación no hay ninguna venta (por ejemplo, el año pasado, antes de usar Odoo), la pantalla lo dice: todo aparece como «Despertó» y no es una subida real. |

**Lo que mide y lo que no.** Mide ventas **facturadas**, no cotizaciones ni pedidos sin facturar. No mide si un producto
se vende poco por falta de foto, precio o existencias (por eso la fila dice *Sin foto*, *Agotado* y *Alcanza para*). Las
ventas de productos ya archivados o que no están a la venta no entran. No separa por almacén.

## Permisos

- **Entran** Gerencia (ventas administrador), administradores y el rol **Marketing**; el servidor lo exige en cada
  llamada (`dcasa.movimiento_productos._exigir`, el mismo de `dcasa.marketing`).
- **El dinero** (lo vendido en $ y el capital parado) es **solo de Gerencia y administradores**
  (`dcasa.tablero._ve_utilidad`): al rol Marketing el servidor ni se lo manda (ni en la pantalla, ni en el Excel, ni en
  Brian).
- La vendedora, Caja y Bodega no entran (`AccessError`; el Excel contesta 403).
- Lista blanca RPC: `dcasa.movimiento_productos.datos` en `dcasa_base/tests/test_superficie_rpc.py`. El Excel es la ruta
  `/dcasa/movimiento/excel` (`controllers/movimiento.py`), que exige el mismo permiso antes de leer.
- **El nombre del modelo no es `dcasa.movimiento`**: ese ya es el libro de puntos de Socios (`dcasa_socios`). Dos modelos
  con el mismo nombre se mezclan y la base no carga (`KeyError: 'partner_id'`).

## Brian

`comparar_movimiento(periodo?, contra?, vista?, categoria?, limite?)` (lectura; Gerencia, administradores y rol
Marketing; el dinero solo para los dos primeros). Ver [BRIAN.md](BRIAN.md) › «Marketing y fotos». Ejemplos: «¿qué subió
este mes frente al mes pasado?» → `periodo=este_mes, vista=subieron`; «¿qué se enfrió en los últimos 30 días?» →
`periodo=30, vista=enfriaron`.

## Pruebas

- `tests/test_movimiento.py`: los extremos exactos de los periodos (hoy y 29 días atrás; 30 y 59 días atrás; 60 no
  cuenta), este mes y el mes pasado, el año pasado, fechas a mano y las que no valen, los seis estados, el cambio y su
  porcentaje (incluido el que no se divide entre cero), la nota de crédito, los pedidos (una factura grande contra tres
  chicas), la cobertura, las listas y su orden, categoría y texto, el resumen (unidades, pedidos distintos, productos y
  dinero), el aviso de comparación sin ventas, el gráfico (por día y por semana), los permisos (Marketing sin dinero;
  vendedora y bodega sin entrar) y el Excel.
- `tests/test_movimiento_navegador.py` (390×844 y 1440×900, Chrome): los botones de periodo y de comparación, el resumen,
  las listas con una fila de cifras exactas, «Elegir fechas», el Excel con lo que se ve, la ida y vuelta con Rotación,
  el gráfico, el scroll y sin scroll de costado; el rol Marketing llegando desde su botón y sin ver un solo dólar; y el
  Excel por la ruta (la vendedora recibe 403).

## Lo que no hace (todavía)

- No crea publicaciones ni anuncios: **decide Gerencia**. «Crear campaña con los primeros 8» arma un borrador de correo
  con Camila (nunca envía). Para redes, «Ver estos en Productos» da la lista con sus fotos.
- No compara contra una meta ni contra otra tienda; no separa por vendedora ni por origen (tienda, web, chatbot).
- No sabe de estacionalidad: «Este mes contra el mes pasado» no dice si diciembre siempre vende más.
