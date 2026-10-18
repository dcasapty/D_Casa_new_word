# Programa de vendedores D'CASA (`dcasa_socios`)

Un programa **aparte de Socios**, hecho para quien vende por su cuenta: empleados de D'CASA o gente de
afuera. El cliente sigue ganando sus puntos de Socios como siempre; el vendedor gana **otros puntos, más
altos**, cuando alguien compra con su código. Los puntos de vendedor se cambian por **mercancía**.

> Las cifras de fábrica viven en [`puntos.json`](../addons/dcasa_socios/data/puntos.json) (sección `vendedores`,
> versión 5). Gerencia puede **ajustarlas desde Ajustes** sin programador (ver «Ajustar las cifras desde Ajustes»):
> el ajuste va encima de la fábrica, con versión y fecha, y solo rige hacia adelante. Este documento explica qué
> significan las cifras de fábrica. Si algo no cuadra, manda lo que dice Ajustes › Programa de vendedores (que
> arranca igual a `puntos.json` hasta que alguien lo cambie).

## En una frase

*Yo le doy mi código de vendedor a alguien; si compra en D'CASA con mi código y paga, gano puntos. Si yo
traje a otro vendedor, gano un poquito extra por lo que él venda (solo un nivel). Mis puntos los cambio por
una cama o lo que haya en el catálogo.*

## Cómo funciona, paso a paso

1. **Afiliar.** Solo **Gerencia o la caja** afilian (no hay auto-registro). En la ficha del contacto →
   pestaña **Vendedor D'CASA** → *Afiliar como vendedor*. Se pide cédula/RUC, celular y que la persona haya
   aceptado los términos. No cuesta nada, no hay que comprar mercancía y **afiliar no da puntos a nadie**.
   Puede ser empleado o gente de afuera. **En caja se afilia sin patrocinador**: quién patrocina a quién lo
   escribe solo Gerencia (una vez, para siempre), así un cajero no puede armarse su propia colmena.
2. **El código.** La persona recibe un código **VEN…** (y un enlace `dcasapty.com/v/VEN…`). Lo da a sus
   clientes. El cliente lo dice en la tienda (la caja lo anota en la cotización: campo *Vendedor*) o entra
   por el enlace en la tienda web.
3. **La venta.** Se factura como siempre. **Cuando la factura queda pagada**, Odoo calcula solo los puntos
   del vendedor. Si hay devolución (nota de crédito), los puntos se devuelven.
4. **Los puntos esperan 30 días** (60 las primeras 5 ventas de un vendedor nuevo). Se ven desde el primer día
   como *por liberar*, pero no se pueden canjear hasta pasada la ventana de devoluciones. Cada noche Odoo
   revisa si alguna factura dejó de estar pagada (contracargo, pago desconciliado) y, si es así, quita los puntos.
5. **Canjear.** El vendedor entra a `dcasapty.com/socios/vendedor` (con su celular y PIN de Socios), pide un
   premio, le sale un código de 72 horas y lo recoge en la tienda. Si no lo recoge, los puntos vuelven.
6. **Revender.** Lo que el vendedor canjeó es suyo: lo puede revender al precio que quiera (no se fija
   precio de reventa).

## Las cifras (versión 5)

