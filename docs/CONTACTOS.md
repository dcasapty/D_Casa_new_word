# Una persona, una ficha (`dcasa_contactos`)

Pedido de la dueña (2026-10-10): que un cliente que escribe por WhatsApp sea reconocido por su número (con o sin el
+507), que no se creen dos fichas con el mismo celular, correo o RUC/cédula, y que dos personas **sí** puedan llamarse
igual.

## Qué hace

* **El candado.** No se guarda una ficha con el mismo **celular o teléfono**, el mismo **correo** ni el mismo **RUC o
  cédula** que otra. El nombre puede repetirse. Se compara sin importar mayúsculas, espacios, guiones, puntos ni el
  +507: `6026-1919`, `60261919`, `+507 6026-1919`, `507 6026 1919` y `00507-6026-1919` son el mismo celular;
  `Ana@x.com` y `ana@x.com` son el mismo correo; `8-123-456` y `8 123 456` son la misma cédula.
* **Panamá y el resto del mundo no se confunden.** Un número de otro país se guarda **completo**, con su código de
  país: `+1 305 555 1234` nunca se parece a `5555-1234`.
* **El aviso.** Al personal le dice de quién es el dato («El correo ana@x.com ya es de «Ana Gómez». Usa esa ficha en
  vez de crear otra»). Quien viene de la tienda o del chat **no ve el nombre de nadie** («Ese correo ya está
  registrado… escríbenos por WhatsApp»). Mientras se escribe en el formulario, un aviso amarillo se adelanta.
* **Lo que no cuenta:** las direcciones de entrega o de facturación de una misma persona (comparten sus datos), los
  usuarios del sistema, los empleados y las empresas propias del grupo.
* **Lo viejo no se toca.** Solo se revisan las fichas nuevas y los datos que se **cambian**. Una ficha que ya estaba
  repetida se puede seguir editando (su nombre, su dirección); lo que no puede es repetir un dato **nuevo**.
* **El chat.** Cuando alguien escribe por WhatsApp, Juan busca su ficha por la llave del teléfono (el celular de
  Socios, el teléfono de la ficha o el del contacto de trabajo del equipo); si existe, la usa; si no, la crea. Dos
  mensajes a la vez de un número nuevo no crean dos fichas (la conversación de cada número es única en la base).
* **La tienda.** Quien compra **sin cuenta** con un celular, correo o RUC que ya son de una ficha **no** entra en esa
  ficha: un dato escrito en la tienda no prueba quién es la persona. Antes (hasta el 2026-10-17) su dirección se colgaba
  de esa ficha por la ruta del pago exprés, y Odoo le enseñaba en el checkout las direcciones, teléfonos y correos de
  esa persona, le dejaba editarlas y le ponía la compra en su «Mi cuenta» (revisión independiente; pruebas en
  `website_dcasa/tests/test_privacidad_checkout.py`). El formulario normal de Odoo 19 nunca pasó por ese atajo: le
  responde «Ese celular ya está registrado… escríbenos por WhatsApp» (sin decir de quién) y la compra no sigue.
  **Pendiente de la dueña:** cómo compra en la web quien ya es cliente de la tienda (entrar con su cuenta, o una ficha
  aparte que el equipo une después).

## Al cotizar (etapa 3, 2026-10-16)

Una misma persona salía hasta cinco veces al elegir el cliente de una cotización: su ficha, su usuario del sistema, su
contacto de empleado y sus direcciones de entrega o de factura, todos con el mismo nombre.

* **El selector de «Cliente» muestra solo fichas de clientes:** contactos principales que no son del equipo (usuario
  interno o empleado) ni una empresa propia. Las direcciones se eligen donde siempre, en «Dirección de factura» y
  «Dirección de entrega». Quien se registró en la tienda (usuario del portal) sí sale: es cliente.
* **Los usuarios y empleados no se tocan:** solo dejan de ofrecerse como cliente. Si alguien del equipo compra, se
  cotiza en su ficha de cliente.
