# La comisión del sitio web (`dcasa_comision_web`)

Decisión de Gerencia del 2026-11-19. Diseño y razones: [PLAN_COMISION_WEB.md](PLAN_COMISION_WEB.md). Este documento
explica **cómo funciona hoy**, en palabras para administración.

> **El módulo nace vacío.** No trae ningún porcentaje, ninguna tarifa ni ninguna persona. Mientras Gerencia no guarde la
> primera versión de las reglas, el sistema **solo mide** las ventas por internet. Nada se paga solo.

## En una frase

Cada venta que sale del sitio web (y quedó pagada por completo) se mide como las de una sucursal; con un porcentaje fijo
de esas ventas, y una tarifa fija por mantener la plataforma, se le va anotando a cada persona lo que le toca; cuando
administración quiere, arma una **liquidación** del periodo que elija, alguien la aprueba y se paga.

## Dónde está

En la app **Nómina › Comisión del sitio web** (solo Gerencia y quien administra la nómina; el administrador técnico solo,
la vendedora, Caja y Marketing no lo ven ni por enlace):

| Pantalla | Para qué |
|---|---|
| **Ventas del sitio** | Una fila por factura del sitio pagada por completo: cómo llegó, cómo pagó, lo vendido, envío, devoluciones, base y comisión. Lista, **gráfico y tabla por mes** (para medir el sitio como una sucursal) y **Excel** con «Exportar». |
| **Liquidaciones** | Armar, aprobar y marcar como pagada la comisión de un periodo. |
| **Quiénes reciben** | La lista de la versión que rige hoy, con el reparto y lo que se le debe a cada quien. Desde aquí se cambia la lista. |
| **Libro** | Todo lo que se ha anotado, por persona. No se edita ni se borra. |
| **Reglas** | Las versiones: porcentaje, tarifa fija, cómo se arma la base y quiénes reciben. Una que todavía no rige y se puso mal se **anula** con su motivo. |
| **Pedidos de la página para revisar** (solo Gerencia) | Los pedidos de la página que una vendedora llevó (aunque sea con un mensaje) y los carritos que abrió alguien del equipo: es la **vigilancia**, no un freno. |

En **Libro**, el botón **Anotar un ajuste** corrige lo que el sistema no puede ver solo (algo pagado de más, una tarifa de
medio periodo): monto con signo y **motivo obligatorio**; queda una fila nueva con tu nombre.

## Qué es una «venta online»

Hay **una sola definición** en todo el sistema (`dcasa_base/models/venta_online.py`). La usan la comisión del sitio, el bono
por meta, el Inicio de la vendedora y el programa de vendedores. En una línea (decisión del 2026-11-20): **un pedido que
nació por un flujo digital real (el carrito de la página, Andrés o la cotización de Juan) y al que ninguna vendedora llevó
(no le escribió al cliente por el chat de Juan en los 30 días anteriores)**. Todo lo demás (mostrador, pedido tecleado,
lo que una vendedora atendió) no es venta online.

| Caso | ¿Es venta online? | Cómo se sabe |
|---|---|---|
| Alguien compra en la página web | **Sí** | El pedido nació en la tienda en línea: lo marca **el carrito real de la tienda** (`website._create_cart`), una sola vez (`dcasa_nacio_en_web`), y anota quién lo abrió (`dcasa_creada_por_id`). |
| Alguien cotiza en la página y llega a la tienda con esa cotización («Pago en la tienda», apartado) | **Sí** | Es el mismo pedido: nació en la página. |
| Lo que **Andrés** (el chat de la tienda) vende y el cliente paga **sin más intervención** | **Sí** | El carrito de Andrés es el carrito real (nace por `website._create_cart`); `dcasa_via_andres` solo dice por dónde llegó la venta, **ya no fuerza** que sea online. |
| Andrés pasa al cliente a una persona (WhatsApp) y **la vendedora lo atiende y cierra** | **No** | Se comprueba lo de siempre al confirmar: si una vendedora le escribió al cliente por el chat de Juan en los 30 días anteriores, la llevó ella y lo recibe como hoy en su bono. |
| Un carrito de Andrés que la vendedora **solo confirma**, sin haberle escrito por el chat de Juan en 30 días | **Sí** (caso gris) | Confirmar el pedido no basta para que sea de ella. Gerencia puede afinarlo (por ejemplo, contar también al que confirma). |
| La cotización que arma **Juan** y el cliente paga | **Sí**, mientras ninguna vendedora haya intervenido | La herramienta de cotizar de Juan marca el pedido (`dcasa_nacio_en_web`) desde su propio flujo; al confirmar se hace la misma comprobación de los 30 días. |
| Entra al chat de **Juan**, Juan lo manda a la página o al catálogo y **compra solo** | **Sí** | Nació en la página y, en los 30 días antes de confirmar, ninguna vendedora le escribió por el chat de Juan. |
| Entra al chat de **Juan** y lo **atiende una vendedora** (aunque ella le mande el enlace después) | **No** | Al confirmar el pedido se mira el chat de Juan: si una vendedora le escribió al cliente en los 30 días anteriores, la venta la llevó ella (`dcasa_llevada_por_vendedora`). |
| Lo que se arma en la tienda física, en Ventas o en el Punto de Venta (un pedido tecleado por una persona) | **No** | No nació por un flujo digital: nadie lo marca. |