| Qué | Cifra | Por qué |
|---|---|---|
| Comisión por vender | **Base: 4 puntos por cada $1** de venta neta (sin ITBMS, ya con descuentos) = 4 %. **Sube a 5 %, 6.5 % y 8 %** según lo vendido en los últimos 90 días (ver «La escalera») | La base es el piso que ya motiva; la escalera deja que quien vende de verdad llegue a un ingreso de oficio |
| ¿A quién se le paga la tasa completa? | Solo a la **primera compra de un cliente nuevo** | Es la venta que de verdad trajo el vendedor |
| Cliente que ya había comprado, o recompra de su cliente | **La mitad (2 %)** | Esas ventas casi seguro ya iban a ocurrir |
| El cliente queda ligado al vendedor | **12 meses**, no para siempre | Cubre el ciclo de compra de camas; no se paga eternamente por clientes de la casa |
| Patrocinio (un solo nivel) | **0.8 puntos por $1** de lo que venda cada directo (= 20 % de la comisión del directo) | No le resta nada al directo; lo paga D'CASA aparte |
| Patrocinio solo de... | Primera compra de clientes nuevos | Para no pagar por ventas que ya existían |
| Para cobrar patrocinio | El patrocinador vendió **a 2 clientes distintos** en el mes, y su patrocinio no pasa de **1 vez su propia comisión del mes** | Nadie vive solo de su colmena; cobrar sin vender no existe |
| Directos por patrocinador | **3** (después 5, máximo) | Evita concentración y aspecto de pirámide |
| Espera antes de poder canjear | **30 días** (60 en las primeras 5 ventas del vendedor) | Ventana de devoluciones; quien recién llega es el que más riesgo trae |
| Canje mínimo | **3,000 puntos** ($30): unas 6 primeras compras | Que el primer premio llegue pronto |
| Canjes por vendedor | **4 al mes** | El riesgo es el costo y el cupo; el tope mensual de puntos ya lo acota |
| Máximo por vendedor al mes | **20,000 puntos ($200)** en el escalón base; **30,000 / 50,000 / 90,000** en los escalones de arriba | Antifraude: la gente nueva tiene el tope más bajo; el alto se gana vendiendo 90 días |
| Freno de todo el programa | Lo entregado a **todos** los vendedores en 30 días no pasa del **3 %** de lo vendido en toda la tienda | Seguro contra una cifra mal puesta (antes 1.5 %, que un solo vendedor del escalón alto consumía casi entero) |
| Techo por factura | Entre cliente + vendedor + patrocinio no se pasa del **25 % de la ganancia** de esa factura | Si se pasa se recorta primero el patrocinio, luego la comisión; nunca los puntos del cliente |
| Efectivo | **No existe** | Solo mercancía; efectivo, más adelante y con abogado y contadora |

100 puntos = $1 al canjear (la misma escala de Socios).

### Un ejemplo con números

Una cama vendida en **$145 netos** (sin ITBMS) a un cliente nuevo que llegó con el código de Brian:

- Brian gana **580 puntos** ($5.80 nominales). Si Brian fue traído por Isabela, **Isabela gana 116 puntos**
  ($1.16), sin quitarle nada a Brian. La mamá de Isabela, si existe, no gana nada: es un solo nivel.
- El cliente gana sus puntos de Socios aparte (155).
- Si ese cliente vuelve dentro de 12 meses **sin decir el código**, Brian gana la mitad (290) y Isabela nada.
- Eso es en el **escalón base** (4 %). 10 primeras compras al mes = **5,800 puntos ($58)**. Una cama Full ($59.99)
  cuesta 6,419 puntos: unas **12 ventas**. En la base es un **ingreso complementario**, y así se le debe decir a la
  gente; quien vende mucho y sostiene el ritmo sube por la escalera (siguiente sección). Con los números de la
  tienda y solo la base, todo el programa reparte unos $390 nominales al mes si el 15 % de las ventas llegan con código.

## La escalera: de complemento a oficio (versión 5)

La dueña pidió que un vendedor de tiempo completo pudiera llegar a unos **$700 al mes en puntos** sin quemar
la utilidad de D'CASA. Con 4 % plano eso eran $17,500 netos al mes (121 ventas de $145: un tercio de todas las
facturas de la tienda, unas 366 al mes), y el tope de $200 lo impedía de todos modos. La solución no fue empezar
de nuevo: se dejó la base y se añadió una **escalera**. La tasa y el tope mensual suben según lo que el vendedor
**vendió en los últimos 90 días** (comisiones directas pagadas y no anuladas):

| Vendido en 90 días | Ganas por cada $1 | Tope del mes | Ventas de $145 al mes para sostenerlo |
|---|---|---|---|
| menos de $3,000 | 4 puntos (4 %) | 20,000 puntos ($200) | — |
| $3,000 o más | 5 puntos (5 %) | 30,000 ($300) | ~7 |
| $9,000 o más | 6.5 puntos (6.5 %) | 50,000 ($500) | ~21 |
| $18,000 o más | 8 puntos (8 %) | 90,000 ($900) | ~42 |

Se recalcula con cada venta y solo afecta ventas futuras. Quien deja de vender baja de escalón. El vendedor ve
su nivel y cuánto le falta para subir en su panel (`/socios/vendedor`) y en los términos.

**Cuánto gana** (clientes nuevos, ticket neto de $145, escalón ya alcanzado):

| Ventas al mes | Ganas (puntos) | Equivale a |
|---|---|---|
| 14 | 10,150 | $102 |
| 28 | 26,376 | $264 |
| 41 | 38,622 | $386 |
| **60 (~3 por día hábil)** | **69,600** | **$696** |
| 69 | 80,040 | $800 |

