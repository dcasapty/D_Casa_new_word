# Ronda 7 · Socios en la web

Fecha: 03/10/2026 · Para: la dueña · Alcance: `addons/dcasa_socios` (herencias de `website_sale` y del
portal dentro del módulo, SCSS propio). No se tocaron `website_dcasa`, `dcasa_invoice`, `edge/` ni
`vendor/odoo`. Capturas (1440 y 390 px) en `capturas/`.

## Qué se pidió y qué quedó

| # | Pedido | Resultado |
|---|---|---|
| 1 | Catálogo de premios en la web | `/socios/premios`, público. Enseña foto (o una placa azul con el valor si no hay foto), nombre, descripción, puntos y «quedan N» de cada premio que Gerencia edita en *Socios → Configuración → Premios*. «Pedir» crea el canje de siempre (código de **72 h**, de `puntos.json`; los puntos se reservan al pedir). La misma página enseña los códigos por recoger y el historial. |
| 2 | Usar puntos en el carrito | En `/shop/cart`, el socio **con cuenta de la tienda** ve el paso **Usar mis puntos** (placa azul, premios como botones amarillos). Elegir un premio de descuento pide el canje, saca los puntos del saldo y pone una línea negativa en la orden. Si lo quita, si el carrito baja del valor del premio, si el código vence o si el pedido se cancela (aun confirmado), los puntos vuelven con un **asiento contrario con motivo**. Nunca saldo negativo, nunca un premio mayor que el carrito, un premio por carrito, la línea no admite cantidad (ni por RPC). Respeta `saldoMinimoParaCanjear`. |
| 2b | Modo `premios` / `todo` | **Decidido por ti: el canje es solo por premios que define el administrador.** Queda en `premios` (valor por defecto del parámetro `dcasa_socios.puntos_en_carrito`). El modo `todo` (puntos sueltos contra cualquier producto, a `canje.puntosPorDolar` de `puntos.json`) existe y está probado, pero **no está activo**; se cambiaría en *Ajustes → Ventas* sin despliegue. |
| 3 | Cuenta unificada | El usuario de la tienda ve en `/my` una tarjeta azul con saldo, premios por recoger, invitados y «Mi cuenta de socio». `/socios` reconoce la sesión de la tienda sin pedir PIN (misma ficha, llave = celular). Si tiene celular pero aún no es socio, se le invita a **activar sus puntos** con un PIN en la misma ficha. Si su celular ya es la llave de otra ficha, se le manda a entrar con PIN. |
| 4 | Puntos de la compra web | Sin cambios de regla: suman **solo cuando la factura queda pagada**, sobre lo que de verdad pagó (ya con el premio descontado). Probado de punta a punta: confirmar no suma, facturar sin pagar no suma, pagar suma. |
| 5 | Premio de ejemplo | **«Dos almohadas» por 400 puntos**, de producto, ligado a `ALMOHADA001` (ALMOHADA MICRO GEL SLEEP ESSENTIALS) × 2 si ese producto ya está en la base; si no, se crea sin producto y no falla. Valor y costo salen del precio y costo del producto (sin producto, 0). Se crea **una sola vez**: Gerencia lo edita o archiva y una actualización no lo resucita. Ver la duda del mínimo abajo. |

## Lo que tienes que decidir

1. **El mínimo de 500 puntos y las almohadas de 400.** Hoy `saldoMinimoParaCanjear` se compara con
   **los puntos del premio**, no con el saldo: ningún premio puede costar menos de 500. Resultado: las
   almohadas salen en el catálogo con el botón «Pedir» (si el socio tiene 400 o más), pero al pedirlas
   sale «El canje mínimo es de 500 puntos» y no se descuenta nada. Opciones:
   - **a)** El mínimo es de **saldo** (como dice su nombre): hay que tener al menos 500 para canjear
     cualquier cosa, y entonces las almohadas (400) se pueden pedir. Es un cambio de código pequeño.
   - **b)** El mínimo es **por premio** (como hoy): subir las almohadas a 500 o más, o bajar el mínimo
     en `puntos.json` (es una cifra del programa: la cambias tú).
   No se cambió nada en `puntos.json`. Hasta que decidas, conviene **archivar** las almohadas o dejarlas
   sabiendo que el botón da ese aviso.
2. **¿Se promueve la cuenta de la tienda a los socios del QR?** El socio del QR no tiene correo; para
   usar puntos en el carrito web necesita cuenta de la tienda. Opciones: pedir correo opcional en el
   registro de `/socios`, o dejar la web para «pedir premio + dictar el código por WhatsApp».
