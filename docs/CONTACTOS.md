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
* **La tienda.** Quien compra **sin cuenta** con un celular, correo o RUC que ya son de una ficha cae en **esa** ficha:
  su dirección queda como dirección de esa persona, así que suma sus puntos en la misma ficha y la compra no falla. Sus
  datos no se modifican.

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
* **Dos cuidados (revisados el 2026-10-16, pendientes de arreglo):** (1) el asistente exige el grupo «Creación» de
  Contactos, que hoy solo tiene el administrador del sistema, así que Gerencia recibe un error de permiso; (2) los
  datos de Socios de la ficha que se borra (código, celular de socio, PIN y quién la invitó) **no se copian** a la que
  queda. Los puntos y los asientos sí se mueven, pero si la ficha que se borra era la socia, se pierde su código.
  **No fusionar fichas de socios con este asistente** hasta que se corrija (ver `docs/PRIORIDADES.md`, etapa 3).

Si el contador de duplicados no baja a cero, se limpia por tandas; el candado ya impide que vuelvan a crecer.

## Detalles técnicos

* Campos nuevos en `res.partner`: `dcasa_telefono_llave` (`pa:60261919` o `intl:13055551234`) y `dcasa_vat_llave`
  (guardados e indexados). El correo usa `email_normalized` de Odoo.
* Se revisa en `create` y `write` (no con un índice único de base de datos, que impediría instalar si hay repetidos
  viejos). `with_context(dcasa_sin_duplicados=True)` salta la revisión: la usan la fusión de contactos y la creación de
  usuarios, empleados y empresas.
* Pruebas: `scripts/test.sh dcasa_contactos` (llaves, candado, excepciones, lista de duplicados, fusión), más
  `TestFichasUnicasEnElChat` (conversaciones) y `TestDireccionDelVisitante` (tienda).
