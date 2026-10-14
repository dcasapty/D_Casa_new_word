# Programa de vendedores D'CASA (`dcasa_socios`)

Un programa **aparte de Socios**, hecho para quien vende por su cuenta: empleados de D'CASA o gente de
afuera. El cliente sigue ganando sus puntos de Socios como siempre; el vendedor gana **otros puntos, más
altos**, cuando alguien compra con su código. Los puntos de vendedor se cambian por **mercancía**.

> Las cifras viven en [`puntos.json`](../addons/dcasa_socios/data/puntos.json) (sección `vendedores`,
> versión 4). Este documento explica qué significan. Si algo no cuadra, manda `puntos.json`.

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

## Las cifras de arranque (Fase 1)

| Qué | Cifra | Por qué |
|---|---|---|
| Comisión por vender | **4 puntos por cada $1** de venta neta (sin ITBMS, ya con descuentos) = 4 % | El piso que todavía motiva; subir después es fácil, bajar es perder la confianza |
| ¿A quién se le paga la tasa completa? | Solo a la **primera compra de un cliente nuevo** | Es la venta que de verdad trajo el vendedor |
| Cliente que ya había comprado, o recompra de su cliente | **La mitad (2 %)** | Esas ventas casi seguro ya iban a ocurrir |
| El cliente queda ligado al vendedor | **12 meses**, no para siempre | Cubre el ciclo de compra de camas; no se paga eternamente por clientes de la casa |
| Patrocinio (un solo nivel) | **0.8 puntos por $1** de lo que venda cada directo (= 20 % de la comisión del directo) | No le resta nada al directo; lo paga D'CASA aparte |
| Patrocinio solo de... | Primera compra de clientes nuevos | Para no pagar por ventas que ya existían |
| Para cobrar patrocinio | El patrocinador vendió **a 2 clientes distintos** en el mes, y su patrocinio no pasa de **1 vez su propia comisión del mes** | Nadie vive solo de su colmena; cobrar sin vender no existe |
| Directos por patrocinador | **3** (después 5, máximo) | Evita concentración y aspecto de pirámide |
| Espera antes de poder canjear | **30 días** (60 en las primeras 5 ventas del vendedor) | Ventana de devoluciones; quien recién llega es el que más riesgo trae |
| Canje mínimo | **3,000 puntos** ($30): unas 6 primeras compras | Que el primer premio llegue pronto |
| Canjes por vendedor | **2 al mes** | El riesgo es el costo y el cupo |
| Máximo por vendedor | **20,000 puntos al mes** | Antifraude |
| Freno de todo el programa | Lo entregado a **todos** los vendedores en 30 días no pasa del **1.5 %** de lo vendido en toda la tienda | Seguro contra una cifra mal puesta |
| Techo por factura | Entre cliente + vendedor + patrocinio no se pasa del **25 % de la ganancia** de esa factura | Si se pasa se recorta primero el patrocinio, luego la comisión; nunca los puntos del cliente |
| Efectivo | **No existe** | Solo mercancía; efectivo, más adelante y con abogado y contadora |

100 puntos = $1 al canjear (la misma escala de Socios).

### Un ejemplo con números

Una cama vendida en **$145 netos** (sin ITBMS) a un cliente nuevo que llegó con el código de Brian:

- Brian gana **580 puntos** ($5.80 nominales). Si Brian fue traído por Isabela, **Isabela gana 116 puntos**
  ($1.16), sin quitarle nada a Brian. La mamá de Isabela, si existe, no gana nada: es un solo nivel.
- El cliente gana sus puntos de Socios aparte (155).
- Si ese cliente vuelve dentro de 12 meses **sin decir el código**, Brian gana la mitad (290) y Isabela nada.
- 10 primeras compras al mes = **5,800 puntos ($58)**. Una cama Full ($59.99) cuesta 6,419 puntos: unas
  **12 ventas**. Es **ingreso complementario, no un sueldo**; así se le debe decir a la gente. Con los
  números de la tienda, todo el programa reparte unos $390 nominales al mes si el 15 % de las ventas llegan
  con código.

### Qué le cuesta a D'CASA

Los puntos de vendedor se pagan **en mercancía que cuesta menos que su precio**, y solo cuando la venta ya
se cobró y pasó la ventana de devoluciones. En el escenario esperado el programa consume cerca del **7 %
de la ganancia** de lo vendido con código; en el peor caso razonable, cerca del **14 %**; el límite que se
puso es 20 %. **Supuestos honestos:** solo hay un costo de producto cargado, así que se supone un margen de
35 %; los premios solo pueden costar 65 % de su precio o menos. Hay que cargar los costos del catálogo y
verificar que el margen de lo vendido con código sea 31 % o más (ver «Antes de subir a Fase 2»).

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
- **Varios frenos en capas:** techo por factura, máximo por vendedor al mes, patrocinio contra la comisión
  propia, freno de todo el programa en 30 días.