El escalón más alto se sostiene con unas 42 ventas al mes; los $700 llegan con unas 60. Llegar toma unos
**3 meses de ritmo constante** (el primer mes casi nunca llega). Con 4 % plano, los mismos $700 serían 121 ventas.

**El límite real es la demanda, no el programa.** 60 clientes nuevos al mes son el 16 % de las facturas que hoy
hace toda la tienda: caben pocos vendedores así a la vez (2 o 3). Y quien solo trae recompras gana la mitad.

### Qué le cuesta a D'CASA (y por qué se paga solo)

Los puntos de vendedor se pagan **en mercancía que cuesta menos que su precio**, y solo cuando la venta ya
se cobró y pasó la ventana de devoluciones. Costo real por escalón, **incluyendo los puntos de Socios del
cliente** (1.07 % del neto) y suponiendo que un punto de vendedor cuesta 70 % de su valor nominal (el punto de
la cama Full cuesta menos: costo $29.34 sobre precio $59.99):

| Escalón | Costo real sobre la venta neta | % del margen (35 % supuesto) | % del margen (44.6 % medido en el inventario) | La venta con código tiene que ser nueva al menos... |
|---|---|---|---|---|
| 4 % | 3.9 % | 11 % | 9 % | 11 % (9 %) de las veces |
| 5 % | 4.6 % | 13 % | 10 % | 13 % (10 %) |
| 6.5 % | 5.6 % | 16 % | 13 % | 16 % (13 %) |
| 8 % | 6.7 % | 19 % | 15 % | 19 % (15 %) |

Ejemplo del escalón más alto con 60 ventas de $145 (**$8,700 vendidos**): se entregan $696 nominales en puntos,
cuesta unos **$580 reales** (con los puntos de Socios del cliente) y a D'CASA le quedan unos **$2,500 a $3,300** de
ganancia después de pagar el programa, según el margen sea 35 % o 44.6 %. Esas ventas no existirían sin el vendedor:
**la regla es que el programa se paga si al menos una de cada cinco ventas con código es de alguien que no habría
comprado**, y por eso a quien ya compraba se le paga la mitad. **Supuestos honestos:** solo hay un costo de
producto cargado, así que se supone un margen de 35 % (el inventario sugiere 44.6 %); los premios solo pueden
costar 65 % de su precio o menos. Hay que cargar los costos del catálogo y verificar que el margen de lo vendido
con código sea 31 % o más.

**Rango de mercado.** Lo que encontré: los vendedores de mueblería cobran 4 % a 8 % de la venta, hasta 10 % en gama alta,
normalmente con sueldo base (fuente: página de carreras, no encuesta). La escalera cae dentro de ese rango.

**Prometer poco.** En las ventas directas la mayoría gana muy poco (la FTC halló en 2024 que la gran mayoría gana $1,000
al año o menos). La escalera se muestra tal cual; **no se promete un ingreso**.

### Qué le cuesta a D'CASA en la base (escalón de 4 %)

En el escenario esperado el programa consume cerca del **7 %
de la ganancia** de lo vendido con código; en el peor caso razonable, cerca del **14 %**.

## Qué lo protege (por qué no se cae y no es pirámide)

- **Nada se paga por reclutar.** Afiliar no da puntos, ni cuota, ni kit, ni compra mínima. El patrocinio sale
  de ventas reales a clientes finales.
- **Solo ventas cobradas.** Los puntos nacen de una factura pagada; una devolución los deshace con un
  asiento contrario (el libro no se edita ni se borra; el saldo es la suma del libro).
- **Un nivel.** Cada vendedor tiene un solo patrocinador, escrito una vez, sin ciclos, y nada paga por debajo
  de los directos.
- **Sin autocompras ni anillos.** Si el cliente es el mismo vendedor (misma ficha, o mismo celular/correo/cédula),
  su patrocinador o uno de sus directos, **o cualquier otro vendedor afiliado**, no hay puntos de vendedor
  (el cliente sí gana los suyos). La caja tampoco puede ponerse a sí misma como vendedora de una factura que
  ella registra.
- **«Cliente nuevo» se prueba, no se declara.** Solo es nuevo quien se puede identificar (celular, cédula o
  correo) y no tiene ninguna compra pagada antes, ni él ni otra ficha con los mismos datos (los clientes
  del sistema anterior cuentan como existentes). Un cliente sin datos se trata como existente (paga la mitad).
