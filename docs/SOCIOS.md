# Socios D'CASA — puntos y referidos (`dcasa_socios`)

El programa que diseñó Abrinay en
[`abrinay1997-stack/DCasa-Referidos`](https://github.com/abrinay1997-stack/DCasa-Referidos),
llevado **dentro de Odoo** para que haya un solo sistema. Se conservaron sus reglas
de negocio y sus defensas antifraude. Lo que aporta Odoo es que las ventas ya no
se teclean dos veces.

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
| Reclamar una ficha con puntos exige el código de la factura | Compra manual solo para facturas del sistema anterior (transición) |
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
3. Ve su saldo, invita por WhatsApp o con su QR, pide premios y ve su actividad.

**Premios:**
- **De descuento:** en la cotización se pulsa **Cobrar premio** y se escribe el código que enseña el cliente.
- **De producto:** se entregan desde *Socios → Canjes*.
- **Catálogo público** en `dcasapty.com/socios/premios`: foto, nombre y puntos de cada premio
  (lo que Gerencia edita en *Socios → Configuración → Premios*). «Pedir» crea el canje de siempre
  (código de 72 h, puntos reservados); la página enseña el estado y si se recoge o se enseña al pagar.

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
- La compra web suma puntos **solo cuando su factura queda pagada**, como cualquier otra, y sobre lo
  que de verdad pagó (ya con el premio descontado).

**Cuenta unificada:**
- El usuario de la tienda ve en `/my` su saldo, premios por recoger e invitados, con enlace a
  `/socios/cuenta`. `/socios` reconoce su sesión sin pedir PIN si su ficha ya es socio.
- Si tiene celular de Panamá pero todavía no entró al programa, `/socios` le invita a **activar sus
  puntos** eligiendo un PIN (misma ficha; no se le pide el código de la factura porque la sesión de la
  tienda ya prueba quién es). Si su celular ya es la llave de otra ficha, se le manda a entrar con PIN.
- Quien solo tiene sesión por PIN (sin cuenta de la tienda) ve en el carrito su saldo y cómo usarlo:
  entrar con su cuenta de la tienda o pedir un premio y dictar el código al coordinar el pedido.

**Gerencia:**
- Hace ajustes con motivo.
- Anula compras.
- Suspende y reactiva socios.
- Reinicia el PIN (le dicta al socio uno temporal) y desbloquea cuentas tras
  muchos intentos fallidos; queda una nota en el chatter con quién lo hizo.
  Estos botones exigen el grupo de gerente de ventas en el servidor, no solo en la vista.
- Edita premios (*Socios → Configuración → Premios*).
- Registra a mano facturas del sistema anterior.

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
