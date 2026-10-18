# Socios D'CASA — puntos y referidos (`dcasa_socios`)

El programa que diseñó Abrinay en
[`abrinay1997-stack/DCasa-Referidos`](https://github.com/abrinay1997-stack/DCasa-Referidos),
llevado **dentro de Odoo** para que haya un solo sistema. Se conservaron sus reglas
de negocio y sus defensas antifraude. Lo que aporta Odoo es que las ventas ya no
se teclean dos veces.

> **Vendedores.** Quien vende por su cuenta (empleado o de afuera) tiene un programa aparte, con código
> `VEN…`, puntos propios y una colmena de un solo nivel; ver [VENDEDORES.md](VENDEDORES.md). Convive con
> este: el cliente sigue ganando sus puntos de Socios y el vendedor es la misma ficha.

## Qué se tomó de cada lado

| De DCasa-Referidos (Abrinay) | De la integración con Odoo |
|---|---|
| Economía en [`data/puntos.json`](../addons/dcasa_socios/data/puntos.json), versionada en git (copia literal, versión 2 aprobada el 2026-09-22) | La **factura pagada suma puntos sola** (`_invoice_paid_hook`): no hay "cargar compra" a mano |
| Libro mayor inmutable: el saldo es la suma de asientos, las correcciones son asientos contrarios con motivo | Nota de crédito total / cancelación / factura a borrador → **anula la compra** y deshace el referido; nota parcial → descuenta la parte proporcional |
| Un cliente y un socio son **la misma ficha** (aquí: el contacto de Odoo), con el celular como llave única | El código y los puntos **impresos en la factura** |
| Referido pagado con la **primera compra que da puntos**, nunca al registrarse; padrino escrito una sola vez; topes de 50 invitados y 5.000 puntos al mes; un tope nunca hace fallar la venta | Link `/r/CÓDIGO` y `?ref=CÓDIGO` en cualquier página; el carrito web y la cotización proponen el padrino (buscable por código) |
| Canjes con código de 72 h; puntos reservados al pedir; un pendiente por premio; stock; se devuelven al vencer o cancelar | Los premios de descuento se **cobran dentro de la venta** («Cobrar premio»): el importe lo pone el premio y el código se sella al confirmar. En la tienda web, el socio los aplica él mismo en el carrito («Usar mis puntos») y el pedido cancelado los devuelve solo |
| Cumpleaños automático (hora de Panamá, una vez al año, con compra previa) | Reportes con pivotes y gráficos de Odoo: puntos por vendedora, pasivo del programa, canjes por premio |
| App del socio con **celular + PIN** (sin correo), candado 5 fallos → 15 min, 10 → 24 h, PIN con pimienta fuera de la base, mensajes que no revelan quién es cliente | Menú **Socios** propio para las vendedoras; ficha del socio como pestaña del contacto |
| Reclamar una ficha con puntos exige el código de la factura (desde el 2026-10-16, también una ficha con compras aunque tenga 0 puntos: ver [Mi cuenta](#mi-cuenta)) | Compra manual solo para facturas del sistema anterior (transición) |
| Términos generados desde las reglas reales (Ley 81 de 2019) | |

## Cómo se usa

**En la tienda:** la vendedora factura como siempre. Cuando la factura queda pagada:
- el cliente suma puntos;
- si es su primera compra y alguien lo invitó, el padrino gana 500 y el cliente 250.

Si el cliente llegó invitado, en la cotización se llena **Invitado por** con el
código `DCA…` o el nombre del padrino.

**El cliente:**
1. Entra a `dcasapty.com/socios` y se registra con su celular y un PIN.
2. Si ya compró, escribe el código de socio impreso en su factura para reclamar sus puntos.
3. Ve su saldo, invita por WhatsApp o con su QR, pide premios y ve su actividad en **Mi cuenta**
   (`/mi-cuenta/puntos`), junto con sus compras y lo que le falta pagar (ver [Mi cuenta](#mi-cuenta)).

**Premios:**
- **De descuento:** en la cotización se pulsa **Cobrar premio** y se escribe el código que enseña el cliente.
- **De producto:** se entregan desde *Socios → Canjes*.
- **Catálogo público** en `dcasapty.com/socios/premios`: foto, nombre y puntos de cada premio
  (lo que Gerencia edita en *Socios → Configuración → Premios*). «Pedir» crea el canje de siempre
  (código de 72 h, puntos reservados); la página enseña el estado y si se recoge o se enseña al pagar.
- **Premio de ejemplo** (decisión de la dueña, 03/10/2026): «Dos almohadas» por 400 puntos, de
  producto, ligado a `ALMOHADA001` × 2 si ese producto ya está en la base (si no, sin producto). Se crea
  una sola vez desde `data/premios_data.xml`; Gerencia lo edita o lo archiva y no vuelve a aparecer.
  **Ojo:** `saldoMinimoParaCanjear` (500) se compara hoy contra los puntos **del premio**, así que un
  premio de 400 no se puede pedir hasta que la dueña decida (ver `docs/auditoria/ronda7/socios-web.md`).

**En la tienda web (puntos en el carrito):**
- Un socio **con cuenta de la tienda** (usuario del portal; la misma ficha `res.partner`, llave =
  celular) ve en el carrito el paso **Usar mis puntos**. Elegir un premio de descuento del catálogo
  pide el canje (reserva los puntos) y lo aplica a la orden como una línea negativa; si lo quita, o si
  el carrito baja del valor del premio, o si el código vence, los puntos vuelven con un asiento contrario.
- Si el pedido se cancela (aun confirmado), el canje se cierra y los puntos vuelven con el motivo
  «Se canceló el pedido …». La línea del premio no admite cantidad: se usa una vez o se quita.
- Parámetro `dcasa_socios.puntos_en_carrito` (Ajustes → Ventas → *Socios: puntos en el carrito web*):
  `premios` (por defecto: solo los premios del catálogo) o `todo` (además, el socio elige cuántos puntos
  usar contra cualquier producto; el descuento sale de `canje.puntosPorDolar` en `puntos.json`,
  redondeado hacia abajo al centavo, respetando `saldoMinimoParaCanjear`). Los dos modos están probados.
  **Decisión de la dueña (03/10/2026): el canje es SOLO por premios que define el administrador**, así
  que se queda en `premios`; `todo` existe y está probado, pero no está activo.
- La compra web suma puntos **solo cuando su factura queda pagada**, como cualquier otra, y sobre lo
  que de verdad pagó (ya con el premio descontado).

**Cuenta unificada:**
- El usuario de la tienda entra a **Mi cuenta** (`/mi-cuenta`; su `/my` lleva ahí) y ve su saldo, premios por
  recoger e invitados junto con sus compras. `/socios` reconoce su sesión sin pedir PIN si su ficha ya es socio.
- Si tiene celular de Panamá pero todavía no entró al programa, `/socios` le invita a **activar sus
  puntos** eligiendo un PIN (misma ficha; no se le pide el código de la factura porque la sesión de la
  tienda ya prueba quién es). Si su celular ya es la llave de otra ficha, se le manda a entrar con PIN.
- Quien solo tiene sesión por PIN (sin cuenta de la tienda) ve en el carrito su saldo y cómo usarlo:
  entrar con su cuenta de la tienda o pedir un premio y dictar el código al coordinar el pedido.

## Mi cuenta

El panel del cliente, en **`/mi-cuenta`** (módulo `dcasa_mi_cuenta`, desde el 2026-10-16). Lo pidió la dueña: «que el
cliente pueda ver cuánto le falta» de sus abonos y un panel «sencillo, muy bien organizado, amigable». Móvil primero
(se usa de pie en el mostrador): letra de 17 px, botones de 48 px, barra fija abajo en el celular
(Inicio · Compras · Puntos · Mis datos) y columna a la izquierda en la computadora.

**Quién entra.**
- Con **celular + PIN** (la sesión de Socios; si el PIN es temporal, primero se cambia en `/socios/pin`).
- Con la **cuenta de la tienda** (correo y contraseña; usuario portal): su ficha es la del usuario (la comercial).
- Sin sesión, `/mi-cuenta` es «Entra a tu cuenta»: el mismo formulario de `/socios` (con Turnstile), «Entra con tu
  correo», «Hazte socio» y «¿Olvidaste tu PIN? Escríbenos por WhatsApp». Un PIN equivocado se avisa ahí mismo.

**Qué ve.**
- **Inicio:** lo pendiente primero (la compra con saldo: «Te falta $X», «Pagaste $A de $T» con su barra y hasta
  cuándo tiene; o un apartado; o una entrega lista; o los premios por recoger con su código), su última compra con
  la línea de tiempo (Compra hecha · Pagada o «Pagando: te falta $X» · Lista · Entregada), sus puntos en la placa
  azul (saldo, código, cuánto le falta para el premio más barato que aún no alcanza) y WhatsApp.
- **Compras:** pedidos (cotización enviada, confirmados y cancelados; **nunca borradores**: los carritos de la web
  son borradores) y facturas que no vienen de ningún pedido, en grupos: «Por pagar», «Por entregar o retirar»,
  «Ya las tienes» y «Canceladas» (las últimas 5). Cada compra lleva foto del mueble principal (si está publicado en
  la tienda) y «y N cosas más».
- **Detalle de una compra:** cada abono con su fecha, su medio y su monto; total de la factura, pagado y saldo;
  hasta cuándo tiene para terminar de pagar (`dcasa_invoice.abono_dias`, 30 días continuos desde el primer abono); la entrega
  (solo lo que ya pasó: «Entregado el …», «Listo: te escribimos para coordinar…», «Lo estamos preparando»; la fecha
  prevista de Odoo **nunca** se enseña como promesa); lo que compró con su ITBMS; los puntos que le sumó.
  - Un pedido confirmado sin factura publicada dice «Tu factura y tus pagos aparecen aquí cuando se emita»: no se
    inventa un saldo.
  - Apartado: «Apartado hasta el 23 oct: pasa a pagarlo antes de esa fecha». Anulado por el cron: «Se anuló porque
    venció el apartado el 14 oct».
- **Puntos:** lo que antes estaba en `/socios/cuenta`, ordenado para el mostrador: los premios por recoger con su
  código **arriba**, el saldo («equivalen a $X» sale de `canje.puntosPorDolar` de `puntos.json`), la meta, invitar
  (WhatsApp, copiar el enlace, el QR plegado), invitados, premios anteriores y actividad. Si es vendedor, el acceso
  a su panel.
- **Mis datos:** nombre, celular, correo, código de socio y cumpleaños, solo lectura («Para cambiar tus datos
  escríbenos por WhatsApp»); cambiar el PIN; con la cuenta de la tienda, cambiar la contraseña y sus direcciones;
  reglas, privacidad y «Salir».

**De dónde salen las cifras.** Solo de `account.move._dcasa_estado_abono()` (`dcasa_invoice`), la misma función que
imprime el papel. Mi cuenta **solo lee**: no toca asientos, impuestos, cuentas ni pagos. Los abonos se siguen
registrando como siempre: la factura completa (con ITBMS) se publica en el primer abono y cada abono es un pago
parcial con «Pagar».

**Privacidad.**
- Todo se lee con permisos de sistema pero **siempre filtrado por la ficha comercial del cliente**. Un pedido o una
  factura de otra persona responde 404, igual que uno que no existe.
- A quien entra con **PIN** no se le enseñan cédula, dirección, teléfonos (solo el celular con que entra), el correo
  entero ni PDF (los PDF traen datos personales): «¿Necesitas tu factura? Escríbenos por WhatsApp» con el número de
  la compra ya escrito.
- Al usuario de la **tienda** sí se le dan los PDF del portal de Odoo (`/my/orders/…`, `/my/invoices/…`), que ya le
  permiten las reglas del portal. Nunca se crean enlaces con `access_token`.
- **Hueco cerrado (2026-10-16):** antes una ficha con 0 puntos se reclamaba en `/socios/registro` sin el código de
  la factura. Con las compras a la vista eso dejaba ver compras ajenas sabiendo un celular. Ahora también se exige el
  código si la ficha tiene una factura de cliente publicada o un pedido que no es borrador
  (`res.partner._dcasa_tiene_compras`); el mensaje pide el código de la factura o escribir por WhatsApp.

**Los caminos viejos llevan aquí.**
- `/socios/cuenta` → `/mi-cuenta/puntos`; `/socios` con sesión → `/mi-cuenta/puntos`.
- Entrar o registrarse en `/socios` → `/mi-cuenta`; guardar el PIN → `/mi-cuenta/datos`; «Salir» → `/mi-cuenta`.
- `/my` y `/my/home` del cliente de la tienda → `/mi-cuenta` (el equipo sigue yendo a su `/my`).
- La cabecera del sitio dice «Mi cuenta» (antes «Inicia sesión») y lleva a `/mi-cuenta` para todos: el borde guarda
  las páginas anónimas, así que el enlace no depende de la sesión. El pie también.
- Las páginas de Odoo que siguen en `/my` (detalle del pedido y de la factura) ya no dicen «Con la tecnología de
  Odoo» y sus botones «secundarios» (que el tema pinta amarillos sobre blanco) son azules.

**Gerencia:**
- Hace ajustes con motivo.
- Anula compras.
- Suspende y reactiva socios.
- Reinicia el PIN (le dicta al socio uno temporal) y desbloquea cuentas tras
  muchos intentos fallidos; queda una nota en el chatter con quién lo hizo.
  Estos botones exigen el grupo de gerente de ventas en el servidor, no solo en la vista.
- Edita premios (*Socios → Configuración → Premios*).
- Registra a mano facturas del sistema anterior.

## Qué pasa con los puntos si se borra un borrador de factura

Una factura que ya dio puntos se puede borrar, sin archivarla y sin que el borrador quede trabado
(antes salía «Error de validación: otro modelo usa el registro… Compra con puntos»). El camino:

1. En la factura pagada, **Restablecer a borrador**. Ahí mismo los puntos de esa venta se devuelven con un
   asiento contrario («La factura … volvió a borrador») y, si esa compra había pagado un referido, también
   se deshace el bono del padrino y el del invitado.
2. **Eliminar**. La factura desaparece. La compra anulada se queda en *Socios → Compras* (estado Anulada, con
   su número y su motivo, sin factura enlazada): es la historia del programa y no se borra.

Qué queda después:

- **El libro no pierde ni una fila.** El saldo sigue siendo la suma del libro: la compra y su reverso se
  anulan entre sí.
- **El cliente sigue siendo socio** (su ficha y su código se quedan), con los puntos que ya tenía antes.
  Si era un cliente nuevo de prueba, queda en 0 puntos netos; si no lo quieres, archiva el contacto
  (no se borra: su historia está en el libro).
- **El referido puede volver a pagarse.** Al deshacer el bono se suelta el sello del invitado: su siguiente
  compra real que dé puntos vuelve a pagar a su padrino (el padrino sigue siendo el mismo, se escribe una
  sola vez). Un bono deshecho **no gasta** el tope de invitados ni el tope de puntos del mes del padrino.
- **Una devolución parcial también se deshace.** Si la compra ya tenía una nota de crédito parcial (que había
  descontado puntos), al anularla se devuelve también ese descuento; el socio no queda con puntos de menos.
- **Una factura publicada no se puede borrar** (es la protección de Odoo, no cambió). Si hay que deshacerla,
  primero se devuelve a borrador, o se hace una nota de crédito.
- **El pago no se borra con la factura.** Al devolver a borrador, el pago sigue ligado a la factura; al
  eliminarla, queda como un pago sin aplicar al cliente. Odoo te lo avisa en las dos pantallas con un
  aviso de advertencia que se queda hasta que lo cierras («El pago … sigue ligado… Si era de prueba, cancélalo en
  Facturación › Clientes › Pagos» y, al borrar, «…quedó sin aplicar…»), y deja la misma nota en el chatter de
  la factura y de cada pago, así el rastro queda aunque luego se borre el borrador. El aviso nunca cambia ni
  frena el botón: si algo fallara, solo queda escrito en el registro del servidor.
- Si en el momento de borrar todavía había una compra activa (no es lo normal), el borrado la anula con su
  asiento contrario («Se eliminó la factura …») antes de dejarte seguir. Quien no tiene permiso de borrar
  facturas no puede anular puntos por esta puerta.

**Si la misma factura vuelve a quedar pagada** (se corrigió y se volvió a publicar con su pago puesto, o se
desconcilió y se pagó de nuevo; o una factura nueva usa un número que quedó libre), da sus puntos otra vez,
**una sola vez**: nunca hay dos compras activas de la misma factura. No vuelve a dar puntos una factura que se
anuló por una devolución total, ni una que Gerencia anuló a mano, ni una que ya tiene una nota de crédito
publicada; y cargar a mano una factura que ya dio puntos sigue prohibido («una factura, una carga»).

## Cambiar las reglas

Se edita `addons/dcasa_socios/data/puntos.json`, se sube la `version` y se hace un
PR. Las compras guardan la versión con que se calcularon, así que las viejas
siguen explicando sus puntos. Los valores en `null` o `PENDIENTE` no se rellenan
a ojo: el programa se niega a acreditar hasta que estén decididos.

## Migrar los socios de DCasa-Referidos

Si el Worker de Abrinay ya tiene socios reales en D1:

- **Fichas:** se exportan a partir del celular, el nombre, el padrino y el cumpleaños.
- **Saldos:** se importan como un asiento «Saldo migrado de la app anterior».
- **PIN:** se derivó con la pimienta de ese Worker, así que no se puede verificar
  aquí. Cada socio elige un PIN nuevo con «Reiniciar PIN» (gerencia) en la tienda, o se
  añade una verificación compatible si se comparte esa pimienta.