- **Si un pago se revierte, los puntos se van.** No hace falta una nota de crédito: la revisión nocturna
  los quita.
- **Un tope nunca hace fallar una venta.** Si algo se pasa, se recorta la comisión, nunca se frena el cobro.
- **Borrar un borrador no se queda trabado por una comisión.** Ver «Qué pasa con la comisión si se borra un
  borrador de factura» más abajo.
- **Varios frenos en capas:** techo por factura, máximo por vendedor al mes, patrocinio contra la comisión
  propia, freno de todo el programa en 30 días.
- **El código no da descuento.** La comisión sale del precio realmente cobrado.
- **Atribución firme.** El vendedor de una factura no se cambia sin que Gerencia lo haga, con motivo; el
  código de otro no le quita un cliente ligado.

## Qué pasa con la comisión si se borra un borrador de factura

Igual que con los puntos del cliente (ver [SOCIOS.md](SOCIOS.md)): una factura de prueba o equivocada que ya dio
comisión se puede **devolver a borrador y eliminar**, sin archivarla.

- Al volver a borrador, la comisión del vendedor (y el patrocinio de su patrocinador) se **anulan con un asiento
  contrario** en el libro de vendedores. El saldo del vendedor es la suma del libro y no queda inflado: la
  comisión y su reverso se anulan entre sí.
- Al eliminar, la comisión anulada se queda en *Socios → Comisiones* (Anulada, con su número y su motivo, sin
  factura enlazada). El libro no pierde ni una fila.
- Una comisión anulada **no gasta** ningún tope: ni el del mes del vendedor, ni el del patrocinio, ni el techo
  de la venta ni el freno global. La siguiente venta real se calcula como si la deshecha no hubiera existido.
- Si la comisión ya tenía una devolución parcial (nota de crédito), al anularla se deshace también lo que esa
  devolución había descontado: el vendedor no queda con puntos de menos.
- Si todavía quedaba una comisión activa al borrar (no es lo normal), el borrado la anula con su asiento
  contrario («Se eliminó la factura …») antes de seguir. Una factura publicada sigue sin poder borrarse.
- Nada se paga por afiliar ni por reclutar: esto no cambia. Si la misma factura vuelve a quedar pagada después de
  haberse corregido, da su comisión **una sola vez** (nunca dos comisiones activas de la misma factura); una
  anulada por devolución total, por pago revertido o a mano no se reabre.

## Dónde se ve en Odoo

Menú **Socios**: *Vendedores* (lista y afiliación), *Comisiones* (cada comisión con su motivo: pagada,
recortada, o por qué no se pagó, y con qué versión de las reglas se pagó), *Canjes de vendedores*
(entregar/cancelar), *Libro de vendedores* y *Historial de reglas* (solo Gerencia: quién cambió qué y cuándo).
En **Reportes**: *Costo del programa de vendedores* y *Pasivo de vendedores*. En **Configuración**:
*Ajustes del programa de vendedores* (las cifras, ver abajo) y *Premios para vendedores* (se crean con su costo
real; no pueden pedir menos puntos de lo que cuestan).

Brian entiende: consultar un vendedor, resumen del programa (Gerencia), afiliar, suspender, reactivar y
ajustar puntos (los últimos, con confirmación y motivo).

## Ajustar las cifras desde Ajustes

La dueña (y Gerencia) cambia los porcentajes y demás cifras **sin programador y sin despliegue**. `puntos.json` sigue
siendo la **fábrica**: lo que dice ahí rige mientras nadie ajuste nada, y nunca se pierde ni se edita desde la pantalla.
Los ajustes son una **capa encima**.

### Cómo se usa (paso a paso)

1. Entra a **Socios › Configuración › Ajustes del programa de vendedores** (Gerencia). Los administradores del sistema
   también lo ven en **Ajustes › Programa de vendedores**: es exactamente lo mismo.
2. Arriba ves **qué reglas rigen ahora** (fábrica o la versión tal, desde qué día y quién la guardó).
3. Cambia lo que quieras. Las cifras vienen en palabras sencillas: **porcentajes**, **dólares** (los topes y mínimos de
   puntos también van en dólares; el sistema los pasa a puntos con «100 puntos = $1») y **días/meses**.
