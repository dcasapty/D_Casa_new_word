# Prioridades vigentes

Puesto al día el **2026-11-20** (todo lo nuevo, Yappy directo incluido, está unido en la rama de trabajo, sin desplegar: ver «Estado al 2026-11-20»). Antes, el **2026-11-18** (**todo está en producción**: el Black Friday desde el 16 —Desplegar 77 y Juan 28—, la portada nueva desde el 17 —CI/CD 377, PR #127— y **la segunda entrega completa desde el 18** —CI/CD 380 y Desplegar Juan 29, squash `d2ba8caf`, PR #128—. Ya no queda nada esperando en la rama de trabajo). Es el orden en que se trabaja: cada sesión lo lee al empezar y lo pone al día al
terminar (ver [LEEME_PRIMERO.md](LEEME_PRIMERO.md)). Aquí va **un solo estado**, el de hoy; lo que pasó cada día está en
la bitácora de LEEME_PRIMERO (y lo más viejo en [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md)).

Cada cosa nueva pasa por capturas a la dueña, pruebas, staging y, si toca dinero, permisos o Socios, revisión adversarial.
**Desde el 2026-11-13 la dueña no pide su visto bueno para pasar a producción** («Y no esperes mi aprobación para pasar
la producción. Apruébalo y punto.»); la revisión adversarial no se salta (reglas en LEEME_PRIMERO §2).
**Excepción desde el 2026-11-20: todo cambio de diseño se le muestra en capturas antes/después y espera su «sí»** («antes de cualquier cosa o
cambio en el diseño me gustaría verlo antes»; ver LEEME_PRIMERO §2).

## Estado al 2026-11-21

- **En producción desde el 2026-11-21 02:24 UTC: `f81d669d4ca4`** (PR #130, squash `d3349ed1`, CI/CD #383, Desplegar #78, digest
  `sha256:706e7954…`): «Forma de pago» en facturas, ventas por día, carrusel configurable, Andrés ampliado, rediseño de la pasarela, legibilidad
  y retoques, que la dueña aprobó. **Tilopay y Yappy directo están instalados y apagados; la comisión web no tiene versión de reglas (solo
  mide).** Antes: `d2ba8caf` (2026-11-18).
- **Falta, en este orden:** (1) **llevar a producción los cierres R9-1 a R9-5** (las dos puertas que halló RV8b en los permisos del pago en
  línea: `default_transaction_ids` del pedido y la factura creada a mano con el cobro de otro; más `action_refund`/`capture`/`void` y los
  caracteres invisibles de `cita`). **Ya están unidos a la rama de trabajo y los aprobó la revisión independiente RV8c** (sin hallazgos que
  bloqueen; solo INFO, ver la bitácora): falta CI → staging → producción, **obligatorio antes de encender cualquier pago**. (2) Lo que depende de
  otros: claves de Tilopay y Yappy en Cloudflare (nunca por el chat), el programa de pruebas de Yappy y la compra de ensayo, las respuestas de Yappy y
  Cloudflare (YAPPY.md §15), la política de privacidad (§16), las decisiones **R7-4 (Nómina confirma cobros) y R7-7 (rastro del botón de Caja)**,
  aceptar el límite R8-3 (un cobro suelto del mismo cliente manda el aviso a revisión humana), las cifras de la comisión web y su tratamiento contable.
- **Para los jefes:** el informe de ChatGPT quedó contrastado con el código (CONTEXTO_AGENTICO); hay tablero y un audio/video de 38 minutos con
  voz gratis; la voz profesional (≈ US$7.30) espera el «sí» de la dueña. **Por comprobar en vivo:** CRM automático y cotizaciones sin vincular,
  111 frente a 93 cotizaciones, margen de octubre y los $44.96 de IA.

## Estado al 2026-11-17

- **Lo último en producción: la segunda entrega completa** (2026-11-18, CI/CD 380 y Desplegar Juan 29,
  `app_version` `d2ba8caff071`, PR #128): Andrés mejor vendedor, notas de voz, micrófono del chat, «Armar
  combo» con los precios de verdad y la regla «un premio nunca sale más caro». Antes, la portada nueva
  (2026-11-17, CI/CD 377, PR #127) y el Black Friday (2026-11-16, Desplegar 77 y Juan 28).
- **Producción funciona desde el 2026-10-13** y **`dcasapty.com` (y `www`) apunta al sistema nuevo desde el
  2026-10-27** (Desplegar 31). Odoo y el borde: **Desplegar 76** (15 nov, PR #122: bandas en azul noche, pie claro, menú sin «Escríbenos», sección de contacto y el carrito en el chat de la tienda; antes, Desplegar 75 (15 nov, PR #121: la portada v3, con secciones compactas, el carrito como ícono, la paleta nueva y la barra del chat de vidrio; antes, Desplegar 74 (15 nov, PR #120: Brian siempre activo de noche, con dos interruptores); antes, Desplegar 73 (14 nov, PR #119: la burbuja de Brian cambia de robot con el scroll); antes,
  Desplegar 72, PR #118: Brian de la tienda, el chat de ventas en la web, y el
  lote 2 de la web: horario, mapa y opiniones; antes, Desplegar 71, PR #117: avisos de Telegram ordenados con la noche sin clientes, lote 1 de
  la web, «Busca con una foto», el robot como ícono de Brian y el horario de la tienda; antes, Desplegar 70, PR #116:
  comentarios de Instagram y Facebook, apagados; antes, Desplegar 69, PR #115: Juan ya no dice «no lo manejamos» de lo que no está publicado; antes, Desplegar 68, PR #113: Juan cotiza envíos con la promoción, reparto justo y Costos de IA con «Pagar»; antes, Desplegar 67, PR #112: el modo oscuro; el 11 nov, Desplegar 66 con
  entregas igual que Bodega y «Más datos», y antes, Desplegar 65 con el Inicio nuevo, el celular al entrar y la caja del chat, y Desplegar 64 con
  los 21 arreglos de la auditoría visual). Juan: **Desplegar
  Juan 27** (15 nov, PR #120: `avisar_cerrado`; Juan 26, 14 nov, PR #118: Brian de la tienda, `POST /tienda/v1/mensaje` y el Durable Object `TiendaSesion`;
  Juan 25, 14 nov, PR #117: `sin_leer` con su motivo, el comprobante solo si es un pago hecho y la foto de la tienda;
  Juan 24, 13 nov, PR #116; Juan 23 trajo «no lo manejamos» y Juan 22 la segunda puerta de Instagram, apagada). La **versión estable 4** es la anterior (Desplegar 63 + Juan 20)
  ([VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md)). El contenedor instala 31 de los 32 módulos de `addons/` (todos
  menos `dcasa_fe_pa`, a propósito); desde Desplegar 72, 32 de 33 (entró `dcasa_brian_tienda`).
- **⚠ Messenger e Instagram NO les llegan a los clientes (descubierto el 2026-11-12):** solo a cuentas con papel en la
  app (la app «D'CASA Juan» no tiene la aprobación de Meta). Ver «Lo que sigue» (punto 00) y JUAN_CANALES §3.
- **Juan atiende WhatsApp (API oficial de Meta), Messenger e Instagram** (estos dos, solo a cuentas con papel en la app: ver arriba), con fotos en los tres, y Telegram. WhatsApp
  desde el 2026-11-02 (el 131070 del 9 y 10 nov se resolvió con «redireccionar conversación» a «D'CASA Juan»);
  Messenger desde el 2026-11-09; Instagram desde el 2026-11-10 (por la página, misma app y llave). El puente de
  WhatsApp por QR (`puente-wa/`) **nunca se desplegó** a producción. Ver [JUAN_CANALES.md](JUAN_CANALES.md).
- **Enlace para choferes:** encendido por la dueña el 2026-11-11 ([ENVIOS.md](ENVIOS.md)).
- **Sofía, la asistente del CRM**, está en producción desde el 2026-11-05 ([SOFIA.md](SOFIA.md)).
- **El correo a clientes (Resend) está encendido** desde el 2026-10-27 ([CORREO.md](CORREO.md)).
- Lo último que entró (noviembre): Valor del inventario y cobrado por forma de pago; medios, Origen y cotizaciones que
  vencen solas en Conversaciones; tres paneles en el Inicio; reparto solo a vendedoras activas; clientes repetidos
  («Es esta persona»); tasa de cierre en el Resumen de Juan; Sofía. Detalle en la bitácora.

## Lo que sigue, en orden

**0. SUBIR LA RAMA UNIDA (2026-11-20).** Facturas con «Forma de pago» y Exportar, ventas por día, carrusel y Andrés ampliado, Tilopay y
la comisión web están en `claude/merge-rama-to-main-ty3koz` con sus revisiones independientes hechas (la de la comisión, segunda
vuelta en curso). Subir con la receta de LEEME_PRIMERO §3: Tilopay **apagado** y la comisión **sin versión de reglas**.
Después, y solo con lo que va aquí:
- **Tilopay a staging** con las claves de la cuenta de pruebas de Tilopay (`tilopay.com/developers/registro`), cargadas por la
  dueña en Cloudflare (nunca por el chat) con `TILOPAY_ENTORNO=prueba`; una compra de ensayo; pedirle a Soporte de Tilopay que
  registre `https://dcasapty.com/payment/tilopay/webhook`, la vigencia de la página de pago y los datos de `docs/TILOPAY.md` §8.
  **No cobrar de verdad** hasta cerrar la lista de `docs/TILOPAY.md` §9.1.
- **Yappy directo** (cuando la dueña diga que sí a las capturas y pase la revisión): cargar en Cloudflare, en staging, `YAPPY_ID_COMERCIO`,
  `YAPPY_CLAVE_SECRETA` (se ve **una sola vez** en Yappy Comercial; se pega directo, nunca por el chat) y `YAPPY_DOMINIO` (letra por
  letra como se escribió en Yappy Comercial); pedir a `botondepagoyappy@bgeneral.com` el acceso al programa de pruebas y las
  preguntas de `docs/YAPPY.md` §8 (validez del token, `Bearer`, `paymentDate`, reintentos del aviso y su código de respuesta,
  IPs de origen, campo del código de error); una compra de ensayo; conciliar a diario contra el reporte de Yappy Comercial.
  **No cobrar de verdad** hasta cerrar la lista de `docs/YAPPY.md` §7 y §12. La contadora decide el tratamiento de la comisión de
  Yappy (no está modelada). Revisar a Juan cuando se encienda (`docs/YAPPY.md` §11).
- **Comisión web:** Gerencia define porcentaje, tarifa fija, quiénes reciben y las fechas de pago desde Ajustes; la contadora
  documenta el tratamiento (no es salario, sin descuentos de planilla). Decisiones abiertas: limitar el pago por código VEN a vendedores
  externos, y afinar el «caso gris» de Andrés (la vendedora que solo confirma). Ver `docs/COMISION_WEB.md`.
- **Confirmar** que el parámetro `web.json.enabled` no está puesto en producción (la ruta `/json/1/…` del núcleo pide el permiso de
  exportar pero no el límite por modelo).
- **La contadora** revisa el diario bancario «Tilopay» (código `TLP`) y su cuenta, que se crean al desplegar aunque el proveedor siga
  apagado, y decide si un cobro conciliado con el extracto debe contar con el diario del banco en «Forma de pago»
  (`docs/CONTABILIDAD.md`).
- **Plan futuro:** factura de emergencia sin conexión, un solo archivo HTML (issue #129).

**LA PORTADA NUEVA YA ESTÁ EN PRODUCCIÓN** (2026-11-17, ejecución 377 de CI/CD a mano desde `main`, squash
`447d6efe`, PR #127). El hero es un fondo en movimiento: las fotos del catálogo a pantalla completa, en orden al azar,
con fundido y zoom lento, sin mandos ni nombres, y el contraste resuelto en azul de marca (la dueña eligió la opción 5
de cinco). Comprobado en vivo en computadora y en celular. Subió en una rama aparte (`claude/portada-solo`, sacada de
`main`, solo `addons/website_dcasa/`), así que **no arrastró** el resto de la segunda entrega.

**Pendiente que salió de ahí:** el contrato visual del panel de Juan falla a 390 px (`panel-lista-390` 7,7 % y
`panel-conexiones-390` 13,7 % de píxeles distintos). Viene de `main`, no de la portada. Hay que mirar si es un cambio
a propósito al que le faltó regenerar las referencias o una falla de verdad en el celular.

**EL BLACK FRIDAY YA ESTÁ EN PRODUCCIÓN** (2026-11-16, Desplegar 77 y Juan 28; PR #126, squash `a904ec65`,
`app_version` `26b357d3bd51…`). La campaña del sitio desde el panel, los combos inamovibles con la regla del par y el
chat de la web como Andrés. Comprobado: salud sana, portada, `/promociones` en 404 mientras no haya campaña y el chat
diciendo «Hola, soy Andrés». **Falta que la dueña cree la campaña** (los pasos están en `RESUMEN_PARA_LA_DUENA.md` y
en el plan): el Black Friday es el **viernes 27**.

**DECIDIDO (la dueña, 2026-11-17): «avisarle y no dejar canjear».** Era el bloqueante que frenaba la segunda
entrega: un premio de puntos podía tirar la compra por debajo del mínimo de la promoción de envío y hacerle perder el
envío gratis (carrito de $205 sin ITBMS, premio de $10 → la compra queda en $195.65 y paga $45 de envío: gastaba
puntos para pagar más). **Ya está programado, probado y revisado** (ver la bitácora del 2026-11-17 y
[SOCIOS.md](SOCIOS.md)): si lo que pagaría de envío iguala o pasa lo que le descuenta el premio, se le avisa con las
dos cifras y no se canjea; si el premio descuenta más de lo que perdería, se deja pasar porque ahí sí le conviene
(eso lo decidí yo y se le dijo). Cubre el carrito web y el mostrador, y al quitar un premio la promoción del envío se
vuelve a ofrecer.

**La segunda entrega YA ESTÁ EN PRODUCCIÓN** (2026-11-18, CI/CD 380 y Desplegar Juan 29). Lo que dejaron sus
revisiones y sigue abierto, sin bloquear nada:

- *Menores que siguen abiertos:* `/carrito/envio` acepta cualquier `lugar_id` sin que Andrés lo haya cotizado; dos
  `GET` escriben en la base; el mismo canje puede quedar en dos ventas abiertas; y el carrito sigue ofreciéndole al
  socio premios que el servidor va a rechazar (el aviso llega después del clic, no antes).
- *(Los tres «importantes» de esta lista —el total negativo en el mostrador, la guardia del Worker con «ok?» y el
  premio viajando al chat— se arreglaron el 2026-11-17; ver la bitácora.)*

**Ya arreglado el 2026-11-17** (en la rama, sin subir, a la espera de la decisión de arriba):

- La pantalla **«Armar combo»** ya muestra los precios de verdad: `precio` es lo que la pieza cuesta suelta ese día y
  `precio_linea` lo que se cobra en el combo (238 pruebas en verde).
- El **total negativo en el mostrador**: la guarda del premio pasó a `_aplicar_en_venta` (los dos caminos) y
  `action_confirm` tiene una última red.
- La **guardia del Worker**: ya no se salta escribiendo «…ok?» sin abrir la pregunta, ni poniendo una pregunta en medio.
- El **premio de Socios** ya no viaja al chat entre los productos: va en «extras», con el envío.
- **PR de Dependabot #98 unido** (parches de `@ai-sdk/*` y `ai` en `juan/`): CI completo en verde y revisado que los
  cambios de comportamiento del registro tocan APIs que Juan no usa. **No cambia producción hasta el próximo
  «Desplegar Juan».**

Queda del Black Friday, anotado y sin bloquear:

- La web y Juan publican la línea de combo escrita en el Excel («Combo con colchón $649.99»), un texto que nadie
  recalcula y que puede no coincidir con lo que cobra la cotización. Viene de antes.

0000000. **Primero termina el 000000 de abajo (Black Friday). Después, la siguiente ronda que pidió la dueña, con su plan
        escrito en [PLAN_ANDRES_VOZ_PORTADA.md](PLAN_ANDRES_VOZ_PORTADA.md).**
        Andrés como vendedor (carrito siempre a mano en el chat, envío en la cotización, reacción al quitar o vaciar,
        cambiar cantidades conversando, vitrina ordenada), notas de voz para Andrés y Brian sin guardar el audio, y la
        portada (hero en carrusel con camas propias y una sección «de cine» tipo PanaClaw).

000000. **Black Friday (viernes 27 de noviembre) y «Andrés»: listos en la rama, sin subir a producción.** La sesión se
       pausó el 2026-11-16 por el límite de uso. El código está en `cae5e57` (la rama tiene después solo commits de
       documentos). Hecho: la campaña del sitio desde el panel, el chat de la tienda renombrado a Andrés, las pruebas
       nuevas y **tres vueltas de revisión adversarial** sin bloqueantes (el detalle de lo que quedó sin hacer está en el
       plan). Pruebas locales del 2026-11-16 (`dcasa_test_bf4`, con el código de `11f9822`): 827 de 827 en verde. **Para terminar, en orden** (el paso 0 de
       [PLAN_ANDRES_VOZ_PORTADA.md](PLAN_ANDRES_VOZ_PORTADA.md) trae los comandos):
       0. **Antes de nada: los combos son inamovibles** (la dueña, 2026-11-16). En un combo armado cama + colchón, la
          campaña no rebaja nada. Hay que dejar un interruptor para permitirlo, apagado. Es el paso 1 del plan; toca
          dinero, así que lleva revisión adversarial.
       1. Correr otra vez las pruebas locales: `website_dcasa`, `dcasa_tienda_borde`, `dcasa_brian_tienda`,
          `dcasa_conversaciones` (las clases de precios), `dcasa_socios`, `dcasa_abonos` y `dcasa_meta_catalogo`, más
          `cd juan && npm test && npm run typecheck`.
       2. CI con staging en la rama, PR `[skip ci]`, squash, **Desplegar** con `respaldo_previo` y **Desplegar Juan**
          (cambió `juan/src/tienda`).
       3. Confirmar que el chat saluda «Hola, soy Andrés» y que /promociones da 404 mientras no haya campaña.
       4. Avisarle a la dueña y explicarle los pasos del panel (están en el plan). Hay que dejarlo en producción con días de
          margen antes del 27, para que alcance a marcar los productos.
       Preguntas abiertas para ella:
       - **I6.** ¿El precio de campaña vale también en la tienda física, o solo en la web? Hoy vale en todos lados.
       - **Ya decidido:** los combos son intocables, porque son una promoción permanente. La línea del combo sale
         siempre con su precio de siempre (cambio del 2026-11-16, en la rama).

00000. **Portada v3: en producción desde el 2026-11-15, 08:3x UTC** (Desplegar 75, PR #121; aprobada por la dueña con
       capturas: «apruebo todo, despliégalo todo cuanto antes»; comparación <https://claude.ai/artifact/XQti28eQjFLDzT1Z9CpsRH>).
       Secciones que caben en una pantalla, categorías con «N productos», carriles en una fila con flechas, carrito como
       ícono, «Quedan pocas» / «Agotado» con la regla de la ficha, hueso #F6F5F2 y la barra del chat de vidrio. Falta que
       la dueña lo mire en su iPhone. Ideas para ofrecerle: «Lo más buscado» con lo que tiene existencia primero y Black
       Weekend con el carril nuevo (detalle en la bitácora, 2026-11-15 (2)).

0000. **Brian de la tienda y lote 2 de la web: en producción desde el 2026-11-14, 07:46 UTC** (Desplegar 72 y Juan 26;
      la dueña: «vamos a subirlo lo antes posible»). Módulo nuevo `dcasa_brian_tienda` (chat de ventas en la web con el motor de Juan,
      ver [BRIAN_TIENDA.md](BRIAN_TIENDA.md)) y, del lote 2, el horario en Visítanos y el pie (sale de Ajustes de
      Juan), el mapa de Google con permiso de cookies y las opiniones de productos aprobadas por Gerencia. Orden:
      **Juan antes que Odoo** (el Durable Object `TiendaSesion` es la migración v2 del Worker). Falta que la dueña lo
      pruebe en su celular y diga qué le parece. Después:
      - **Antes del 1 de diciembre: «Por pagar a Meta» en el cambio de mes** (revisión adversarial, tercera vuelta):
        lo que Brian de la tienda gasta en Meta después del último pago se pierde si el pago siguiente cae en otro mes
        (el Worker solo da el mes en curso; la pantalla ya dice que la cifra es un mínimo). Arreglo: una foto diaria de
        lo que lleva la tienda en Meta, como `dcasa.juan.costo.dia`, o que el Worker mande también el mes anterior.
        Prueba del revisor guardada en la carpeta de trabajo de la sesión (`pendiente_meta/`): pasarla al módulo.
        Solo importa si Juan usa el modelo de Meta.
      - **Turnstile en el chat de la tienda** antes de anunciarlo en grande (el código ya lo soporta: falta crear la
        llave en Cloudflare y ponerla en el sitio). Sin él, unas pocas redes pueden agotar el tope del día de Brian (no
        el dinero: el tope de 30 USD aguanta).
      - **Comedores:** Brian dice «Comedores no los manejamos» (no hay comedores publicados). Confirmar con la dueña.
      - **Herramientas del Brian del panel** para lo nuevo: `resumen_de_brian_tienda` (gasto, presupuesto y estrellas) y
        opiniones por aprobar.
      - **Tilopay** (la semana del 2026-11-16): pasarela de pago con todos los métodos que tenga activos (Visa,
        Mastercard, «Pase U», Yappy). Odoo no trae proveedor de Tilopay: hay que hacerlo; las claves solo en
        Cloudflare, nunca en el chat.
      - **Search Console:** la dueña pedirá ayuda para dar de alta el sitio (pasos para el jefe).
      - **El mapa:** el borde solo manda `frame-ancestors 'self'` (no `frame-src`), así que el `iframe` de Google no se
        bloquea; comprobarlo en producción con el permiso de cookies aceptado.
      - **«Tu compra lista»** (de la cotización de WhatsApp al carrito con un código o enlace, con lista de deseos):
        borrador de diseño hecho en la sesión del 2026-11-13; esperar el informe de la comparación con Carbone y las
        decisiones de la dueña.
      - **Fotos y medidas de los productos:** las sube Marketing.

00. **Messenger e Instagram para todos los clientes** (la dueña, 2026-11-12, con el diagnóstico de un amigo y de otro
    Claude: los mensajes de clientes reales nunca llegan; solo los de cuentas con papel en la app). Plan:
    - **Messenger:** el único camino es la revisión de la app de Meta (acceso avanzado de `pages_messaging`,
      `pages_manage_metadata`, «Business Asset User Profile Access») con el **negocio verificado**, y la app «En vivo».
      Antes: revisar a qué portafolio pertenece la app (si es el de la agencia Juancito Ads, pasarla al de D'CASA).
    - **Instagram:** probar primero «Instagram API con inicio de sesión de Instagram» con la cuenta propia de D'CASA
      (según Meta, si la app solo sirve la cuenta propia basta el acceso estándar, sin revisión; hay fuentes que dicen
      lo contrario y el amigo de la dueña lo logró así con otro cliente). Pide en Juan una segunda llave (`IG…`, se
      renueva cada 60 días) y la clave secreta de la app de Instagram. Si no alcanza, va en la misma revisión de la app.
      **En producción desde Juan 22, apagada:** falta que el jefe siga JUAN_CANALES §3b y pruebe con una cuenta SIN papel.
    - **Comentarios: en producción desde Desplegar 70 y Juan 24, apagados** (JUAN_CANALES §3c). Los avisos de
      comentarios piden acceso avanzado por las dos puertas (también por inicio de sesión de Instagram): hasta la
      revisión de la app solo llegan los de cuentas con papel. Falta: que el jefe marque `feed` (página) y `comments`
      (Instagram) en la app; que la dueña los encienda y pruebe con su cuenta; pedir `pages_manage_engagement`,
      `pages_read_engagement`, `pages_read_user_content` e `instagram_manage_comments` /
      `instagram_business_manage_comments` en la misma revisión que Messenger.
    - **Paquete para la revisión de Meta** (textos de cada permiso y guion del video): ofrecido a la dueña el
      2026-11-13; base en el borrador de permisos de la sesión y JUAN_CANALES paso 9.
    - **Alternativas investigadas el 2026-11-15** (OpenReply, MCPs de Instagram y otros repos; detalle en la bitácora de
      LEEME_PRIMERO): ninguna quita la revisión de Meta. La única pista es **Zernio**, un proveedor con su propia app de
      Meta (sin verificar para Instagram y Messenger; los mensajes pasarían por un tercero). Espera la decisión de los
      jefes; la prueba barata es conectar una cuenta de Instagram sin papel a una cuenta gratis de Zernio.
0. **Envíos de Juan, reparto justo de chats y Costos de IA con «Pagar»** (2026-11-12): ver la bitácora. (Los colchones
   ya están publicados, 2026-11-13.) Falta de la dueña: revisar en Envíos › Lugares (filtro «Por revisar (Gerencia)») los lugares agregados a mano, para que Juan
   dé su precio; archivar la nota de la promoción de noviembre en el Conocimiento el 1 de diciembre; preguntar a la
   contadora si el envío lleva ITBMS.

000. **Panel renovado (2026-11-11): todo lo aprobado está en producción (Desplegar 64, 65, 66 y 67, este último el
     modo oscuro).** Detalle y citas de la dueña en la bitácora de LEEME_PRIMERO
     (entradas del 2026-11-11 (2) y (3)). Informe de la auditoría: <https://claude.ai/artifact/QN3GPdAtm7nKxQtu9X64MP>.
     - **En producción:** Desplegar 64 (PR #109: 21 arreglos de la auditoría) y **Desplegar 65** (PR #110: el Inicio
       nuevo con accesos del celular en tres tamaños; el Inicio ya no queda en blanco al entrar; el menú del celular
       es una sola lista; «atrás» dentro del chat vuelve a la lista; la caja de responder del celular de 215 a 111 px;
       la lista de chats entera en tableta). **Falta que la dueña lo pruebe en su iPhone** y diga si el blanco
       desapareció del todo.
     - **También en producción, Desplegar 66 (PR #111):** «Entregas pendientes» del Inicio igual que «Bodega» (con el
       renglón de las que esperan pago) y «Más datos» plegable en la cotización.
     - **Modo oscuro gris («estilo Cubase»), opcional por persona:** **en producción, Desplegar 67 (PR #112)**,
       aprobado por la dueña («Si me gusta, apruebo el modo oscuro para producción»). El claro no cambia. Preguntas abiertas para ella en la bitácora (interruptor en el menú del celular, por usuario o por
       navegador, seguir el modo del teléfono).
     - **Más adelante (van con el diseño nuevo o son de Odoo):** gráficas de Odoo en el azul de D'CASA; tablas
       dinámicas en el celular; listas estiradas en 1920 px; títulos de las pantallas propias en la barra del celular;
       la tarjeta «Instale Odoo» y OdooBot; «Manual Payment» (dato: se cambia en Ajustes); en tableta parada
       (768–991 px) el menú sigue siendo el de Odoo (íconos arriba) y el botón de Brian tapa «Enviar» del chat.
     - **Versión estable:** Desplegar 67 es más nuevo que la estable 4. Cuando lleve unos días sin dar guerra, nombrar
       la estable 5 (pedirle el «sí» a la dueña, como la vez pasada).
1. **Camila (mail marketing)** ([CAMILA.md](CAMILA.md)): etapas 1 y 2 **en producción** desde el 2026-11-06 (Desplegar
   52 y 54, con Juan 7). La clave de campañas ya está y Odoo la tomó (Desplegar 53). Nada sale sin que alguien de
   Marketing o Gerencia apruebe la campaña. Falta de la dueña: la primera campaña y confirmar el «Sí, quiero» de dos
   toques. **Etapa 1b** (la lista crece sola: se activa al agregar el correo y se quita con un «no», CAMILA.md §1c):
   **en producción** desde el 2026-11-07 (Desplegar 58 y Juan 9, con dos revisiones adversariales). **«Abrieron» y
   «Tocaron» en 0** (2026-11-07, CAMILA.md §1d): el remitente propio de las campañas y el aviso de Resend están
   **en producción** desde el 2026-11-07 (PR #95, Desplegar 61). La dueña ya agregó y verificó `novedades.dcasapty.com`
   en Resend (registros puestos solos en Cloudflare) con aperturas y clics encendidos en `links`. Falta de la dueña:
   poner `hola@novedades.dcasapty.com` en «Remitente de las campañas» y probar «Enviarme una prueba» (CAMILA.md §6b). Después: cumpleaños, «tu cotización sigue aquí» y la etapa de la página web.
2. **Brian al día** y la **pantalla nueva de Sofía**: **en producción** desde el 2026-11-06 (Desplegar 57; capturas
   aprobadas por la dueña; Brian con revisión adversarial). Sigue para Brian: los topes de dinero (punto 5).
3. **Que el equipo use lo nuevo** (lo hace la dueña con el equipo; ver «Lo que falta de la dueña»): el Reparto
   «Parejo», el Telegram de cada vendedora, «Revisar ahora» de Sofía y los mensajes de Sofía.
4. ~~**Respaldo de la IA de Juan** y plantillas de WhatsApp~~: la dueña (2026-11-07): «no es una prioridad, con que ya
   esté disponible es más que suficiente; ya eso está resuelto y está bien». Queda anotado por si cambia.
5. ~~**Brian: topes de dinero**~~ (issue #26): la dueña (2026-11-07): «ya pusimos los límites».
6. **Conversaciones: seguimiento por persona** (issue #25): lo que quedaba (aprobado por la dueña el 2026-11-07)
   está **en producción** desde el 2026-11-07 (PR #94, Desplegar 60), con la revisión adversarial arreglada; issue #25
   cerrado. Queda de la dueña: si 6 h de atraso máximo le parecen bien (es un ajuste en Ajustes de Juan).
7. **Contabilidad:** el menú raíz propio «Contabilidad» (reportes, bancos, cierre de mes, en un solo lugar). Las
   **facturas del sistema anterior** dejaron de ser una preocupación (la dueña, 2026-11-07: los jefes están bien con los
   números actuales); el importador queda listo por si algún día hace falta.
8. ~~**Messenger e Instagram**~~: conectados (9 y 10 nov, [JUAN_CANALES.md](JUAN_CANALES.md) §3).
9. ~~**Códigos de barras**~~: la dueña (2026-11-07): «ya solucionamos» (issues #9, #10 y #12, [BARRAS.md](BARRAS.md)).
10. **Envíos:** la calculadora (`dcasa_envios`, [ENVIOS.md](ENVIOS.md)) está **en producción** desde el 2026-11-06
    (Desplegar 50). Sigue: que Gerencia cargue el archivo en Envíos › Tarifa y **apruebe la tarifa** (redondeo,
    viático, honorarios y peaje); después, con su «sí», que Juan cotice y la sección de envíos del sitio (cuando haya
    flota propia).
11. **Siguiente etapa de Sofía:** mensajes con IA y plantillas de WhatsApp para después de 24 horas (sus herramientas
    de Brian, de lectura y «Revisar ahora», ya están en producción).
12. **Privacidad (issues #22 y #23):** borrar la oportunidad junto con la conversación y lo que «Eliminar conversación»
    todavía no borra.
13. **Juan: hallazgos** del issue #24: lo aprobado el 2026-11-07 (eco de Messenger e Instagram, nota de voz que pide una
    persona, transcripción después del anti-spam, reintento del turno, carrera del seguimiento y menores) está **en
    producción** desde el 2026-11-07 (Desplegar Juan 10), con la revisión adversarial arreglada. Quedan tres menores que
    no entraron en esa lista (ver el comentario del issue #24, que sigue abierto por ellos).
14. **CRM, fase 2** (issues #15 a #21): se eligen con la dueña.
15. **Cabos técnicos menores** (sin urgencia):
    - que el respaldo previo de staging despierte el sitio antes de pedir el volcado (el despliegue a staging del CI se
      frenó así tres veces; ver CONTEXTO_AGENTICO › Despliegue);
    - por qué Odoo de producción estaba apagado el 2026-10-23 a las 06:38 UTC si debe estar encendido siempre (sin
      confirmar: registros del contenedor de esa hora);
    - encender la portada guardada en el borde en producción (`tienda` sale «falta»: `TIENDA_FEED_TOKEN` y
      `TIENDA_ESTATICA`, [OPERACION.md](OPERACION.md) › Tienda rápida);
    - velocidad: `/web/image` lee el archivo de R2 antes de contestar «no cambió», el ZIP de comprobantes ocupa la CPU
      mientras se arma (pedirlo fuera de horario) y el costo de lo vendido hoy se busca producto por producto;
    - pruebas de humo a mano después de cada despliegue a producción y una revisión de secretos;
    - una pantalla propia abierta desde antes de un despliegue sigue con el JavaScript viejo y puede romperse con los
      datos nuevos (2026-11-06: Camila en el celular de la dueña, «ctx['d'].proxima.ya», tras Desplegar 54; se arregla
      recargando). Que las pantallas propias avisen «Hay una versión nueva: toca para recargar» cuando cambie
      `APP_VERSION`;
    - ~~los PR de Dependabot abiertos (#7, #78 a #81)~~: aplicados y en producción (PR #88, Desplegar 56 y Juan 8,
      2026-11-06); los PR de Dependabot se cierran solos al ver `main` al día;
    - `abrir` de Bodega no exige pago a una entrega en borrador (hoy no hay entregas de venta en borrador);
    - «Rastrear inventario»: la prueba de la Vendedora con el mensaje exacto y el motivo en el historial del movimiento;
    - «Cobrado» suma `amount` y todo cobro entrante (igual que la Caja de hoy); no hay prueba con costo FIFO;
    - Brian sin huecos: descuentos, facturar desde una cotización, margen por producto, recibir compras (fusionar
      contactos: ya los lista con `clientes_repetidos`; fusionar sigue en la pantalla, a propósito).

**Nombres reservados** (2026-11-06, el jefe): **Daniela, Alejandra y Andrés** quedan para futuras herramientas; se
asignan con la dueña cuando toque (Camila ya es la del mail marketing y la web).

**Sin fecha:** la **puerta del equipo `/master` en producción** (issue #27) queda pendiente, sin fecha: la dueña decide
cuándo, cuando el equipo se haya adaptado ([PUERTA_MASTER.md](PUERTA_MASTER.md)).

## Lo que falta de la dueña

Lo que no es programación. Absorbe lo que seguía vigente de la lista vieja
([historico/PENDIENTES_DUENA.md](historico/PENDIENTES_DUENA.md)).

### Para usar lo que ya está

- **Reparto «Parejo»** (Conversaciones › Reparto, Gerencia): mientras esté apagado, Juan no asigna clientes, y la regla
  de «solo vendedoras activas» y «pasar a otra si no contesta» no corre ([JUAN_ODOO.md](JUAN_ODOO.md) › Reparto).
- **El Telegram de cada vendedora** (para los «Te tocó a ti» y el resumen de Sofía).
- **Sofía:** que Gerencia ajuste los mensajes (CRM › Configuración › Sofía) y que las vendedoras toquen «Revisar ahora»
  y guarden los datos de quienes ya contestaron.
- **Valor del inventario:** cargar el costo de los productos que salen «sin costo» y contar los que salen en negativo.
- **Quien cobra tiene el rol Caja** (Ajustes › Usuarios; sin Caja solo Gerencia cobra). Confirmar que ya se hizo.
- **Bodega y compras:** el rol Marketing a quien corresponda, el tiempo de llegada de cada proveedor (en su precio de
  proveedor) y, si se quieren, las alertas de bodega con sus umbrales ([EXISTENCIAS.md](EXISTENCIAS.md)).
- **QR y código público** en la factura y la cotización (vienen apagados: Ajustes › Empresas › Documentos D'CASA;
  aprobar antes las imágenes) y el **QR de la nota de entrega** (lo lee el panel de Bodega; encenderlo si todavía no).
- **Camila** (cuando entre): crear en Resend la clave de campañas con permiso «Full access» y pegarla como secreto
  `RESEND_CAMPANAS_API_KEY` en el panel de Cloudflare del Worker `dcasa` (paso a paso en [CAMILA.md](CAMILA.md) §6;
  nunca en el chat), revisar la política de privacidad (novedades por correo y Resend) y pedirle a las vendedoras que
  marquen la casilla «Novedades por correo» cuando el cliente diga que sí.
- **Camila, para que «Abrieron» y «Tocaron» cuenten** (cuando entre el remitente propio): en Resend, el subdominio
  `novedades.dcasapty.com` verificado (DNS en Cloudflare con la nube gris) y con **Enable tracking metrics** (subdominio
  `links`, aperturas y clics); después, en Marketing › Camila, el «Remitente de las campañas» con un correo de ese
  subdominio. **No** encenderlo en `dcasapty.com` (las facturas). Paso a paso en [CAMILA.md](CAMILA.md) §6b.
- **Guía:** confirmar las listas «En tu puesto lo que más se usa» (`addons/dcasa_guia/data/guia_roles.json`).

### Decisiones

- Las **cifras** de los topes de Brian (puntos por ajuste, monto de una factura, unidades por ajuste) y del tope mensual
  de gasto de IA.
- **Tarifas de envío** (Gerencia): cargar el archivo en Envíos › Tarifa y aprobar la tarifa.
- **Anuncios en Meta** (catálogo, píxel y ventas reportadas): todo apagado hasta que diga; las decisiones están en
  [META_CATALOGO.md](META_CATALOGO.md) y [META_EVENTOS.md](META_EVENTOS.md) («Decisiones de la dueña»).
- **Segundo factor para todos y apagar la cuenta genérica `admin`** (pregunta I4 de la gerencia, sin respuesta).
- **`app.dcasapty.com`** (el sistema anterior) sigue vivo hasta que la dueña diga.
- **El repositorio es público** desde el 2026-10-13: volverlo privado al terminar el lanzamiento, o borrar del historial
  de Git la factura de un cliente que se quitó ese día. Y no subir a `up media/` nada con datos de personas.
- **Limpieza que necesita su visto bueno:** las ramas `respaldo/…` y `claude/bold-volta-fsqq4c` (copias de trabajos que
  ya están en `main`; `claude/bold-volta-fsqq4c` se borra en GitHub › Branches, porque desde la sesión no se puede).
- **Buscar en el conocimiento por significado** (opcional, apagado): probarlo en staging antes de encenderlo
  ([JUAN_ODOO.md](JUAN_ODOO.md) › El asistente aprende).
- **Datos del inventario anterior** (lista del 2026-10-12): 23 precios que cambia el inventario, el código XXI070507
  repetido, las bases N-F10018 King y Twin como productos aparte y 11 lecturas dudosas
  ([inventario-anterior-informe.md](inventario-anterior-informe.md)).
- **Con el abogado:** los textos de la factura (garantía, cambios, términos; se editan en Ajustes › Empresas ›
  Documentos D'CASA), la ficha «Apartados» del conocimiento de Juan (inactiva hasta su revisión) y el canje de negocios
  externos del programa de vendedores (apagado, `CLAUDE.md`).

### Trámites

- **Factura electrónica de la DGI:** elegir el PAC ([FACTURA_ELECTRONICA.md](FACTURA_ELECTRONICA.md)).
- **Etiquetas de códigos de barras:** pedir el rollo numerado y ensayar los dos lectores ([BARRAS.md](BARRAS.md)).
- **Dominio nuevo:** Google Search Console, Meta y lo impreso (pasos 13 a 15 de
  [historico/TRASLADO_DOMINIO.md](historico/TRASLADO_DOMINIO.md)). Los QR impresos de Socios apuntan a
  `https://dcasapty.com/socios`.
- **Messenger e Instagram:** los pasos en Meta ([JUAN_CANALES.md](JUAN_CANALES.md)); Meta puede pedir la verificación
  del negocio, que tarda días.
- **Nómina:** lo que valida el contador (tasas, riesgo profesional, décimo, cuentas) y las fichas de los colaboradores
  (salario, fecha de ingreso, cédula, seguro social, cuenta) antes de correr la primera planilla en Odoo
  ([NOMINA.md](NOMINA.md)).
- **Equipo:** la jerarquía (departamentos con su gerente) y el rol de cada quien ([EQUIPO.md](EQUIPO.md)); viene de la
  lista del 2026-10-12, confirmar si ya se hizo.
- **Contactos repetidos viejos:** fusionarlos en Socios › Configuración › Posibles duplicados ([CONTACTOS.md](CONTACTOS.md)).

### Para la contadora (y la gerencia)

Preguntas abiertas de la auditoría de los reportes (copiadas de
[historico/AUDITORIA_CONTABLE.md](historico/AUDITORIA_CONTABLE.md), donde está el detalle de cada una) y de las
revisiones de octubre. Lo que la gerencia ya respondió está en [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md).

- **Las facturas del sistema anterior:** la equivalencia de cuentas y el ensayo de la carga en staging con los archivos
  reales ([MIGRACION.md](MIGRACION.md)).
- **Diarios y formas de cobro:** las cuentas de Visa, Mastercard, American Express, Clave y KrediYa (111.011 a 111.015),
  la forma de pago DGI de KrediYa y Crediviva, las cuentas de Tafi y Crediviva y cómo se cruza lo que deposita la
  financiera, y las comisiones de cada método (Bancos › Reglas de conciliación).
- **Lo que se vio en octubre:** costo de ventas en cero (falta cargar costos, C8), ACH de Banco Nacional en negativo,
  saldos de Punto de venta y Yappy sin traspasar al banco, ITBMS acumulado.
- **C1** activo fijo e intangibles como «corriente»; **C2** anticipos de clientes (la cuenta 2120000 es «por pagar»; la
  gerencia dejó la decisión a la contadora, I5); **C3** préstamos de corto o largo plazo y su actividad en el flujo.
- **C4** cómo se lleva el saldo a favor de ITBMS de un mes a otro; **C5, C20 y C21** el efectivo (¿un movimiento de caja
  por cobro o el saldo directo?) y si lo que está en tránsito suma al dinero en bancos.
- **C7** cómo se hará el cierre anual; **C17 y C18** el presupuesto (la gerencia quiere arrancar 2027 con presupuesto).
- **C9 a C16** (monedas, ITBMS y dinero entre empresas, mapa de cuentas): solo hacen falta cuando haya otra empresa o
  moneda (hoy no hay, K3).
- **Para la gerencia:** si Caja puede seguir quitando un cobro mal aplicado de una factura (hoy sí) y si el contador
  sin Gerencia debe poder anular o hacer notas de crédito (hoy no).

## Issues abiertos (revisados el 2026-11-06: 16)

| Issues | Qué son | Dónde va en la lista |
|---|---|---|
| ~~#9, #10, #12~~ | Lectores y etiquetas de códigos de barras: **cerrados el 2026-11-11** (resueltos, según la dueña) | 8 |
| #15 a #21 | CRM, fase 2: seguimiento de cotizaciones sin respuesta (#16), invitar a la tienda (#17), posventa (#18), Brian y oportunidades (#19), perder oportunidades (#20), cotizaciones fuera de la conversación (#21) | 13 |
| #22, #23 | Privacidad (Ley 81): zona de entrega y borrar la oportunidad con la conversación; lo que «Eliminar conversación» todavía no borra | 11 |
| #24 | Juan: hallazgos que quedaron para después | 12 |
| #25 | Conversaciones: permisos de escritura y seguimiento por persona | 5 |
| ~~#26~~ | Brian: topes de gasto, de archivos y de dinero: **cerrado el 2026-11-11** (límites puestos) | 4 |
| #27 | Puerta del equipo `/master` | Sin fecha |