Las marcas se escriben **una vez, por código del sitio**, y nadie las cambia ni las fabrica a mano: ni con `sudo()`, ni por
RPC, **ni con un `default_*` en el contexto** (que también viaja por RPC y Odoo aplica después de `create`: el `default_get`
de las marcas lo descarta), ni al importar o duplicar un pedido; tampoco el campo calculado «venta online», que se calcula
solo. Lo mismo vale para el estado de una liquidación («propuesta» siempre al crearla) y para «anulada» en una versión. **Tener `website_id` no basta**: ese campo se acepta por RPC y
cualquiera que teclee un pedido de mostrador podría ponérselo. Solo dos flujos reales marcan el origen: el carrito real
(`website._create_cart`) y la herramienta de cotizar de Juan (la API que usa el Worker, con su autenticación). Por
`_create_cart` nace todo lo que es de la página: la compra normal, la recompra, el carrito de **Andrés** (que además marca
`dcasa_via_andres`), la cotización de la página y «Pago en la tienda»; lo que se arma en Ventas o en el Punto de Venta, y
la cotización que arma una vendedora desde el panel de conversaciones, **no** pasan por ahí. Los pedidos que ya existían se marcaron una sola vez al
instalar (a los de la página ya confirmados y todavía sin pagar por completo también se les miró el chat de Juan, para que
uno atendido por una vendedora antes del despliegue no cuente como online). Si una factura junta un pedido online con otro
de la tienda, solo cuentan como online las líneas del pedido online.

**El pedido que nace por un flujo digital guarda además quién lo tocó**: si una persona del equipo (un usuario interno)
cambia su cliente o sus líneas, o alguien teclea el precio de una línea (la tienda pone los precios sola), queda anotado
(`dcasa_tocada_por_id`, que tampoco se escribe a mano). Así se ve el carrito que abre un visitante y arma después el equipo
para cobrarlo como venta del sitio: sale en *Ventas del sitio* («Abrió o cambió el carrito alguien del equipo») y en
*Pedidos de la página para revisar*. La cotización que arma Juan guarda a Juan como quien la creó (el asistente no cuenta
como del equipo).

**Cotizar en la página y pagar en la tienda SÍ cuenta** (decisión de Gerencia). Como alguien del equipo podría abrir un
carrito en la página y cobrarlo en la tienda para llevarse la comisión del sitio y no la de vendedora, cada venta guarda
**quién abrió el carrito** y si era **alguien del equipo** (un usuario interno, no un visitante): en *Ventas del sitio*
se filtra por «Carrito de alguien del equipo» y se agrupa por quién lo abrió, y los que pagaron en la tienda salen como
**Pagó en tienda**. Es vigilancia para que Gerencia lo vea, no un freno.

**Límite honesto del chat de Juan.** Un solo mensaje de una vendedora al cliente, en los 30 días anteriores a confirmar el
pedido, basta para que la venta sea de ella y no del sitio (un «hola» cuenta). Se dejó así (es lo que se decidió y lo que
atribuye el panel de Juan) y se vigila: *Pedidos de la página para revisar* arranca filtrado en los que una vendedora llevó,
para que Gerencia vea si alguien lo usa de más.

## Lo que cambió para las vendedoras (solo hacia adelante)

**Las vendedoras nunca reciben nada por una venta online.** Desde el día en que Gerencia ponga en vigencia la primera
versión de las reglas (el «Rige desde» de esa versión), una venta online:

* **no cuenta para el bono por meta** de la vendedora que la confirmó o facturó, ni su nota de crédito resta;
* **no suma al avance** que ella ve en su Inicio («Tu meta del mes» y «Vendido hoy»), y en el Inicio de Gerencia se atribuye
  a «Sin vendedora» en vez de a la vendedora del pedido;
* **no da comisión del programa de vendedores si no lleva código VEN** (queda escrita con el motivo «venta del sitio web» y
  cero puntos). **La compra por un enlace `VEN…` sigue dando al dueño del enlace lo de siempre, aunque sea online, y además
  cuenta para la comisión del sitio** (decisión del 2026-11-20: la empresa paga las dos cosas). Consecuencia: si una
  vendedora de la tienda usa su propio enlace VEN, también gana por esa venta; se podría limitar a vendedores externos más
  adelante.

**Nada es retroactivo, y el corte es uno solo.** «Rige desde» es el **inicio de ese día en Panamá**, y lo que decide a quién
le toca una venta online es **el día en que se cobró** (el día del pago, no el de hoy ni el de la factura; el Inicio de
Gerencia mira el de la factura): el día que rige y después es **del sitio y de ninguna vendedora**; el día antes y
anteriores es **de las vendedoras como siempre** (y nunca del sitio). Ejemplo, con la primera versión guardada el 4 de
marzo a las 10:00:

| Pago de una venta online con fecha… | ¿De quién es? |
|---|---|
| 3 de marzo (aunque se registre el 4) | De la vendedora, como siempre. El sitio no la cobra. |
| 4 de marzo a las 8:00, **antes** de guardar la versión | Del sitio: al guardar la versión se atribuye (la vendedora ya no la cuenta). Así no queda sin dueño. |
| 4 de marzo a las 11:00, o después | Del sitio. |

El bono por meta, el Inicio, el programa de vendedores y la comisión del sitio usan **la misma regla**, así una venta nunca
paga a las dos partes ni a ninguna. Una versión que se guarda con la fecha de hoy es válida todo el día (no importa si el
formulario estuvo abierto un rato). Lo cobrado antes de ese día cuenta como siempre, y sus devoluciones también. **El mes en
curso queda partido**: si la primera versión rige el 15, lo cobrado del 1 al 14 cuenta como antes y lo cobrado desde el 15
ya no cuenta lo online. **Sin versión de reglas, nada de esto cambia.** Lo de la tienda, y lo de Juan que atiende una
vendedora, cuenta igual que hoy.

## Las reglas (una versión por cambio)

**Nómina › Comisión del sitio web › Reglas › Nueva versión.** Cada versión dice, desde cuándo rige:

* **Porcentaje** de cada venta del sitio (fijo; **no es un bono por meta**: se paga aunque no se llegue a ninguna meta). En 0
  no hay porcentaje: las ventas se miden igual.
* **Tarifa fija** por mantener la plataforma (un monto fijo que sale siempre de la empresa) y **cada cuánto se anota**:
  cada mes (por defecto), cada quincena o cada semana. En 0 no hay tarifa. La tarifa se anota **el primer día de cada
  periodo** (el día 1; los días 1 y 16; cada lunes) con la versión que regía el día anterior. La primera tarifa de una
  versión es la del primer periodo que empieza **después** del día en que rige (si rige un 10, la del mes empieza el día 1
  del mes siguiente; si rige un lunes, la semana de ese lunes no cuenta y la primera es la del lunes siguiente; no depende
  de la hora tecleada). Si hace falta algo distinto, se anota un ajuste con motivo (queda por decidir con Gerencia: ver
  abajo).
* **Cómo se arma la base**, con cinco interruptores en palabras sencillas. Al cambiar uno, el **ejemplo con números de
  mentira** de la pantalla se mueve para que se vea qué entra y qué no:

| Interruptor | Recomendado de fábrica | La otra posición |
|---|---|---|
| ITBMS | **Sin ITBMS**: antes del impuesto | Con ITBMS: después del impuesto |
| Envío | **No cuenta el envío** | Cuenta el envío |
| Descuentos | **Después de los descuentos**: con lo que de verdad se cobró (premios y cupones ya restados) | Antes de los descuentos: con el precio de lista |
| Devoluciones | **Se resta** lo que el cliente devuelve | No se resta |
| Comisión de la pasarela | **No se resta** | Se resta (hoy ninguna pasarela guarda cuánto cobra: el interruptor ya está listo para cuando la guarde) |