4. Mientras escribes, el cuadro **«Lo que cuesta y lo que vas a cambiar»** se actualiza solo y te dice:
   - *«Con estas cifras el programa cuesta hasta X % de la venta neta»*: la venta que más cuesta (cliente nuevo, en el
     escalón más alto, con patrocinio y con los puntos que gana el cliente). Es (comisión más alta + patrocinio) × 0.7
     (lo que de verdad cuesta un punto de vendedor, ver `pesoDelPuntoDeVendedor`) + los puntos de Socios del cliente.
     Con las cifras de fábrica: 7.23 %. (La tabla de más arriba no suma el patrocinio, por eso allí el escalón más alto
     sale 6.7 % y 19 %; la pantalla cuenta el peor caso.)
   - *«Para que se pague solo, al menos Y % de lo vendido con código tiene que ser de clientes que no habrían
     comprado»*: es el punto de equilibrio, costo ÷ ganancia supuesta (35 %, `techos.margenBrutoSupuestoPorcentaje`).
     Con las cifras de fábrica: 20.7 %.
   - **Lo que no se puede guardar todavía** (en rojo), con lo que hay que corregir.
   - **Lo que vas a cambiar**, con el valor de antes y el de ahora.
5. Si quieres, escribe el **motivo** (queda en el historial) y pulsa **Guardar**. Si algo no cumple los límites, **no
   se guarda nada** y el mensaje dice qué corregir. Si todo está bien, nace una **versión nueva**.
6. **Volver a los valores de fábrica**: botón en la misma pantalla. Crea una versión nueva igual a `puntos.json`; no
   borra nada del historial.

### Qué se puede ajustar

| Bloque | Cifras |
|---|---|
| **Programa** | Encendido / apagado. Motivo del cambio. |
| **Comisión y escalera** | Comisión base (%); la escalera (hasta 5 escalones: cuánto hay que vender, cuánto gana y su tope del mes) y el tope del mes del escalón base; días que se miran para el escalón; venta mínima que da comisión; cuánto paga la recompra de su cliente y el cliente que ya compraba (% de la comisión); meses que el cliente queda ligado al vendedor |
| **Patrocinio** | Patrocinio (%); vendedores que puede patrocinar cada uno; clientes que debe atender el patrocinador en el mes; tope del patrocinio (veces su comisión propia del mes); tope de patrocinio al mes (en dólares, 0 = sin tope) |
| **Retención** | Días de espera antes de poder canjear; cuántas primeras ventas esperan más y cuántos días |
| **Límites de seguridad** | Techo de costo por venta (%); freno de todo el programa (%) |
| **Canjes** | Canje mínimo (en dólares); horas que dura el código; canjes por vendedor al mes |

**Lo que NO se ajusta desde Ajustes** (cambia solo con el programador, en `puntos.json`, subiendo la versión):

- **Canje de externos y canje en efectivo**: la pantalla los muestra apagados, de solo lectura, con la nota *«Apagado
  hasta el dictamen del abogado y la contadora»*. El servidor los ignora aunque alguien intente mandarlos.
- Lo antifraude y el diseño: nada por reclutar, compras dentro de la colmena, patrocinio solo de clientes nuevos,
  cuándo paga la comisión, base de cálculo, el peso del punto de vendedor (70 %) y el margen supuesto (35 %).
- Todo lo de Socios (puntos del cliente, referidos, cumpleaños, 100 puntos = $1).

### Límites duros (lo que nunca se deja guardar)

Los **límites de negocio** salen de las propias cifras del programa; los de **sentido común** (contra un cero de más)
están en `models/reglas_ajustes.py` (`CAMPOS`).

| Qué | Límite |
|---|---|
| Cualquier comisión (base o de escalón) | Mayor que 0, nunca por encima del **techo por venta** |
| Patrocinio | No mayor que la comisión base |
| Una sola venta | (comisión más alta + patrocinio) × 0.7 + puntos del cliente **no puede pasar del techo por venta** |
| Techo por venta | Mayor que 0 y no mayor que la **ganancia supuesta** (35 %) |
| Freno de todo el programa | Mayor que 0, no mayor que el techo por venta |
| La escalera | Cada escalón empieza más arriba que el anterior, paga más y tiene un tope igual o mayor; máximo 5; un escalón a medias no se guarda (déjalo todo en 0 para no usarlo) |
| Porcentajes | Entre 0 y 100 |
| Días de la escalera | 1 a 365 |
| Días de espera / de las primeras ventas | 0 a 365; las primeras ventas no esperan menos que las demás |
| Meses de vínculo | 0 a 60 (0 = el cliente no se liga) |
| Vendedores por patrocinador | 1 a 5 (el máximo absoluto de `puntos.json`) |
| Horas del código / canjes al mes | 1 a 720 / 1 a 100 |
| Dólares | Venta y canje mínimos hasta $1,000; topes del mes hasta $10,000; lo que hay que vender para un escalón hasta $1,000,000 |
| Siempre | Enteros donde van enteros; nada negativo; una cifra que falta en `puntos.json` se dice, no se rellena a ojo |

