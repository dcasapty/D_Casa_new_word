# Ronda 7 · Socios en la web

Fecha: 03/10/2026 · Para: la dueña · Alcance: `addons/dcasa_socios` (herencias de `website_sale` y del
portal dentro del módulo, SCSS propio). No se tocaron `website_dcasa`, `dcasa_invoice`, `edge/` ni
`vendor/odoo`. Capturas (1440 y 390 px) en `capturas/`.

## Qué se pidió y qué quedó

| # | Pedido | Resultado |
|---|---|---|
| 1 | Catálogo de premios en la web | `/socios/premios`, público. Enseña foto, nombre, descripción, puntos y «quedan N» de cada premio que Gerencia edita en *Socios → Configuración → Premios*. «Pedir» crea el canje de siempre (código de **72 h**, de `puntos.json`; puntos reservados al pedir). La misma página enseña los códigos por recoger (con «Recógelo en la tienda» o «Enséñalo al pagar») y el historial con su estado. |
| 2 | Usar puntos en el carrito | En `/shop/cart`, el socio **con cuenta de la tienda** ve el paso **Usar mis puntos** (placa azul, premios como botones amarillos). Aplica un premio de descuento del catálogo: se pide el canje, los puntos salen del saldo y la orden lleva una línea negativa. Si lo quita, si el carrito baja del valor del premio, si el código vence o si el pedido se cancela (aun confirmado), los puntos vuelven con un **asiento contrario con motivo**. Nunca saldo negativo, nunca un premio mayor que el carrito, un premio por carrito, la línea no admite cantidad (ni por RPC). Respeta `saldoMinimoParaCanjear`. |
| 2b | Modo `premios` / `todo` | Parámetro `dcasa_socios.puntos_en_carrito`, también en *Ajustes → Ventas → Socios: puntos en el carrito web*. `premios` (por defecto): solo los premios del catálogo. `todo`: además un campo «usa los puntos que quieras» contra cualquier producto; el descuento sale de **`canje.puntosPorDolar`** en `puntos.json` (la cifra aprobada en `$decidido`: 100 puntos = $1), redondeado hacia abajo al centavo, con el mínimo de 500 y sin pasarse del carrito ni del saldo. Si esa cifra se pone en `null`, el modo se apaga solo y quedan los premios. **Los dos modos están probados.** |
| 3 | Cuenta unificada | El usuario de la tienda (portal) ve en `/my` una tarjeta azul con saldo, premios por recoger, invitados y «Mi cuenta de socio» → `/socios/cuenta`. `/socios` reconoce la sesión de la tienda sin pedir PIN (misma ficha `res.partner`, llave celular). Si tiene celular pero aún no es socio, `/socios` y `/my` le invitan a **activar sus puntos** eligiendo un PIN y aceptando los términos, en la misma ficha (sin crear otra). Si su celular ya es la llave de otra ficha, se le manda a entrar con PIN. «Salir» desde la sesión de la tienda cierra la sesión de la tienda. |
| 4 | Puntos de la compra web | Sin cambios de regla: suman **solo cuando la factura queda pagada**, sobre lo que de verdad pagó (ya con el premio descontado). Probado de punta a punta: confirmar no suma, facturar sin pagar no suma, pagar suma. |

## Decisiones que se tomaron (y se pueden revertir)

- **El canje libre es un premio técnico** (`dcasa_socios.premio_libre_web`, marcado `libre`): así el
  canje del carrito libre entra por el mismo `dcasa.canje._pedir` que todo lo demás (código, reserva,
  vigencia, reverso, reportes). No sale en el catálogo ni en la lista de Premios de Gerencia.
- **`puntos.json` sube a la versión 3** solo por añadir `canje.puntosPorDolar: 100`. Es la cifra que ya
  estaba aprobada en `$decidido` («100 puntos = $1 al canjear») y la misma escalera de los premios de
  arranque; antes vivía solo en texto y en una plantilla. Ninguna cifra de acumulación ni de referido cambió.
  La pantalla de inicio de `/socios` ahora lee esa cifra en vez de tenerla escrita.
- **Quien activa desde la tienda no teclea el código de la factura** aunque tenga puntos esperando: la
  sesión de la tienda (correo + contraseña) ya prueba que es él, y los puntos están en su misma ficha.
  El registro por QR sigue exigiéndolo.