* **Aviso de posible repetido:** si la ficha elegida comparte celular, correo o RUC/cédula con otra ficha (lo viejo, de
  antes del candado), sale un aviso con el nombre de la otra para cotizar en la correcta y fusionarlas después.
* Lo ya guardado no cambia: una cotización vieja con una dirección como cliente se sigue abriendo igual.

## Buscar antes de crear (etapa 3, 2026-10-22)

* **Al crear una ficha** (Contactos › Nuevo, «Crear y editar» desde la cotización, «Nuevo cliente» del Inicio):
  mientras se escribe el nombre, un aviso amarillo muestra las fichas con un **nombre parecido** («Ojo: ya hay fichas
  con un nombre parecido: «Ana Gómez» (6123-4567)… Si es la misma persona, usa esa ficha»). **No bloquea**: dos
  personas pueden llamarse igual. «Parecido» = las mismas palabras sin mayúsculas, tildes ni signos, en cualquier orden,
  o un nombre que contiene al otro (con al menos dos palabras). Solo fichas de clientes y proveedores: los usuarios y
  empleados del sistema no cuentan. Código: `models/parecidas.py`; pruebas: `test_parecidas.py`.
* **Brian** (`crear_cliente`, por el chat o por Telegram) busca antes por celular, correo, RUC y nombre parecido. Un
  dato repetido no crea nada y dice de quién es; un nombre parecido no crea nada y pregunta. Si la persona confirma que
  es otra, Brian usa `crear_cliente_distinto` (el celular, el correo y el RUC siguen sin poder repetirse).
* **Conversaciones:** quien escribe por Telegram, Messenger o Instagram sin celular recibe una ficha provisional
  («Telegram 123…» o su nombre del canal). Cuando da su celular y ese celular ya es de una ficha, la conversación pasa a
  esa ficha (como antes) y ahora, además, la provisional le pasa su oportunidad de esa conversación y, si quedó **vacía**
  (sin celular, correo, RUC, ventas, facturas, oportunidades, otras conversaciones ni usuario), **se archiva** con una
  nota (no se borra nada). Lo mismo si una persona cambia a mano el cliente de la conversación. Si la provisional tiene
  algo propio, se queda como está.
* **La fusión** sigue como en la etapa 3 del 16 de octubre (abajo): la usa Gerencia, copia los datos de Socios, y por
  defecto queda la ficha que ya está en un programa (socio o vendedor) y, si ninguna lo está, la **más vieja** (como
  pide la etapa 3); el destino se cambia en el asistente.

## Celular y correo bien escritos y obligatorios (2026-10-16 y 2026-10-17)

Pedido de la dueña: «el vendedor siempre, obligatoriamente, debe capturar el número de teléfono y correo electrónico,
pero bien escrito». Ahí le llegan al cliente su factura y cómo ver sus puntos.

* **Qué es «bien escrito»** (`dcasa_socios/models/bien_escrito.py`, funciones puras):
  * Correo con una sola `@`, sin espacios ni comas y con un dominio completo. Los errores de dedo de los correos más
    usados traen sugerencia: `ana@gmial.com` → «¿Quisiste decir ana@gmail.com?»; también `hotmail.con`, `gmail.co`,
    `yahoo.cmo`… (`hotmail.es` y `yahoo.es` sí valen; `algo.co` también). Lo de relleno (`no@no.com`,
    `sincorreo@gmail.com`) no es un correo. Se guarda limpio y en minúsculas.
  * Celular de Panamá de 8 números (`6026-1919`, con o sin +507) o de otro país **con +** y su código
    (`+1 305 555 1234`). Se guarda como `+507 6026-1919` o `+13055551234`; la llave de contactos no cambia. Un fijo de
    7 números escrito en «Celular» no se guarda: el mensaje dice que va en «Teléfono fijo».
  * **Teléfono fijo** (2026-10-22, abajo): en Panamá 7 números que no empiezan por 0, 1 ni 6 (`234-5678`, con o sin
    +507), o de otro país con +. Se guarda como `+507 234-5678`; si se escribe un celular ahí, dice que va en
    «Celular».
  * El correo de alguien del equipo o de la empresa no sirve como correo del cliente.