3. **Fotos de los premios.** El catálogo las enseña si Gerencia las sube; sin foto sale la placa azul.
   ¿Quién las produce y en qué estilo? (Si `ALMOHADA001` ya tiene foto al crear el premio, se usa esa.)
4. **Un carrito abandonado con premio** reserva los puntos hasta que el código venza (72 h). Si se
   quiere devolver antes, hay que decidir el plazo (no hay cifra en `puntos.json` y no se inventó).
5. **`puntosMaximosPorCompra` sigue PENDIENTE DE CONFIRMAR POR MARCIAL** (ya lo estaba).
6. **`puntos.json` versión 3** añadió `canje.puntosPorDolar: 100`, la cifra ya aprobada en `$decidido`
   («100 puntos = $1»). Solo la usa el modo `todo` (inactivo) y la pantalla de inicio de `/socios`.
   Si prefieres que no esté, el modo `todo` se apaga solo con `null`.

## Decisiones técnicas (reversibles)

- **El canje libre es un premio técnico** (`premio_libre_web`, marcado `libre`): no sale en el catálogo.
- **Un canje aplicado en el carrito no se cancela desde la app** («quítalo desde el carrito»).
- **El socio que solo entra con PIN no canjea en el carrito** (su carrito no tiene ficha hasta la
  dirección y ligarlo por celular mezclaría fichas): se le enseña su saldo y cómo usarlo.
- **Doble gasto imposible** (arreglado en esta ronda): pedir un premio escribe la fila de la ficha antes
  de leer el saldo. Antes, la app y el carrito a la vez podían gastar dos veces el mismo saldo porque
  Odoo trabaja con fotos de la base (REPEATABLE READ) y el candado de lectura no lo impedía.
- En el carrito, la línea del premio enseña el importe **sin ITBMS** (−$9.35 para un premio de $10),
  igual que las demás líneas; la placa azul y el total sí dicen −$10.00. Si confunde, se puede cambiar.

## Pruebas

`scripts/test.sh dcasa_socios,website_dcasa,dcasa_base,dcasa_invoice` en base limpia
(`dcasa_t_socios3`, puerto 8522): **333 tests**, todos en verde salvo **uno ajeno a esta ronda**:
`website_dcasa` `TestPaginasBlackWeekend.test_banda_en_la_portada_antes_de_los_carruseles` espera un
`<source type="image/webp">` para un producto de prueba **sin foto** (viene del merge con
`claude/merge-rama-to-main-ty3koz`; `website_dcasa` queda fuera del alcance). `ruff check addons`: limpio.

Tests de esta ronda (`@tagged('post_install', '-at_install')`):
- `tests/test_socios_web.py`: catálogo público y premio técnico oculto; pedir desde el catálogo;
  carrito en los dos modos (aplicar, quitar, mínimo, saldo insuficiente, premio mayor que el carrito,
  un premio por carrito, cantidad bloqueada por RPC, carrito que se achica, código vencido, cancelar
  pedido en borrador y confirmado → reverso con motivo, el libro no se edita); `todo` sin la cifra se
  apaga; la compra web suma solo al pagar; cuenta unificada (`/socios` reconoce la sesión, activar con
  PIN, sin celular, `/my`, salir); superficie RPC; ninguna cifra de puntos en plantillas, controladores
  ni modelos; pedir un premio escribe la ficha antes de leer el saldo.
- `tests/test_premio_ejemplo.py`: el premio de ejemplo se crea al instalar (400, producto, × 2,
  editable); se liga al producto si existe y toma su precio y costo; sin producto se crea igual; no
  resucita si se archiva o borra; el mínimo de `puntos.json` se aplica al premio (comportamiento actual,
  documentado); un premio de producto no entra en el carrito.

## Capturas

Base de prueba con un «Producto de prueba (captura)» de $100 y una socia de prueba con 1,500 puntos.

| Archivo | Qué se ve |
|---|---|
| `premios-visitante-1440/390.webp` | Catálogo público, con «Entra para pedirlo» |
| `premios-socia-1440/390.webp` | Catálogo con sesión: saldo, «Pedir», «Te faltan…», las almohadas de ejemplo |
| `carrito-usar-puntos-1440/390.webp` | Carrito de la socia: paso «Usar mis puntos» (modo `premios`) |
| `carrito-premio-aplicado-1440/390.webp` | Premio de $10 aplicado: línea negativa, total y botón para quitarlo |
| `carrito-visitante-1440.webp` | Carrito del visitante: invitación a entrar |
