# Brian de la tienda (el chat de ventas de dcasapty.com)

Aprobado por la dueña el 2026-11-13 (prototipo v2). Módulo `addons/dcasa_brian_tienda` (Odoo y la página) y el Worker de
Juan (`juan/`, rama aparte; su parte está en [JUAN.md](JUAN.md) › Brian de la tienda). **Viene encendido.**

## En palabras sencillas

- En la tienda web, en vez de la burbuja verde de WhatsApp, sale **la burbuja de Brian** (el robot). Los botones
  «Escríbenos por WhatsApp» de la página se quedan.
- Al tocarla se abre el chat: Brian saluda una sola vez («Hola, soy Brian. ¿Qué buscas hoy?»), busca muebles y los
  muestra en tarjetas que se deslizan (con foto, precio + ITBMS, disponibilidad y cantidad), deja el carrito listo,
  calcula el envío con la tarifa aprobada (escribiendo el barrio o tocando «Usar mi ubicación actual»), da la
  cotización del carrito en PDF y, para atención personal, abre WhatsApp con el mensaje ya escrito.
- **No guarda la conversación** ni crea contactos ni oportunidades. Las estrellas del final se guardan solo como número
  y fecha.
- De noche Brian duerme en la burbuja y, al abrir, dice que las vendedoras responden por WhatsApp en cuanto abran (el
  horario sale de Ajustes de Juan).
- **Sitio web › Brian de la tienda** (Gerencia y administradores): encender o apagar, el presupuesto del mes (30 USD de
  fábrica, aparte del de Juan), los topes de mensajes, cuánto va gastando y las calificaciones del mes.

## Cómo está armado

```
navegador ──(1) POST /dcasa/brian/v1/pase (CSRF) ──────────────► Odoo: pase firmado, 30 min
navegador ──(2) POST {JUAN_URL}/tienda/v1/mensaje (Pase …) ────► Worker de Juan ──► IA + herramientas de leer de Odoo
navegador ──(3) /dcasa/brian/v1/carrito/* (sesión, CSRF) ──────► Odoo: el carrito de verdad de la tienda
```

- **El navegador habla directo con el Worker**: una respuesta de IA tarda de 3 a 20 s y, pasando por Odoo, ocuparía un
  hilo y una conexión de la base todo ese tiempo.
- **El pase** (`models/pase.py`): `B64U(payload).B64U(HMAC-SHA256(llave, B64U(payload)))` con
  `llave = HMAC-SHA256(JUAN_WORKER_TOKEN, "brian-tienda-pase-v1")` (32 bytes crudos): **sin secretos nuevos**. El
  payload lleva `v`, `sid` (de la sesión del visitante: el mismo navegador, el mismo `sid`), `exp` (30 min), `red`
  (IPv4 /24 o IPv6 /64, formato exacto en `red_de` y en `scratchpad/brian_tienda/contrato_cambios.md` §2; el Worker
  ya no la compara con la conexión, porque el navegador puede llegar a la tienda por IPv6 y al Worker por IPv4) y
  `sitio`. Respuesta: `{ok, pase, worker, vence_en, noche, horario_texto}` o `{ok:false, motivo: apagado|verificacion|tope}`.
- **Tope de pases**: 20 por hora por conexión (cambiable): la IPv4 entera o la red /64 de la IPv6, como el borde y el
  Worker (nunca la /24, que comparten muchos clientes del mismo operador). Un contador por conexión y por hora
  (`dcasa.brian.tienda.cupo`, con
  una huella HMAC, nunca la IP), reservado en la misma transacción que el pase, bajo `pg_advisory_xact_lock` y con
  `INSERT … ON CONFLICT DO UPDATE`: con pedidos a la vez, PostgreSQL le da al segundo un error de serialización y Odoo
  repite la petición con la cuenta nueva (la lección B1 de la búsqueda por foto). La misma sesión no gasta otro cupo en
  la misma hora. Los contadores se borran a los dos días.
- **Turnstile** solo si el sitio ya lo tiene configurado (`website_cf_turnstile`, las dos claves); hoy está apagado.
- **El modelo nunca toca el carrito.** Brian *propone* (`proponer_carrito`); la página lo aplica con la sesión del
  visitante y le cuenta el resultado (`accion: confirmar_carrito`). Si el visitante toca «Agregar al carrito» en una
  tarjeta, la página lo aplica y lo dice sin gastar IA. Los precios y totales siempre salen de Odoo.