* **Cuándo se exige** (solo a quien trabaja en Odoo y sin `sudo`; Juan, la tienda, Socios, el importador, la fusión
  y los crons no pasan por aquí; Brian sí, porque corre como la vendedora):
  * **Al escribir** un correo o un celular en la ficha de un cliente: si está mal escrito no se guarda (al salir del
    campo ya sale el «¿Quisiste decir…?»). Lo viejo no se toca: solo se revisa lo que cambia.
  * **Al crear una persona como cliente** (Ventas › Clientes, «Crear y editar» en la cotización, «Nuevo cliente» del
    Inicio): celular y correo obligatorios. La creación rápida (escribir el nombre y Enter) y las empresas no se frenan
    al crear: los pide la venta.
  * **Al confirmar la venta** (puerta A) y **al publicar la factura** (puerta B), con un mensaje que dice qué falta y
    dónde se escribe. Mientras se cotiza, un aviso amarillo lo adelanta. **«Pagar» nunca se bloquea.**
  * Nada de esto frena el guardado automático (la nube): una cotización o una ficha vieja a medias se guarda igual.
* **«Cliente no tiene correo electrónico»** (decisión de la dueña, 2026-10-17): es la única excepción y **solo exime
  del correo** (el celular sigue obligatorio). La marca la vendedora junto al cliente en la cotización (se guarda en la
  ficha al guardar la cotización) o en la ficha, debajo del correo. Solo se ve mientras el correo está vacío; si
  después se le escribe un correo, **se desmarca sola**. Queda en el historial de la ficha quién la marcó. Por Brian:
  `crear_cliente` o `actualizar_cliente` con el correo «no tiene».
* **Teléfono fijo** (pedido de la dueña, 2026-10-22: «hubo un cliente que no tenía WhatsApp sino teléfono fijo de 7
  números»): campo propio, «Teléfono fijo», debajo del celular en la ficha y en «Crear y editar» de la cotización o la
  factura. **Sirve en lugar del celular** para crear al cliente, confirmar su venta y publicar su factura (el correo
  sigue igual). **No es una llave**: no se compara con otras fichas (una casa o una empresa con varios contactos
  comparten el fijo), no entra en «Posibles duplicados» y no sirve para Socios ni para WhatsApp, cuya llave sigue
  siendo el celular (regla 5). Se encuentra al cliente escribiendo su fijo en el buscador o en el selector de cliente;
  la fusión lo conserva como cualquier dato; sale en la factura junto al celular. Por Brian: el fijo en «celular» de
  `crear_cliente` y `telefono_fijo` en `actualizar_cliente`. La carga del sistema anterior pone el primer fijo de Panamá en su campo.
* **Clientes viejos:** **Socios › Configuración › Clientes sin correo o sin celular** (Gerencia) los lista para
  completarlos antes de su próxima venta (no salen los que tienen un teléfono fijo en lugar del celular).
* **Los fijos viejos guardados en «Celular»** (la dueña, 2026-10-22: «Sí, hazlo si puedes»): al actualizar
  `dcasa_contactos` a 19.0.1.1.0 pasan **una sola vez** a «Teléfono fijo» (`models/mover_fijos.py`). Solo fichas de
  clientes y proveedores (no usuarios, empleados ni empresas propias), solo si el celular es un fijo de Panamá bien
  escrito y el fijo está vacío; el celular queda vacío y la ficha lleva la nota «Se pasó el número X de Celular a
  Teléfono fijo». Si el fijo ya tenía otro número, no se toca. **Socios y vendedores del programa no se tocan** (su
  llave es el celular): el registro del servidor dice cuántos quedaron así, sin nombres, para que la dueña decida.