* **Quiénes reciben**: se eligen entre los **empleados de Nómina** (no depende del departamento: si la persona cambia de
  departamento, esto no cambia) y a cada quien le toca un porcentaje del reparto; **tiene que sumar 100 %**. Los centavos
  que sobran van, de uno en uno y siempre en el mismo orden, a las primeras personas de la lista.

**Una versión guardada no se edita ni se borra**; un cambio es una versión nueva, y solo rige hacia adelante (no se acepta un
día que ya pasó; hoy vale, porque «Rige desde» es el inicio de ese día en Panamá). Lo ya anotado en el libro **nunca se
recalcula**. Pausar es guardar una versión con porcentaje y tarifa en 0.

**Qué versión rige cuando se guardan en desorden:** la **última que se guardó**, desde su fecha en adelante. Si se guarda A
«desde el 20» y después B «desde el 10», B manda desde el 10 y sigue mandando después del 20 (A queda tapada: se anula si se
puso mal); si dos caen el mismo día, gana la última guardada, no la de la hora más tardía.

**Si una versión se puso con la fecha equivocada** (por ejemplo, con el año errado) y todavía no rige, se **anula**: se
escribe el motivo y se toca *Anular*; queda en la lista como «Anulada», con quién y cuándo, y es como si nunca se hubiera
guardado (no frena nuevas versiones ni fija desde cuándo las vendedoras dejan de recibir lo online). Una que ya rige, o que
ya se usó para calcular una venta, no se anula: se guarda una nueva.

**Para guardar una versión tiene que haber a quién le toque aprobar**: al menos una persona de Gerencia o de Nómina que no
figure entre quienes reciben (quien cobra no aprueba lo suyo). Si no, el sistema no la guarda y dice que primero se cree
ese usuario (por ejemplo, Gerencia general).

## La base y el porcentaje, paso a paso

La base de una venta es: **lo vendido** (los muebles, sin ITBMS y con el descuento de cada línea) más o menos lo que digan
los interruptores. La **comisión** es la base × porcentaje ÷ 100, en centavos (mitad hacia arriba, como la planilla), y se
reparte entre quienes reciben. Nunca es negativa. Cada venta guarda con qué versión nació.

**«Antes de los descuentos» y las devoluciones.** Con esa posición la base es el precio de lista, así que **lo devuelto
también se resta a precio de lista**, en la misma proporción: si el cliente devuelve la mitad de lo que pagó, se resta la
mitad de la lista (no lo neto, que dejaría comisión sobre mercadería devuelta). Devolver todo deja la base en cero. El
ejemplo de la pantalla lo muestra con sus números. Con «antes de los descuentos» y «con ITBMS», el impuesto que se suma
es el del precio de lista (y el que se resta por lo devuelto, también).

**Anticipos y envío devuelto.** El anticipo que se resta en la factura final no es un descuento de precio: resta de lo
vendido con cualquier posición del interruptor (ya se contó en la factura del anticipo). Una nota de crédito que devuelve
**solo el envío** no baja la base cuando el envío no cuenta; si el envío cuenta, resta lo devuelto de envío. La línea de la
nota se reconoce por su producto (el flete): **una nota libre, sin producto, no se puede atribuir** y se resta de lo
vendido.

## Cuándo cuenta una venta y cómo se corrige

* Cuenta cuando su factura queda **pagada por completo** (o «en proceso de pago»), con la misma definición del bono por
  meta y del Inicio (hay una prueba que verifica que las dos dan el mismo día). Los abonos a medias no cuentan.
* Una **devolución** (nota de crédito, enlazada o aplicada suelta) resta en el libro **en el mes en que ocurre**; el mes de la
  venta no cambia nunca.
* Una **nota de crédito aplicada suelta** a varias facturas resta en cada una **por lo que de verdad se le aplicó**, no
  entera en cada una. En una factura que junta varias líneas, la devolución se reparte en proporción (la nota no dice de
  qué línea es).
* Un **pago revertido**, una factura **anulada**, vuelta a borrador o **borrada** **reversa** lo anotado **en el acto**
  (no espera al barrido de la noche), y **armar y aprobar una liquidación comparan antes** el libro con la verdad. Si
  vuelve a quedar pagada, se repone.
* **Armar y aprobar** una liquidación miran, en una sola consulta, si cambió la factura de alguna venta (estado, pago,
  notas, conciliaciones) y solo recomponen las que cambiaron; el barrido de cada noche las compara todas. Si otra operación
  choca con la misma venta, el sistema repite la operación con una foto nueva de la base (no sigue con datos viejos).