### Solo hacia adelante (la regla de oro)

- Cada cambio guardado es una **versión nueva** (`dcasa.vend.reglas`) con **fecha-hora de vigencia**: rige desde que se
  guarda, nunca antes (el sistema rechaza una fecha pasada).
- **Lo ya acreditado no se recalcula jamás**: las comisiones guardan lo que pagaron, la versión de `puntos.json` y el
  número del ajuste con que se pagaron (campo «Ajuste de Gerencia» de la comisión); el libro de puntos es inmutable y
  no se toca; la ventana de devoluciones ya quedó escrita en cada asiento.
- Una venta usa las reglas que rigen **cuando se paga la factura**.
- **Los meses del vínculo cliente-vendedor**: un cambio vale para los clientes que se liguen después; los que ya estaban
  ligados conservan el plazo con que se ligaron.
- Una cifra que Gerencia deja igual a la de fábrica deja de ser un ajuste: vuelve a seguir a `puntos.json`. Los
  ajustes se acumulan: cada versión dice todo lo que está cambiado frente a la fábrica.
- Si dos personas tienen la pantalla abierta a la vez, la segunda que guarda recibe un aviso y no pisa el cambio de la
  primera. Si `puntos.json` sube de versión después de un ajuste, la pantalla avisa.

### El historial

**Socios › Historial de reglas** (solo Gerencia y administradores, solo lectura): una fila por cambio, con la fecha
desde la que rige, quién lo guardó, el motivo, y por cada cifra el valor de **antes → ahora**. No se edita ni se
borra: un error se corrige guardando otro cambio, y *Volver a los valores de fábrica* es otro cambio más.

### Qué ve el vendedor

El panel del vendedor y la página de términos (`/vendedores/terminos`) leen las **mismas reglas que se pagan** (fábrica
más ajustes vigentes), y al pie de los términos dicen con qué versión están. Lo que el vendedor lee coincide con lo que
se le paga.

### Permisos y seguridad

- Solo **Gerencia** (`dcasa_base.group_gerencia`) y los **administradores** del sistema leen y cambian los ajustes y el
  historial; una vendedora ni lo ve en el menú ni lo abre por ninguna otra puerta. El servidor vuelve a comprobar el
  permiso antes de leer o escribir; nada que venga del navegador es de confianza (se vuelve a convertir y a validar
  todo en el servidor).
- Gerencia no entra a Ajustes de Odoo (ahí hay mucho más que esto): tiene su propia pantalla igual (Socios ›
  Configuración). El bloque dentro de Ajustes es para administradores.
- Si leer los ajustes fallara (una fila dañada), **la venta se cobra igual**: rige la versión anterior o la fábrica y
  queda escrito en el registro.

## Interruptores y cómo cambiar las reglas

- **Apagar todo:** Ajustes › Programa de vendedores › *Programa encendido* (o `vendedores.programaActivo: false` en la
  fábrica). No se acredita nada y las ventas siguen igual.
- **Canje de externos: APAGADO** (`canje.externosHabilitado: false`). Los puntos de un externo **sí se
  acumulan y no se pierden**, pero no pueden canjear hasta que el abogado revise el contrato. Los empleados
  sí canjean. Cuando llegue el visto bueno: lo cambia el programador a `true` en `puntos.json`, sube la versión y
  despliega (no se enciende desde Ajustes).
- **Cambiar una cifra de rutina:** desde Ajustes (arriba). **Cambiar la fábrica:** se edita `puntos.json`, se sube la
  `version` y se despliega. Las comisiones viejas guardan la versión con que se calcularon.
- **Una cifra en `null`** hace que el programa se niegue a acreditar (queda escrito «falta una cifra»).

## Cómo se cuida la escalera (y cuándo se baja)