- **El carrito** (`controllers/main.py`): `POST /carrito/agregar` y `/carrito/cantidad` (`{producto_id, cantidad}`,
  1 a 20, 0 = quitar), `GET /carrito` y `GET /carrito/cotizacion.pdf`. CSRF en la cabecera `X-CSRF-Token` y cuerpo
  JSON de hasta 2 KB. Solo productos publicados en el sitio, que se agregan sin elegir nada y con precio (las reglas
  del «Agregar» de la portada); si hay que elegir medida, color o combo: `{ok:false, motivo:"elegir", url}` con la
  ficha. Cada visitante ve solo su carrito.
- **El PDF** (`report/cotizacion.xml`): las líneas, el subtotal, el ITBMS y el total de Odoo; «Cliente: (por
  confirmar)» salvo que lo pida un usuario con sesión y el carrito sea suyo. No se guarda como adjunto. 10 por hora por
  sesión.
- **Las estrellas**: `POST /calificar` `{estrellas}`, solo si esa sesión recibió un pase y una vez por `sid`
  (`dcasa.brian.tienda.calificacion`: número y fecha; la ven Gerencia y administradores; nadie la escribe por la
  interfaz).
- **Las herramientas** que usa el Worker son las de Juan, solo las de leer, con `origen: "tienda"` y sin conversación
  (Odoo vuelve a exigir la lista blanca: `buscar_productos`, `ver_producto`, `listar_categorias`,
  `buscar_conocimiento`, `horario_y_tienda`, `reglas_socios`, `cotizar_envio`). Para las tarjetas, cada producto trae
  además `producto_id`, `plantilla_id`, `imagen`, `ruta` y `agregable`; `ver_producto` acepta `producto_id`.
- **El envío por ubicación**: el Worker manda `lat`/`lon` a `cotizar_envio` (no están en el esquema de la herramienta:
  el modelo no las ve ni las inventa). La API de Juan las cambia por el lugar de la tabla más cercano (a 3 km como
  mucho, como la calculadora de choferes) **antes** de correr la herramienta: ni la auditoría (`brian.accion`) ni el
  registro ven las coordenadas. Devuelve lo de siempre más `por_ubicacion: true`; sin lugar cerca, `motivo: "lejos"`.
  `cotizar_envio` ya funciona sin conversación (sin cotización, con la promoción dicha con sus condiciones).
- **Los ajustes llegan al Worker** en `GET /dcasa/juan/v1/config`, clave `brian_tienda`
  (`activo`, `presupuesto_mes_usd`, `tope_sesion_hora`, `tope_red_hora`, `tope_dia`).
- **El gasto** lo manda el Worker en `/odoo/costos` (`tienda`) y Odoo lo pinta en su propio renglón de **Costos de IA**
  («Brian de la tienda (chat de la web)») y en los ajustes. **Nunca** se suma al gasto de Juan ni a «Por pagar a Meta»;
  sin dato del Worker dice «sin dato», nunca $0.

## La página (`static/src/js/brian_tienda.js`, `static/src/scss/brian_tienda.scss`)

- El prototipo v2 llevado tal cual: los 16 robots (`static/src/img/poses/*.webp`), las transiciones distintas por pose,
  la cabecera con WhatsApp, ampliar y cerrar, las tarjetas con selector de cantidad, las sugerencias, la ubicación, la
  ventana ampliada con la cuadrícula, las estrellas y la noche. Todo cuelga de `.o_dcbt` (clases `o_dcbt_*`).
- **La pose por página**: inicio (asomado), catálogo (con laptop), colchones (cama), cocina, oficina (escritorio),
  ficha (cinta métrica), carrito (bolsita), socios (fidelidad), visítanos (mapa), busca con una foto (marco), de noche
  (dormido). Al llegar a otra página la burbuja trae la pose anterior y cambia a la nueva con su transición.
- **No tapa nada**: en la ficha del celular sube sobre la barra fija de «Agregar al carrito»; y se hace a un lado
  mientras tendría debajo «Pregunta por este mueble por WhatsApp», «Agregar al carrito», un botón de WhatsApp o el de
  pagar del carrito. No sale en el pago (`/shop/checkout`, `/shop/payment`…), en `/my` ni en el panel; ahí, y con Brian
  apagado, vuelve la burbuja de WhatsApp.
- **Sobre las páginas guardadas en el borde**: el HTML es el mismo para todos (el WhatsApp del sitio, el horario y las
  poses en atributos `data-*`). El token CSRF, el pase y el carrito los pide el JS al abrir. Las claves de sesión del
  chat no vuelven «personal» la sesión (`dcasa_tienda_borde`, `CLAVES_NEUTRAS`) y el borde nunca guarda
  `/dcasa/brian/` (`edge/src/routing.ts`). Sin JavaScript la burbuja es un enlace a WhatsApp.