* El pago de una pasarela lleva la **fecha de Panamá** (no la del servidor), y un cobro cuya fecha es de **dos días o más**
  antes del día en que se anotó la venta queda señalado en *Ventas del sitio* («Cobro con fecha atrasada»): el día de
  cobro lo teclea quien registra el pago y decide de quién es la venta; lo frenan los bloqueos contables, si existen.
* Un mensaje de una vendedora que **nunca salió** (fallido, por enviar o programado) no le quita la venta al sitio.
* El **día de cobro** (el del pago, hora de Panamá) decide qué versión de las reglas le toca a la venta. Un cobro del mismo
  día en que se guarda la primera versión, aunque haya sido horas antes, se atribuye a esa versión al guardarla.
* **Un error de la comisión nunca hace fallar un cobro ni una factura**: corre dentro de un savepoint y el error queda en el
  registro. Cada noche un **barrido** anota lo que el gancho no alcanzó y **compara el libro con la verdad** de cada venta,
  asentando la diferencia como fila contraria. Va por lotes de 200 ventas y confirma cada lote, así que ni retiene candados
  de más ni se detiene por una factura rara.
* **Solo hacia adelante**: una venta cobrada antes de que rija la primera versión se mide y **nunca cobra**.

## El libro

Una fila por persona y por hecho, **en centavos enteros**. El **saldo es la suma de las filas** (no existe una columna de
saldo). Tipos: venta, devolución, reverso, tarifa fija, ajuste y liquidación. **No se edita ni se borra** (ni con `sudo()` ni
por RPC): una corrección es otra fila con la cifra contraria, su motivo y su autor. Cada fila guarda el **mes de Panamá** en
que se anotó y ese mes no se mueve: lo anotado en noviembre queda en noviembre.

El **ajuste** solo se anota a quien **figura o ha figurado** en el reparto de alguna versión (el servidor lo exige, no solo la
pantalla), y al armar una liquidación los **avisos** listan cada ajuste a mano que entra (de cuánto, por qué, quién y
cuándo) y marcan los que anotó la misma persona que cobra.

Hay **dos conceptos**, aparte en el libro y en cada liquidación: el **porcentaje de las ventas** y la **tarifa fija**.

## Liquidaciones: propuesta → aprobación → pagada

**Nómina › Comisión del sitio web › Liquidaciones › Nuevo.**

1. **Propuesta.** Se elige el periodo que se quiera (desde y hasta, **cualquiera**: semana, quincena, mes; con atajos «este
   mes», «el mes pasado», «primera quincena de este mes», «segunda quincena del mes pasado», «esta semana»…) y se toca
   **Armar**. Se junta **todo lo que se debe hasta esa fecha y todavía no se había liquidado**, por persona y concepto.
   Se puede armar de nuevo las veces que haga falta.
2. **Aprobada.** La aprueba una persona de Gerencia o de Nómina **que no figure entre quienes cobran en esa
   liquidación**: es la **única protección** y es automática (la pantalla lo explica con una frase amable). Queda quién y
   cuándo. «Figurar» se mira por el usuario y el contacto de trabajo que la ficha de cada persona nombra hoy **y por los
   usuarios que tenía ligados el día en que se guardó la versión del reparto**: cambiar la ficha después (soltar el usuario,
   cambiar el contacto) no deja a quien cobra aprobar lo suyo, y cualquier cambio en la ficha queda en su chatter. Al aprobar se anota en el libro una fila negativa de liquidación por persona y concepto: la plata sale del
   saldo, así que **nunca se paga dos veces lo mismo**, aunque los periodos se solapen o haya dos propuestas a la vez
   (la segunda en aprobarse pide armarse otra vez; el sistema la repite solo con una foto nueva de la base). Una aprobada **no
   se edita**.
3. **Pagada.** Se escribe la fecha y la referencia del pago (transferencia, cheque, recibo) y se marca como pagada. El
   sistema **no mueve dinero**: lo anota.
4. **Cancelada.** Una aprobada que todavía no se pagó se cancela: se escribe el **motivo** en el mismo formulario y se toca
   *Cancelar*; se anula con filas contrarias y lo que se debe vuelve al saldo. Una propuesta se cancela o se borra sin tocar
   el libro. Una ya pagada no se cancela: se corrige con un **ajuste**.

Si el saldo de alguien es negativo (devoluciones que superaron lo ganado), hoy se le paga cero, se avisa y el saldo sigue
para la próxima liquidación: **nunca se le descuenta a nadie por la planilla sin que Gerencia lo decida**.
**Nada se paga solo**: ningún proceso automático aprueba ni paga.