La escalera ya está encendida, pero se vigila cada mes. Si el semáforo se pone amarillo, se **baja un escalón o dos
hacia adelante** (desde Ajustes › Programa de vendedores, o en la fábrica subiendo la versión y desplegando; nunca
retroactivo). Lo que más importa vigilar es la
**incrementalidad**: el escalón de 8 % solo se paga solo si al menos 19 % de lo vendido con código es de clientes que no
habrían comprado (15 % con el margen medido). Antes de la versión 5 se pedía además que los costos del catálogo estuvieran
cargados, que el abogado y la contadora no tuvieran objeciones y que la incrementalidad fuera de 20 % o más; **esas
condiciones siguen siendo la meta** y se revisan al medir, pero ya no son un candado para empezar con la escalera.

### Semáforo del programa

| Qué mirar | Verde | Amarillo (bajar la escalera, no afiliar más) | Rojo (congelar afiliaciones, revisar con abogado y contadora) |
|---|---|---|---|
| Costo real sobre la ganancia atribuida | hasta 20 % | más de 20 % | más de 30 % |
| Incrementalidad (parte de lo vendido con código que es de clientes nuevos) | 30 % o más | menos de 25 % dos meses | menos de 20 % dos meses |
| Margen de lo atribuido | 35 % o más | entre 31 y 35 % (no se sube) | menos de 31 % |
| Ventas con código sobre las facturas | menos de 35 % | 35 % (el freno de 3 % corta cerca) | 50 % |
| Devolución de ventas con código | hasta 3 % | más de 5 % | vendedor con más de 8 %: en revisión |
| Pasivo de puntos sobre 90 días de venta | menos de 1 % | más de 3 % | más de 5 % |

Con **negro** (objeción escrita del abogado, la DGI o un fraude confirmado) se suspende la emisión de
puntos nuevos; lo ya acreditado se respeta y las ventas nunca se bloquean. Los reportes de Odoo dan la
mayoría de estas cifras; la revisión es **mensual y a mano** (no hay alertas automáticas todavía).

## Pendientes legales y contables (no son código)

Antes de pagar o dejar canjear a un externo:

- **Abogado laboral:** contrato tipo de agente/comisionista independiente (sin horario ni exclusividad, libre
  de fijar precio de reventa) y riesgo de relación laboral encubierta; que el diseño no encaje en captación
  masiva ni multinivel; términos públicos frente a la Ley 45 de 2007; Ley 81 de 2019 (consentimiento
  específico y revocable del vínculo cliente-vendedor, aviso de privacidad); vencimiento de puntos;
  garantía frente al comprador de una reventa.
- **Contadora / DGI:** cómo se factura el canje (por ahora, **al valor de lista con ITBMS**), retención de ISR
  a independientes locales, si las comisiones integran el salario de los empleados (décimo tercer mes,
  vacaciones, CSS; mientras tanto se tratan como salario variable), tratamiento contable de la provisión de
  puntos.
- **Datos propios:** cargar el costo de todo el catálogo; confirmar la política real de devolución (si es
  más larga que 30 días, la ventana se iguala) y la tasa de devolución real.

## Lo que dijo el equipo rojo (y lo que ya se hizo con eso)

Un equipo de agentes buscó fallas al consenso. Su veredicto: *las cifras aguantan; lo que se rompe es lo que las
rodea*. Ya está hecho: definición firme de «cliente nuevo», bloqueo de compras de cualquier vendedor, patrocinador
solo por Gerencia, retención de 60 días para las primeras ventas, reversa nocturna de pagos deshechos, costo del
punto de vendedor subido a 70 %. **Falta, y conviene antes de abrirlo a externos:** confirmar cada venta con
código por WhatsApp (el control más valioso contra testaferros), una segunda firma de la dueña para liberar
excedentes y reasignaciones, un trato especial para empleados en mostrador (ver «Decisiones tuyas»), cuentas
contables separadas para los puntos y datos de costo cargados para al menos el 80 % de la venta.

## Decisiones tuyas (no las tomé yo)

1. **Empleados en el mostrador.** Si una vendedora de la tienda ya cobra sueldo por atender a los clientes que
   llegan solos, ¿debe ganar puntos cuando teclea su propio código en esa venta? Hoy no (el sistema lo bloquea
   si ella misma registra la venta), pero si otra persona registra la venta con el código de ella, sí paga.
   Lo más sano: empezar solo con vendedores de afuera y empleados que traen clientes de fuera de la tienda.