- **Al pasar de página** el chat sigue igual: lo conversado se recuerda en ese navegador (`sessionStorage`, se borra al
  cerrar la pestaña o a las 2 horas sin actividad), nunca en Odoo. La ubicación no se guarda ni ahí.
- **Accesible**: foco al abrir (el campo en la computadora, cerrar en el celular) y de vuelta a la burbuja al cerrar,
  Esc (primero vuelve del tamaño ampliado, después cierra), `aria-*`, botones de 44 px en pantallas táctiles; con
  movimiento reducido, quieto (ni entradas, ni reposo, ni transiciones de pose).

## Trampas que ya costaron

- **El panel no es un `<section>`**: el tema del sitio le pone `height: auto !important` a las `section` en el
  celular y el chat quedaba de 640 px con el campo de escribir fuera de la pantalla. Es un `<div role="dialog">`.
- **Nada de plantillas de texto (`` `…` ``) dentro de otra** en el JS: el minificador de Odoo les come los espacios del
  borde («abramos(atendemos», «2×Colchón»). Se arma con `+`; `test_ajustes.py` lo revisa.
- **Odoo guarda la portada y las páginas del sitio una hora** para los visitantes (`website.page`): un cambio del
  horario de Juan tarda hasta una hora (más lo que guarde el borde) en llegar a la pose de noche de la burbuja. El
  saludo de noche no, porque sale del pase. El interruptor sí se ve al momento (`set_param` limpia esa memoria y el
  borde se marca para rehacer).

## Mientras el Worker no esté

`addons/dcasa_brian_tienda/tests/worker_simulado.py` responde `POST /tienda/v1/mensaje` según el contrato (pase, CORS,
tarjetas solo de las herramientas de Odoo, `proponer_carrito`, ubicación, WhatsApp, estrellas y los errores). Lo usan
las pruebas del navegador y las capturas; se puede correr suelto:

```
python3 addons/dcasa_brian_tienda/tests/worker_simulado.py --puerto 8787 --token-worker <JUAN_WORKER_TOKEN> \
    --odoo http://127.0.0.1:8069 --token-odoo <JUAN_ODOO_TOKEN>
```

## Privacidad

La política (`/privacidad#brian-de-la-tienda`) lo dice en la sección de inteligencia artificial: lo que se escribe va
al proveedor de IA (el de Juan, con sus condiciones), la conversación no se guarda (como mucho 2 horas y 30 mensajes en
el Worker), la ubicación solo se usa para el envío y no se guarda, Brian no ve ni cambia datos ni compras, las estrellas
son número y fecha, y los topes cuentan por conexión sin guardar quién es. **Texto propuesto**: lo aprueba la dueña (y
el abogado) antes de producción.

## Pruebas

- `dcasa_brian_tienda/tests/test_pase.py`: la firma (comprobada aparte y con el Worker simulado), la red, el `sid`,
  CSRF, apagado, Turnstile, el tope por conexión (la IP entera, no la /24) y **dos pedidos a la vez** (dos conexiones reales), la limpieza.
- `test_carrito.py`: publicados, variantes, sin precio, cantidades, otro visitante, el PDF sin datos ajenos, el tope de
  PDF y las estrellas.
- `test_ajustes.py`: permisos, lo que llega al Worker, el renglón de Costos de IA, la Guía, la burbuja en lugar de la de
  WhatsApp, la página igual para todos, el editor del sitio (la trampa del error 500) y la privacidad.
- `test_navegador.py` (Chrome): el chat de punta a punta a 390 y 1366 px con el Worker simulado, la burbuja a 360, 390,
  430 y 1366 px en inicio, catálogo, ficha y carrito, que no tape la barra ni el botón de WhatsApp de la ficha, el
  movimiento reducido y la administradora abriendo el sitio en modo edición (tour `dcasa_brian_tienda_editor`).
- En `dcasa_conversaciones`: las tarjetas (`TestTarjetasDeLaTienda`), `cotizar_envio` sin conversación y por ubicación
  y la lista blanca de la tienda (`test_envios_juan.py`). En el borde: `routing.test.ts` y `bots.test.ts`.

## Brian (el del panel)

No necesita herramienta nueva para lanzar: el gasto ya lo ve en `costos_de_juan` cuando el Worker lo mande. Un
`resumen_de_brian_tienda` (gasto, presupuesto y calificaciones del mes) queda propuesto para después.