- **El código no da descuento.** La comisión sale del precio realmente cobrado.
- **Atribución firme.** El vendedor de una factura no se cambia sin que Gerencia lo haga, con motivo; el
  código de otro no le quita un cliente ligado.

## Dónde se ve en Odoo

Menú **Socios**: *Vendedores* (lista y afiliación), *Comisiones* (cada comisión con su motivo: pagada,
recortada, o por qué no se pagó), *Canjes de vendedores* (entregar/cancelar), *Libro de vendedores*.
En **Reportes**: *Costo del programa de vendedores* y *Pasivo de vendedores*. En **Configuración**:
*Premios para vendedores* (se crean con su costo real; no pueden pedir menos puntos de lo que cuestan).

Brian entiende: consultar un vendedor, resumen del programa (Gerencia), afiliar, suspender, reactivar y
ajustar puntos (los últimos, con confirmación y motivo).

## Interruptores y cómo cambiar las reglas

- **Apagar todo:** `vendedores.programaActivo: false`. No se acredita nada y las ventas siguen igual.
- **Canje de externos: APAGADO** (`canje.externosHabilitado: false`). Los puntos de un externo **sí se
  acumulan y no se pierden**, pero no pueden canjear hasta que el abogado revise el contrato. Los empleados
  sí canjean. Cuando llegue el visto bueno: cambiar a `true`, subir la versión y desplegar.
- **Cambiar una cifra:** se edita `puntos.json`, se sube la `version` y se despliega. Las comisiones viejas
  guardan la versión con que se calcularon.
- **Una cifra en `null`** hace que el programa se niegue a acreditar (queda escrito «falta una cifra»).

## Antes de subir de fase (5 % y 1 %)

No se sube nada hasta cumplir **todo** esto (el 4 % base no baja en los primeros 6 meses salvo alerta roja):

1. Costos del catálogo cargados y margen de lo vendido con código **35 % o más**.
2. **Incrementalidad 20 % o más** dos meses seguidos (que de lo vendido con código, la parte de clientes
   nuevos sea esa).
3. Devolución de lo vendido con código **3 % o menos**.
4. Costo real del programa **menos de 10 %** de la ganancia atribuida.
5. Revisión escrita del abogado y de la contadora, sin objeciones.

Entonces: 5 % (solo para quien venda $2,000 netos o más en 90 días; en `puntos.json`, `escalones`), patrocinio
1 %, hasta 5 directos, máximo 30,000 puntos al mes, freno 2 %. Siempre hacia adelante, nunca retroactivo.

### Semáforo del programa

| Qué mirar | Verde | Amarillo (volver a tasas de Fase 1, no afiliar más) | Rojo (congelar afiliaciones, revisar con abogado y contadora) |
|---|---|---|---|
| Costo sobre la ganancia atribuida | hasta 10 % | más de 12 % | más de 20 % |
| Incrementalidad | 20 % o más | menos de 17 % dos meses | menos de 10 % dos meses |
| Margen de lo atribuido | 35 % o más | entre 31 y 35 % (no se sube) | menos de 31 % |
| Ventas con código sobre las facturas | menos de 20 % | 20 % | 30 % |
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
3. **Subir de fase** (5 %) solo con las condiciones de arriba.

## Lo que NO está hecho todavía (para no engañarnos)

- Líneas con descuento manual mayor a 5 %, en promoción o de margen menor a 31 % **no se excluyen una a
  una**: la comisión sale del neto realmente cobrado (el descuento ya baja la base) y el techo por factura
  cuida el costo. Excluir por línea queda para cuando estén los costos cargados.
- Los 20,000 puntos al mes por vendedor **recortan**; el excedente no queda en una cola de revisión: Gerencia
  puede acreditarlo con *Ajustar puntos* y motivo.
- No hay tope por colmena (40,000) ni la regla «80 % de las ventas de la colmena a no afiliados»; los reportes
  de comisiones permiten revisarlo a mano.
- No hay alertas automáticas semanales; los reportes (pivotes) están, la revisión es de Gerencia.
- El canje de más de 20,000 puntos no pide aprobación aparte (se entrega en caja, donde Gerencia puede frenarlo).
- No hay vencimiento de puntos (queda para después de la revisión legal).
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
- Web: `/v/<código>`, `/socios/vendedor`, `/vendedores/terminos` (generado desde `puntos.json`).
- Pruebas: `tests/test_vendedores_reglas.py`, `test_vendedores.py`, `test_vendedores_web.py` y
  `dcasa_brian/tests/test_vendedores_brian.py`.
- Datos personales: ninguno en el repositorio; solo viven dentro de Odoo.