2. **Encender el canje de externos** (`canje.externosHabilitado`) solo después del visto bueno del abogado.
3. **Cómo se le paga a quien vive de esto.** Un vendedor de tiempo completo necesita efectivo, y con puntos solo en
   mercancía tendría que revender para comer. Si trabaja a tiempo completo solo para D'CASA se parece mucho a un
   empleado: el abogado y la contadora deben decir si va con **sueldo base más comisión** (como pagan las mueblerías)
   o como **agente independiente con comisión en efectivo**. El interruptor de efectivo ya existe
   (`canje.efectivoHabilitado`), apagado hasta ese dictamen. **2026-10-18, la gerencia:** el canje en efectivo queda
   descartado; el canje es en producto (ver [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md), J3).
4. **Cuántos vendedores de tiempo completo.** 60 ventas nuevas al mes por vendedor son el 16 % de lo que vende hoy toda
   la tienda: caben 2 o 3 a la vez. Más vendedores así piden más tráfico, y el freno de 3 % corta cerca de ahí.

## Lo que NO está hecho todavía (para no engañarnos)

- Líneas con descuento manual mayor a 5 %, en promoción o de margen menor a 31 % **no se excluyen una a
  una**: la comisión sale del neto realmente cobrado (el descuento ya baja la base) y el techo por factura
  cuida el costo. Excluir por línea queda para cuando estén los costos cargados.
- El tope mensual por vendedor (20,000 en la base, hasta 90,000 en el escalón alto) **recorta**; el excedente no queda
  en una cola de revisión: Gerencia puede acreditarlo con *Ajustar puntos* y motivo.
- La escalera cuenta lo vendido en 90 días con **todas** las comisiones directas pagadas (también las de recompra, que
  pagan la mitad): no distingue clientes nuevos de recompras para subir de escalón. Se puede afinar con datos.
- No hay tope por colmena (40,000) ni la regla «80 % de las ventas de la colmena a no afiliados»; los reportes
  de comisiones permiten revisarlo a mano.
- No hay alertas automáticas semanales; los reportes (pivotes) están, la revisión es de Gerencia.
- El canje de más de 20,000 puntos no pide aprobación aparte (se entrega en caja, donde Gerencia puede frenarlo).
- No hay vencimiento de puntos (queda para después de la revisión legal).
- La herramienta de Brian `resumen_programa_vendedores` todavía lee la fábrica (`puntos.json`) para decir si el programa
  está encendido: debe leer las reglas vigentes (`dcasa.vend.reglas._vigentes()`), porque desde Ajustes se puede apagar.
- La ventana de 30 días cuenta desde el pago; la regla «o la entrega confirmada» no está.
- La investigación de mercado se hizo con búsqueda web (sin poder abrir páginas completas) y un modelo
  numérico propio con datos reales de la tienda; es una base seria, no un estudio auditado.

## Técnico

- Módulo `dcasa_socios`. Reglas puras en `models/reglas_vendedores.py` (sin base de datos, con pruebas);
  libro `dcasa.vend.movimiento` (inmutable); comisiones `dcasa.vend.comision` (una por factura y vendedor,
  idempotentes, con la versión de reglas y el motivo); canjes `dcasa.vend.canje`; extensión de
  `dcasa.premio` (`para_vendedores`).
- Se dispara en `account.move._invoice_paid_hook`, dentro de un savepoint: un error del programa se
  registra y **nunca** impide el cobro.
- Ficha única: el vendedor es el mismo `res.partner` que el cliente y el socio (llave = celular). Campos
  `dcasa_vendedor_*` y `dcasa_vend_*`.
- Web: `/v/<código>`, `/socios/vendedor`, `/vendedores/terminos` (generado desde las reglas vigentes).
- Ajustes de Gerencia: la lógica pura está en `models/reglas_ajustes.py` (`CAMPOS`, conversiones, `reglas_efectivas`,
  `calcular_cambio`, `problemas_de_las_cifras`, `costo_del_programa`); las versiones en `dcasa.vend.reglas`
  (`models/vend_reglas.py`; `_vigentes()` es lo que lee TODO lo de vendedores, y nunca falla); la pantalla en
  `models/vend_ajustes.py` (un molde con los campos que usan `res.config.settings` y `dcasa.vend.ajustes`, la pantalla
  de Gerencia) y `views/vendedores_ajustes_views.xml`.
- Pruebas: `tests/test_vendedores_reglas.py`, `test_vendedores.py`, `test_vendedores_web.py`,
  `test_vendedores_ajustes_reglas.py` (la capa de ajustes en puro), `test_vendedores_ajustes.py` (versiones, pantalla,
  permisos, vistas y web) y `dcasa_brian/tests/test_vendedores_brian.py`.
- Datos personales: ninguno en el repositorio; solo viven dentro de Odoo.
