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
| Canjes con código de 72 h; puntos reservados al pedir; un pendiente por premio; stock; se devuelven al vencer o cancelar | Los premios de descuento se **cobran dentro de la venta** («Cobrar premio»): el importe lo pone el premio y el código se sella al confirmar |
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

**Gerencia:**
- Hace ajustes con motivo.
- Anula compras.
- Suspende socios.
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
  aquí. Cada socio elige un PIN nuevo con «Reiniciar PIN» en la tienda, o se
  añade una verificación compatible si se comparte esa pimienta.
