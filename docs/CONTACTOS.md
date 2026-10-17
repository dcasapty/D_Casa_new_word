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