**El límite honesto de «quien cobra no aprueba».** Lo que el sistema ve es el usuario y el contacto ligados a la ficha. Si
una persona que cobra se hace con **otro usuario** de Gerencia o de Nómina que **no está ligado a su ficha** (ni lo estuvo
al guardar la versión) y lo maneja ella misma, ese usuario puede aprobar. No hay manera de saberlo con código: la cubren
tres cosas: (1) cada cambio de usuario o contacto en la ficha queda **en el chatter**, (2) los usuarios ligados quedan
**fijos en cada versión del reparto**, y (3) hay que tener a alguien más (Gerencia general) con quien confirmar, que es
justo lo que la protección pide. El administrador técnico, que puede darse cualquier rol, queda fuera de la comisión
(como en el resto del sistema).

## Cómo se paga (y lo que NO es)

Decisión de Gerencia: **la comisión no cuenta como salario**. Se paga **sin descuentos de planilla** (como los reembolsos).
**Conviene que la contadora deje por escrito el tratamiento** (anótese; no bloquea nada). Enviar una liquidación aprobada a la
planilla como línea sin descuentos queda como siguiente paso (ver abajo); mientras tanto basta marcarla como pagada con su
referencia.

## Quién puede qué

| Quién | Qué ve y hace |
|---|---|
| Gerencia y quien administra la nómina | Todo: ven las cinco pantallas, guardan y anulan versiones de las reglas, arman, aprueban (menos donde cobran), pagan y cancelan liquidaciones y anotan ajustes. |
| Solo Gerencia | *Pedidos de la página para revisar* (la vigilancia). |
| El administrador técnico (solo) | **Nada** de la comisión (como siempre, puede darse roles: es el límite honesto de cualquier sistema). |
| Vendedora, Caja, Marketing, el público | Nada: ni el menú ni por enlace. |

## Pendiente a propósito (anotado como futuro)

* **Sello mensual por correo y huella encadenada** del diseño original: Gerencia pidió una sola protección, así que no están.
* Enviar una liquidación aprobada a la **planilla** como línea sin descuentos.
* Un resumen de la comisión en el **Inicio** y una herramienta de **Brian** de solo lectura.
* Escalones, metas, topes y porcentajes por producto o canal; restar la comisión de la pasarela automáticamente (el
  interruptor ya existe: falta que cada pasarela guarde su cobro en `payment.transaction.dcasa_comision_pasarela`).
* Informes de «Pendientes de cobro» y «Pagos del sitio sin factura todavía».

## Por decidir o verificar con Gerencia y la contadora

1. **Cuántos días hacia atrás se mira el chat de Juan** para saber si una vendedora llevó la venta: 30, los mismos con que
   el panel de Juan atribuye ventas (Gerencia, 2026-11-20: se queda).
2. **El caso gris:** un carrito de Andrés, una cotización de la página llevada a la tienda o una cotización de Juan que la
   vendedora **solo confirma**, sin haberle escrito por el chat de Juan, cuenta como online. Gerencia no quiere
   trazabilidad extra, pero lo puede afinar. Andrés, por sí solo, no deja un registro de que pasó al cliente a una persona:
   lo único fiable es el mensaje de la vendedora en el chat de Juan.
3. **Códigos VEN y vendedoras de la tienda:** hoy una vendedora que usa su propio enlace también gana por esa venta
   online; se podría limitar a vendedores externos.
4. **La contadora**: tratamiento por escrito de la comisión y de la tarifa fija (no son salario) y de las devoluciones
   posteriores a un pago.
5. **Compras de quienes reciben:** el diseño las excluía; con «una sola protección» hoy no se excluyen.
6. **Un «hola» de una vendedora** basta para que la venta sea de ella y no del sitio (30 días, un solo mensaje). ¿Se deja así o
   se pide más (varios mensajes, o que ella haya cotizado)? Hoy se vigila en *Pedidos de la página para revisar*.
7. **Primera tarifa:** se anota el primer día del periodo que empieza después del día en que rige la versión (no el mismo
   día, aunque la versión rija desde las 00:00); si hace falta una parcial, es un ajuste. El segundo revisor opinó lo
   contrario para el mismo caso (que el lunes en que rige ya cuente); no se cambió porque lo escrito pide «el periodo
   siguiente» y la primera revisión lo da por bueno: queda para Gerencia.