* No aplica a fichas solo de proveedor, ni a las de usuarios, empleados o empresas propias.
* Código: `dcasa_contactos/models/contacto.py` (ficha y mensajes), `sale_order.py` (puerta A y la casilla de la
  cotización), `account_move.py` (puerta B). Pruebas: `test_bien_escrito.py`, `test_exigir_contacto.py` y
  `test_sin_correo_navegador.py` (la casilla en el navegador, guardando con la nube).

## Puntos por WhatsApp

Juan responde el saldo de puntos del **número de esa conversación** (nadie puede pedir el de otro número) y **pide el
PIN de Socios**: el número prueba que es *ese teléfono*, no que quien lo tiene en la mano es el dueño (un teléfono
prestado o perdido). WhatsApp a veces esconde el número y manda un identificador en su lugar: en ese caso no se puede
saber de quién es hasta que el cliente dé su número y lo confirme con su PIN. Decisión de la dueña si algún día se
quiere que baste el número: una línea en `saldo_puntos` de Juan.

## Limpiar lo que ya estaba repetido

**Socios › Configuración › Posibles duplicados** (Gerencia) lista cada celular, correo o RUC/cédula que comparten dos o
más fichas, con sus nombres. Por fila:

* **Ver las fichas:** abre las fichas repetidas (incluidas las archivadas).
* **Fusionar:** abre el asistente de fusión de Odoo con esas fichas (hasta 3 a la vez). Por defecto queda la ficha
  **activa más vieja** (no la de más movimiento; se puede cambiar el destino en el asistente) y se lleva facturas,
  puntos, conversaciones y notas de las otras. Con más de 3, se repite.
* **Qué se cuida al fusionar (arreglado el 2026-10-16):**
  * Gerencia puede usar el asistente (antes solo lo abría el administrador del sistema).
  * Por defecto queda la ficha que **ya está en un programa** (socio o vendedor) y, entre esas, la de más puntos
    movidos; si ninguna lo está, la activa más vieja. El destino se puede cambiar en el asistente.
  * Lo de Socios y de vendedores que Odoo no copia solo (código, celular del programa, PIN, quién la invitó y si ya
    se pagó el referido, patrocinador…) **pasa a la ficha que queda** si esa no lo tenía. Lo que ya tiene manda.
  * **Dos fichas con código de socio (o de vendedor) no se fusionan:** se perdería uno de los dos códigos. El
    asistente avisa y no borra nada; se revisa con la dueña.
  * Si los correos son distintos, solo el administrador del sistema puede fusionar (regla de Odoo, se mantiene).

Si el contador de duplicados no baja a cero, se limpia por tandas; el candado ya impide que vuelvan a crecer.

## Detalles técnicos

* Campos nuevos en `res.partner`: `dcasa_telefono_llave` (`pa:60261919` o `intl:13055551234`) y `dcasa_vat_llave`
  (guardados e indexados). El correo usa `email_normalized` de Odoo.
* Se revisa en `create` y `write` (no con un índice único de base de datos, que impediría instalar si hay repetidos
  viejos). `with_context(dcasa_sin_duplicados=True)` salta la revisión: la usan la fusión de contactos y la creación de
  usuarios, empleados y empresas.
* Al cotizar: `models/sale_order.py` (dominio de `sale.order.partner_id` armado con `sudo` como lista de ids, así la
  Vendedora, que no ve empleados, busca sin error; aviso en el `onchange` del cliente).
* Pruebas: `scripts/test.sh dcasa_contactos` (llaves, candado, excepciones, lista de duplicados, fusión, al cotizar), más
  `TestFichasUnicasEnElChat` (conversaciones), `TestDireccionDelVisitante` y `TestCheckoutSinDatosAjenos` (tienda).
