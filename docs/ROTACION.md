# Rotación del inventario (`dcasa_marketing`)

Pedido de Gerencia (2026-11-22), llegado por la dueña desde el jefe:

> «Que indique cuáles productos no han tenido rotación y poder definir en cuánto tiempo (30, 60, 90 días, etc.) a los
> fines de bajarlos de precio y recuperar capital de trabajo; que se enfoque en aquellos de mejor rotación o prueba en
> nuevos SKU que mejoren márgenes, o que sean productos ancla.» · «Tenemos lo más movido y lo más quieto, sí, pero tiene
> que haber formas más precisas de identificarlo por días o por flujos por pedidos.»

El tablero de Marketing ya tenía «Más quietos» y «Mayor movimiento» (Semana, 15 días, Mes), pero solo ordenaba y no
decía **cuánto dinero está parado**, ni dejaba escoger «30, 60 o 90 días», ni separaba lo que llegó hace poco de lo que
de verdad no se vende. «Rotación» es esa pantalla.

## Para la dueña (en corto)

**Dónde está.** *Inventario › Rotación* (Gerencia y administradores), el botón **Rotación del inventario** de la
pantalla *Marketing* (también para el rol Marketing) y un acceso directo en el Inicio.

**Qué ves.**

1. **Arriba**, el dinero que costó la mercancía que hay y cuánto de eso lleva **90 días o más sin venderse**. Si hay
   productos con existencias y sin costo cargado, avisa (su dinero no suma).
2. **«Por días sin vender»**: una barra por grupo. Cada producto con existencias está en **uno solo**: *menos de 30
   días*, *30 a 59*, *60 a 89*, *90 a 179*, *180 o más*, *nunca vendido*, *llegó hace poco* o *pedido abierto*. Tocas una
   barra y abajo salen sus productos.
3. **«¿Qué productos quieres ver?»**: los botones que pidió el jefe (*30 días o más sin vender*, *60*, *90*, *180*) y
   además *nunca vendidos*, *llegaron hace poco*, *con pedido abierto* y *ancla*. Eliges categoría, buscas por nombre o
   código y ordenas por *más capital parado*, *más días sin vender*, *mejor rotación*, *mejor margen*, *se agota primero*
   o nombre.
4. **Cada producto** dice: existencias, cuándo se vendió por última vez, lo vendido en 30 · 60 · 90 días, para cuántos días
   alcanza lo que hay, el capital parado, el precio y el margen. Con el rol Marketing salen las unidades y los días, sin
   dinero.
5. **«Si se rebaja (simulación)»**: escribes un porcentaje y te dice cuánto entraría a caja con esos productos, cuánto
   costaron, cuánto queda sobre el costo y **cuántos quedarían por debajo del costo**. Es solo una cuenta: **no cambia
   ningún precio**.
6. **Descargar Excel**: la lista que estás viendo, **completa** (la pantalla muestra los primeros 100), más una hoja
   «Resumen» con los grupos.

7. **«Por margen y rotación»** (solo Gerencia y administradores): cuatro botones más para elegir **qué empujar y qué
   rebajar**. Cada producto con existencias, costo y precio cae en uno solo:
   - **Estrellas**: se venden bien y dejan buen margen. Cuídalos y anúncialos con tranquilidad.
   - **Venden mucho, dejan poco**: traen gente a la tienda, pero dejan poco margen. Ojo con rebajarlos.
   - **Buen margen, se mueven poco**: cada venta deja mucho. Son los mejores para anunciar y darles visibilidad.
   - **Ni se mueven ni dejan margen**: candidatos a rebajar para liberar capital, o a no volver a pedir.

   «Se venden bien» y «buen margen» no son cifras puestas a mano: son **la mitad de arriba de la propia tienda** (la
   mediana), y la pantalla dice los números de hoy («3 unidades o más en 90 días», «38 % o más»). Para elegir qué
   productos nuevos probar, mira las estrellas y busca parecidos.