- **Un canje aplicado en el carrito no se cancela desde la app** («quítalo desde el carrito»): si se
  cancelara desde la app, la línea negativa seguiría en el carrito hasta la siguiente visita.
- **El socio que solo tiene sesión por PIN no canjea en el carrito.** El carrito de un visitante no tiene
  ficha hasta el paso de dirección, y ligarlo al socio por celular mezclaría fichas. Se le enseña su saldo
  y dos salidas: entrar con su cuenta de la tienda, o pedir un premio y dictar el código al coordinar
  por WhatsApp.

## Decisiones pendientes (de la dueña)

1. **`premios` o `todo`.** Está en `premios`. Con `todo`, el 1 % devuelto se puede gastar en cualquier
   producto a partir de 500 puntos ($5); con `premios`, solo en la escalera de $5/$10/$25/$50/$100 que
   edita Gerencia. Se cambia en Ajustes sin despliegue.
2. **¿Se promueve la cuenta de la tienda a los socios del QR?** Hoy el socio del QR no tiene correo; para
   usar puntos en el carrito web necesita cuenta de la tienda. Opciones: pedir correo opcional en el
   registro de `/socios` y crear el usuario del portal con la misma ficha; o dejar la tienda web para
   «pedir premio + dictar el código». No se hizo nada sin decidirlo.
3. **Fotos de los premios.** El catálogo las enseña si Gerencia las sube (campo imagen del premio); sin
   foto sale una placa azul con el valor. ¿Quién las produce y en qué estilo?
4. **Un carrito abandonado con premio** reserva los puntos hasta que el código venza (72 h); al vencer,
   el cron devuelve los puntos y la línea sale del carrito en la siguiente visita. Si se quiere devolver
   antes, hay que decidir el plazo (no hay cifra en `puntos.json` para eso y no se inventó).
5. **`puntosMaximosPorCompra` sigue PENDIENTE DE CONFIRMAR POR MARCIAL** (ya lo estaba).

## Pruebas

`scripts/test.sh dcasa_socios,website_dcasa,dcasa_base` en base limpia (`dcasa_t_socios2`, puerto 8516):
__RESULTADO__. `ruff check addons`: limpio.

Nuevas (`tests/test_socios_web.py`, `@tagged('post_install')`): catálogo público y premio técnico oculto;
pedir desde el catálogo (código, estado, stock, cancelar); carrito en los dos modos (aplicar, quitar,
mínimo, saldo insuficiente, premio mayor que el carrito, un premio por carrito, cantidad bloqueada por RPC,
carrito que se achica, código vencido, cancelar pedido en borrador y confirmado → reverso con motivo, el
libro no se edita); `todo` con `puntosPorDolar` en `null` se apaga; compra web suma solo al pagar; cuenta
unificada (`/socios` reconoce la sesión, activar con PIN, sin celular, `/my`, salir); superficie RPC (los
caminos del carrito son privados; portal no crea el wizard ni edita premios); ninguna cifra de puntos en
plantillas, controladores ni modelos; la equivalencia del canje sale de las reglas (se cambia en el JSON y
cambia en pantalla).

## Capturas

| Archivo | Qué se ve |
|---|---|
| `premios-visitante-*.webp` | Catálogo público, con «Entra para pedirlo» |
| `premios-socia-*.webp`, `premios-socia-con-canje-*.webp` | Catálogo con sesión: saldo, «Pedir», código por recoger |
| `carrito-visitante-*.webp` | Carrito del visitante: invitación a entrar |
| `carrito-usar-puntos-*.webp` | Carrito de la socia: paso «Usar mis puntos» (modo `premios`) |
| `carrito-premio-aplicado-*.webp` | Premio aplicado: línea negativa y botón para quitarlo |
| `carrito-modo-todo-*.webp`, `carrito-modo-todo-aplicado-*.webp` | Modo `todo`: campo de puntos y 733 puntos = $7.33 |
| `my-socia-*.webp`, `my-activar-*.webp` | `/my` con la tarjeta del programa (socia / cliente sin PIN) |
| `socios-activar-*.webp` | `/socios` para el cliente de la tienda: activar con PIN |
| `cuenta-socia-*.webp` | `/socios/cuenta` entrando con la sesión de la tienda |