**Lo que no se ofrece como candidato a rebajar.** Lo que *llegó de un proveedor hace menos de 30 días* y todavía no se
vende, lo que tiene un *pedido confirmado sin facturar* (esa mercancía ya tiene dueño) y los *productos ancla*.

## Cómo se cuenta cada cifra

Nada se estima ni se inventa; todo sale de la base (`addons/dcasa_marketing/models/rotacion.py`).

| Cifra | Qué cuenta |
|---|---|
| Ventas | Las **facturas de cliente publicadas** (la misma base del Inicio, Marketing y Reponer): sin servicios ni anticipos; las notas de crédito restan unidades. Una ventana de N días son los últimos N días corridos, hoy incluido (hora de Panamá). |
| Días sin vender | De hoy a la fecha de la **última factura** del producto. Grupos exactos que no se solapan: menos de 30, 30 a 59, 60 a 89, 90 a 179, 180 o más (`CORTES`). Sin ninguna factura: *nunca vendido*. Hoy es día 0 (vendido hoy = *menos de 30 días*). |
| «30 días o más», «60 o más»… | La suma de los grupos que llevan **ese tiempo o más** sin venderse, con los que nunca se vendieron, **sin** los nuevos ni los de pedido abierto. |
| Llegó hace poco | Su **primera recepción de un proveedor** (solo compras) fue hace menos de 30 días y todavía no tiene ventas. Un ajuste de inventario o una carga inicial **no es una llegada**. Sin ninguna recepción registrada, la fecha se ignora: nunca se inventa. |
| Pedido abierto | Tiene un pedido de venta **confirmado** que todavía no se factura entero (unidades pedidas − unidades facturadas > 0). Una cotización no cuenta. Si se vendió hace menos de 30 días sigue en su grupo de días. |
| Ancla | Los productos que **juntos hacen el 80 % de las unidades vendidas en 90 días** (la regla de Pareto, 80/20), de mayor a menor, sobre **toda la tienda** aunque la pantalla esté filtrada a una categoría. Son los que traen a la gente a la tienda: se cuidan. |
| Alcanza para (cobertura) | Existencias ÷ (unidades vendidas en 90 días ÷ 90). Sin ventas en 90 días no se calcula. **Cuánto pedir y cuándo** lo calcula *Compras › Reponer*, con el tiempo que tarda en llegar. |
| Capital parado | Lo que **costó** la mercancía que hay, con la valuación de Odoo: **la misma de «Valor del inventario»**: la suma de todos los grupos es el total de esa pantalla, menos la mercancía de productos archivados o que no están a la venta (aquí no cuentan). Lo negativo no suma. |
| Margen | (precio de venta sin ITBMS − costo) ÷ precio de venta, como en «Valor del inventario» y «Mejor margen». |
| Margen y rotación | Solo Gerencia y administradores. **Se vende bien**: vendió al menos una unidad en 90 días y tantas como la **mediana** de lo vendido en 90 días entre los productos que sí se vendieron. **Buen margen**: tanto como la **mediana** del margen de los productos con existencias, costo y precio. Los cuatro cuadros salen de cruzar las dos cosas (justo en el corte cuenta como «de arriba»). Un producto sin costo, sin precio o agotado no tiene cuadro, ni tampoco el que **llegó hace menos de 30 días** o ya tiene un **pedido confirmado** (todavía no se puede juzgar su rotación y no se ofrece como candidato a rebajar). Un **ancla** cuenta como que se vende bien aunque quede justo debajo de la mediana. Las medianas se calculan sobre **toda la tienda**, aunque la pantalla esté filtrada a una categoría. Si ningún producto se vendió en 90 días, nadie «se vende bien». |
| Simulación | Con X %: precio × (1 − X ÷ 100) por las unidades que hay; ingreso, costo, diferencia, margen y cuántos productos quedarían por debajo del costo. El precio mínimo para no perder es el **costo**. Entre 1 y 95 %. |

**Lo que mide y lo que no.** Mide ventas **facturadas**: una venta confirmada que todavía no se factura no cuenta hasta que
se factura (por eso existe «pedido abierto»). No mide si un producto se vende poco *porque no tiene foto, precio o stock*:
eso lo dicen las otras secciones de Marketing. Un producto con **más de un color o medida** se cuenta como uno solo.
No se llama «producto muerto» a nada: se dice cuántos días lleva sin venderse y la decisión es de Gerencia.

## Permisos

- **Entran** Gerencia (ventas administrador), administradores y el rol **Marketing**; el servidor lo exige en cada
  llamada (`dcasa.rotacion._exigir`, el mismo de `dcasa.marketing`).
- **El dinero** (costos, capital parado, precio, margen, la simulación y el orden por capital o margen) es **solo de
  Gerencia y administradores** (`dcasa.tablero._ve_utilidad`): al rol Marketing el servidor ni se lo manda (ni en la
  pantalla, ni en el Excel, ni en Brian) y la simulación se ignora aunque la pida a mano.
- Los cuatro cuadros de margen y rotación (`estrella`, `trafico`, `oportunidad`, `revisar`) son **solo con dinero**: el rol
  Marketing no los ve ni puede pedirlos (el servidor contesta con un error), y el Excel suyo no trae esa columna.
- La vendedora, Caja y Bodega no entran (`AccessError`; el Excel contesta 403).
- Lista blanca RPC: `dcasa.rotacion.datos` en `dcasa_base/tests/test_superficie_rpc.py`. El Excel es la ruta
  `/dcasa/rotacion/excel` (`controllers/rotacion.py`), que exige el mismo permiso antes de leer.

## Brian

`rotacion_de_inventario(grupo?, categoria?, orden?, rebaja?, limite?)` (lectura; Gerencia, administradores y rol
Marketing; el dinero, y con él los cuadros `estrella`, `trafico`, `oportunidad` y `revisar`, solo para los dos primeros). Ver [BRIAN.md](BRIAN.md) › «Marketing y fotos». Ejemplos: «¿qué lleva más
de 90 días sin venderse?» → `grupo=mas_de_90`; «¿cuánto tengo parado en Salas?» → `grupo=mas_de_90, categoria=Salas`;
«¿cuáles son mis productos ancla?» → `grupo=ancla`.

## Pruebas

- `tests/test_rotacion.py`: los grupos exactos (29, 30, 60, 90 y 200 días, y nunca), «o más», nota de crédito, agotados,
  lo nuevo (y que un ajuste no es una llegada), el pedido abierto, el ancla (con una cuenta exacta), la cobertura, las
  facturas por ventana, el capital contra «Valor del inventario», el costo faltante, la simulación (20 % y 50 %), los
  descuentos inválidos, categoría y texto, el orden, el tope de 100, los permisos (Marketing sin dinero; vendedora y
  bodega sin entrar) y el Excel (hojas, columnas, orden, total con fórmula, sin dinero para Marketing, nombre que parece
  fórmula).
- `tests/test_rotacion_navegador.py` (390×844 y 1440×900, Chrome): las 8 barras, buscar, cambiar de 90 a 30 días, la
  simulación con cifras exactas, «Bajo el costo», el enlace del Excel con lo que se ve, el scroll, sin scroll de costado;
  el rol Marketing llegando desde su botón y sin ver un solo dólar; y el Excel por la ruta (la vendedora recibe 403).

## Lo que no hace (todavía)

- No cambia precios ni crea promociones: **decide Gerencia** (la simulación solo cuenta). Para una campaña con los
  quietos, *Marketing › Camila › Crear campaña con estos* sigue donde estaba.
- Los cortes (30, 60, 90, 180) y el 80 % del ancla están en el código (`CORTES`, `PARETO`); si Gerencia pide otros, se
  cambian ahí y se prueba. El tiempo que tarda en llegar un pedido (3 a 4 meses) **no** entra en «días sin vender»: lo usa
  Reponer.
- No separa por almacén (bodega o tienda) ni por medida o color, ni compara contra el año pasado.
