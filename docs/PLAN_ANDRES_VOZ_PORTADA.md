# Plan: Andrés vendedor, notas de voz y la portada nueva

Escrito el 2026-11-16 para que otra sesión lo continúe. Antes de empezar, leer `CLAUDE.md`, `docs/LEEME_PRIMERO.md`
(cómo se trabaja con la dueña, autorizaciones, receta de producción y bitácora) y `docs/PRIORIDADES.md`.

## Estado al dejar este plan

- **En producción:** paleta con bandas en azul noche y pie claro, menú sin «Escríbenos», sección de contacto, el
  número de /visitanos a WhatsApp y el carrito en la barra del chat de la tienda (Desplegar 76, PR #122).
- **En la rama, listo y SIN subir (la sesión se pausó el 2026-11-16 por el límite de uso):** la **campaña del sitio**
  (Black Friday desde el panel, `website_dcasa/models/campana.py`, tres vueltas de revisión adversarial sin
  bloqueantes) y el **cambio de nombre del chat de la tienda a Andrés** (Odoo y el Worker `juan/src/tienda`, que
  necesita *Desplegar Juan*). Terminar eso es el **paso 0**, antes que todo lo demás: el Black Friday es el viernes
  27 de noviembre.
- **Pregunta abierta a la dueña (I6):** el precio de campaña hoy vale en todos lados (web, Juan por WhatsApp y las
  cotizaciones de la tienda física), porque la tienda en línea y las vendedoras usan la misma tarifa («Default»).
  Si ella quiere «solo web», hay que darle al sitio su propia tarifa y revisar Juan (sus cotizaciones usan la del
  contacto). No cambiarlo sin su «sí».

## Reglas que no se negocian (resumen; el detalle está en CLAUDE.md y LEEME_PRIMERO)

- **Capturas antes de cualquier prueba o subida.** Computadora (1440) y celular (390), revisadas antes de mandarlas.
  La dueña aprueba; después pruebas locales, CI con staging, PR `[skip ci]`, *squash* con `expectedHeadSha` y
  *Desplegar* (más *Desplegar Juan* si cambió `juan/`).
- **Revisión adversarial independiente** cuando se toca dinero, permisos, datos personales o Socios. El bloque A
  (envío en la cotización, cambiar el carrito) y el B (audio de los clientes) la necesitan.
- **Andrés nunca suma ni inventa cifras**: los totales, el envío y los descuentos los calcula Odoo
  (`juan/src/tienda/prompt.ts`, regla «No sumes… el total lo calcula la tienda»). Eso se queda: lo que cambia es que
  Andrés **ofrece** sumar el envío y la página le pide a Odoo que lo agregue; el total lo dice el carrito.
- Marca: azul `#1340B1`, amarillo `#FED00F` (nunca toca el blanco), Anton/Oswald/Inter, plano, tuteo, sin «remate»
  ni «¡¡CORRE!!», sin datos inventados. CTA único: WhatsApp.
- Las pruebas de navegador **solo corren en local** (el CI no tiene `websocket-client`): correr
  `scripts/test.sh <módulos>` aquí con el venv de Python 3.12 (receta en CONTEXTO_AGENTICO).
- La máquina de la sesión se reinicia sin aviso (cuatro veces el 2026-11-15/16): PostgreSQL queda abajo
  (`pg_ctlcluster 16 main start`) y lo que no está en la rama se pierde. **Subir a la rama seguido.**

## 0. Terminar la subida de Black Friday y Andrés (lo primero)

El código está en `cae5e57`. El commit que devuelve el combo, del 2026-11-16, va encima; después solo hay commits de
documentos. Las capturas de la campaña ya las aprobó la
dueña (<https://claude.ai/artifact/GxqG2zGJZ949owo6Pbqwgn>), igual que el nombre «Andrés» y el botón «Empezar de cero».
Ya autorizó la subida: «lleva ya todo a producción». La revisión adversarial ya se hizo (tres vueltas).

1. **Antes de subir: «los combos son inamovibles».** Hay que programar esta regla primero, porque sin ella el Black
   Friday rompe lo que pidió la dueña. Sus palabras del 2026-11-16: «no quiero tocar en absoluto los combos. Los combos
   son inamovibles aunque hayan estrategias o ofertas… si aplican una promoción u oferta, no contempla los combos que
   tienen descuento. Aunque se pudiera… romper la regla, por ahora no quiero romperla. Pero debería poderse, pero no
   quiero».
   - **El problema hoy:** la vendedora arma en la cotización el combo cama + colchón
     (`dcasa_catalogo/models/combo_armable.py`, `_dcasa_recalcular_combos` y `_dcasa_emparejar`). La cama toma la
     tarifa, y con la campaña rigiendo eso es el precio de Black Friday. El colchón va a su «precio en combo».
   - **La regla:** en un combo armado, la cama y el colchón emparejados se calculan **sin las reglas de la campaña**
     (`product.pricelist.item.dcasa_campana`). Las demás reglas de la tarifa se mantienen. Al salir del combo, cada
     pieza vuelve a su precio con campaña. Cuando entra o sale del combo, la cama también se vuelve a calcular (hoy
     solo se recalcula el colchón: `_dcasa_reponer_precio` cuando cambia `dcasa_combo_con_precio`).
   - **Cómo, sugerido:** una bandera de contexto que saque las reglas `dcasa_campana` del dominio de reglas aplicables
     de la tarifa. Esa parte va en `website_dcasa/models/campana.py`; mirar `_get_applicable_rules_domain` en
     `vendor/odoo/addons/product/models/product_pricelist.py`. `dcasa_catalogo` la usa en las líneas del combo:
     `dcasa_catalogo` ya depende de `website_dcasa`.
   - **Hay que comprobar con una prueba** que el «precio en combo» del colchón no cambie cuando el colchón tiene precio
     de campaña.
   - **«Debería poderse»:** un interruptor en la campaña, «La campaña también rebaja los combos», **apagado** y que
     solo Gerencia puede cambiar. Lo apagado es lo que vale hoy.
   - **Ya está:** los combos tipo «Combo» de Odoo no admiten precio de campaña (`_check_dcasa_campana_precio`). La
     línea «Combo con colchón $X» sale siempre con su precio de siempre (`a18ff7f`).
   - **Revisión adversarial obligatoria**, porque toca dinero. Las capturas no hacen falta: no cambia ninguna pantalla,
     salvo la casilla del interruptor, que sí hay que mostrarle.
2. **Pruebas locales.** El 2026-11-16, con el código de `11f9822`, pasaron 827 de 827. Hay que repetirlas con el
   código final (los arreglos de `cae5e57` y el combo de vuelta):
   `TEST_TAGS="/website_dcasa,/dcasa_tienda_borde,/dcasa_brian_tienda,/dcasa_conversaciones:TestPrecioDeCampanaEnLaFicha,/dcasa_conversaciones:TestHerramientas,/dcasa_conversaciones:TestPanelCatalogo,/dcasa_conversaciones:TestPagosIa,/dcasa_socios,/dcasa_abonos,/dcasa_meta_catalogo"`
   con `scripts/test.sh` (el venv y Chrome, como en CONTEXTO_AGENTICO › Esta máquina). Correr también
   `cd juan && npm test && npm run typecheck` (1810 en verde el 2026-11-16) y `ruff check addons`.
3. **Desplegar Odoo.** Seguir la receta de LEEME_PRIMERO:
   1. Correr `ci.yml` en la rama con `desplegar_en=staging`.
   2. Sacar el digest del job «Desplegar a staging».
   3. Abrir el PR con «[skip ci]» en el título.
   4. Hacer el squash con `expectedHeadSha` igual al commit probado.
   5. Comprobar que el árbol de `origin/main` sea el mismo.
   6. Correr `desplegar.yml` en main: `production`, el digest, `app_version` igual a los 40 caracteres del commit
      probado y `respaldo_previo` en true.
   7. Cancelar el CI del PR.
   8. Correr `git merge -s ours origin/main`.
4. **Desplegar Juan** (`desplegar-juan.yml`: `production`, `dry_run` en false), porque cambió `juan/src/tienda`
   (Andrés).
5. **Verificar.**
   - `/dcasa/salud` responde sano con la versión nueva.
   - El chat de la tienda saluda «Hola, soy Andrés».
   - Sin campaña, /promociones da 404 y el menú no muestra «Promociones».
6. **Avisarle a la dueña en palabras sencillas, con estos pasos para el panel:**
   1. Entrar a Sitio web › Configuración › **Campaña del sitio**.
   2. Tocar **«Empezar de cero»**: las camas del Black Weekend siguen marcadas.
   3. Poner el nombre («Black Friday»), las fechas reales y, si quiere, una frase. Las horas son de Panamá: la campaña
      corre de las 00:00 del primer día a las 23:59 del último.
   4. En **«Elegir productos y precios»**, marcar «En la campaña» y escribir el precio de campaña **sin ITBMS** (es
      opcional: un producto marcado sin precio sale en la página con su precio normal).
   5. Para varios productos a la vez: seleccionarlos y usar Acción › **«Aplicar un descuento de campaña»** (%).
   6. «Promociones» aparece sola en el menú cuando empieza la campaña y se quita cuando termina.
7. **Preguntas abiertas para ella** (no cambiar nada sin su «sí»):
   - **I6.** ¿El precio de campaña vale también en la tienda física, o solo en la web? Hoy vale en todos lados.
   - **Combos, ya contestado (2026-11-16):** son inamovibles. Es el paso 1 de arriba.
   - **Ya decidido (2026-11-16):** «los combos son intocables. Esa es una promoción permanente de la empresa…
     supongo que es a cosas individuales y no a combos». La línea «Combo con colchón $X» sale siempre con su precio
     de siempre, también con precio de campaña, en la página y en lo que dicen Juan y Andrés. Los combos tipo «Combo»
     de Odoo ya no admiten precio de campaña.
7. Anotar en la bitácora, PRIORIDADES y CONTEXTO_AGENTICO.

## A. Andrés como buen vendedor (lo primero: es lo que más vende)

### Lo que vio la dueña (2026-11-16, con capturas del chat)

1. Andrés arma el carrito y da el botón de cotización, pero con la conversación el **carrito y el botón «se van para
   arriba»** y el cliente los pierde.
2. Calculó el envío a Montelimar y, cuando ella dijo «súmale eso a la cotización» y «dame la cotización», contestó
   «Yo no sumo totales…». Ella esperaba que **ofreciera** sumar el envío y le dejara la cotización completa.
3. En la vitrina grande quedaron **camas y colchones mezclados** (pidió primero camas y luego colchones): a una
   persona que no domina la tecnología, lo viejo y lo nuevo juntos le hace ruido.
4. Vació el carrito y **Andrés no reaccionó**. Quiere que, sin ser invasivo, diga algo como «vi que quitaste la cama,
   ¿buscamos una más económica o con más prestaciones?».
5. Quiere poder pedirle a Andrés **cambiar cantidades o quitar** un producto, y que Andrés ofrezca alternativas.
6. Le gustó la vitrina grande con «Lo más buscado» y la sincronización con el carrito: no romperlas.

### Propuesta (mostrar capturas antes de programar)

- **A1. El carrito siempre a mano.** Una barra fija en la columna del chat, encima del campo de texto: «4 artículos ·
  $649.96 + ITBMS · Ver / Cotización». Al tocarla se abre el carrito editable (± cantidad, quitar) sin salir del chat.
  Los números salen de `GET /dcasa/brian/v1/carrito` (Odoo). En el celular, la misma barra.
- **A2. Envío en la cotización.** Cuando Andrés calcula el envío (ya lo hace con la ubicación o el barrio), ofrece
  «¿Te lo sumo a la cotización?». Con el sí, la página pide a Odoo que ponga la línea de envío en el carrito (la
  misma que pone `dcasa_envios`, con su promoción) y el PDF de la cotización la trae. Andrés dice «Listo, te lo sumé:
  el total lo ves en tu carrito y en la cotización», nunca la cifra sumada por él.
- **A3. Reacción al quitar o vaciar.** La página ya ve los cambios del carrito (`vigilarCarritoDeLaPagina` en
  `brian_tienda.js`). Cuando baja la cantidad o se vacía, le avisa al Worker **una sola vez por sesión** (y solo con el
  chat abierto) y Andrés contesta una vez, amable, ofreciendo una alternativa. Nunca insiste.
- **A4. Cambiar el carrito conversando.** Igual que `proponer_carrito` (`juan/src/tienda/motor.ts`): una propuesta
  estructurada `proponer_cambio_carrito` {producto, cantidad; 0 = quitar} que **la página aplica en Odoo** con la
  sesión del visitante; Andrés confirma con la verdad de Odoo, como hoy con «agregar».
- **A5. Vitrina ordenada.** Arriba «En tu carrito»; después un grupo por lo que se pidió, el más reciente primero
  («Colchones», «Camas»), con su título y plegable. «Lo más buscado» sigue cuando todavía no hay nada.

### Dónde está cada cosa

- Página del chat: `addons/dcasa_brian_tienda/static/src/js/brian_tienda.js` (clase `ChatBrian`: `pintarCabCarrito`,
  `ponerCarrito`, `pintarVitrina`, `vigilarCarritoDeLaPagina`, `refrescarCarrito`), estilos en
  `static/src/scss/brian_tienda.scss`. Rutas de Odoo en `controllers/main.py` (`/dcasa/brian/v1/...`: pase, carrito,
  cantidad, vitrina, `carrito/cotizacion.pdf`). Contrato en `docs/BRIAN_TIENDA.md`.
- Motor (Worker): `juan/src/tienda/` (`motor.ts` con las propuestas y opciones, `prompt.ts`, `bloques.ts`). Pruebas
  con vitest en `juan/test/tienda/`. Necesita *Desplegar Juan*.
- Envío: `addons/dcasa_envios/models/` (`venta.py`: la línea de envío del sistema y la promoción, `tarifa.py`,
  `promocion.py`).
- Pruebas de navegador del chat: `addons/dcasa_brian_tienda/tests/test_navegador.py` (con
  `tests/worker_simulado.py` para capturas locales: puerto 8788, tokens de 40 caracteres, `JUAN_URL`,
  `JUAN_WORKER_TOKEN`, `JUAN_ODOO_TOKEN`).

## B. Notas de voz para Andrés y para Brian del panel

- **Pedido:** «es muy fácil enviar notas de voz… el bot puede sugerirle si quieres envíame notas de voz»; y para
  Brian del panel, darle indicaciones por voz. **Con protección para que nadie use la herramienta para clonar voces.**
- **Lo que ya existe:** Juan transcribe notas de voz de WhatsApp con Whisper de Workers AI
  (`juan/src/motor/transcribir.ts`; se enciende con `TRANSCRIBIR_AUDIO=1` y el binding `ai`). El audio no sale de la
  cuenta de Cloudflare de D'CASA.
- **Propuesta:**
  - Botón de micrófono en el chat de la tienda (y en el panel de Brian). El navegador graba (MediaRecorder), muestra
    el tiempo, y manda el audio al Worker con el pase; el Worker lo transcribe y lo usa como si el cliente lo hubiera
    escrito. El cliente ve el texto transcrito en su globo.
  - **Nunca se guarda el audio** (ni en R2, ni en registros, ni en la conversación), no se devuelve, no se reenvía a
    nadie y no se usa para generar voz. Solo queda el texto, igual que un mensaje escrito. Límite de duración (por
    ejemplo 60 s) y de tamaño, y cupos por visitante y por conexión como los mensajes.
  - Actualizar `/privacidad` (párrafo del chat de la tienda, `FECHA_PRIVACIDAD` en
    `dcasa_brian_tienda/controllers/main.py`) y la Guía.
  - Brian del panel (`addons/dcasa_brian`): el mismo botón en su panel; la transcripción por el Worker con el token
    de Odoo (Odoo no transcribe). Revisar permisos: solo usuarios internos.
- Revisión adversarial obligatoria (privacidad, abuso, costos de IA).

## C. La portada

- **Hero:** hoy muestra una recámara y una sala que no son productos de D'CASA. Cambiar a fotos propias que se vean
  muy bien, en **carrusel** («algo dinámico, interactivo, que cambie»). La dueña nombró «la cama 805, la 801 y la
  cama negra 300-300»: **preguntarle cuáles son con las fotos a la vista**. Candidatas en el catálogo: `Y0300300`
  (cama queen negra, cabecero con alas en chevron), `8010-1001-K` (king rosada), `8017-1003-K` (king crema) y
  `8017-1002-Q` (queen beige).
- **Sección «de cine»:** una sección grande a media página con un carrusel lateral animado como el de
  `https://panaclaw.com/proyectos/` (camas, colchones, salas, mesitas en movimiento) y un botón al catálogo. El dominio
  no resolvió desde la sesión del 2026-11-16: agregar el repositorio `abrinay1997-stack/PanaClaw` con `add_repo`
  (lectura) para estudiar la animación, o pedirle a la dueña que habilite el dominio en la red del entorno.
- Respetar `prefers-reduced-motion`, la foto del hero como LCP (precarga), la marca plana y el contrato visual: un
  cambio del hero obliga a regenerar las referencias (`scripts/actualizar_referencias_visuales.sh`) en el mismo commit.
- Plantillas: `addons/website_dcasa/views/homepage_templates.xml` (hero en `oe_structure_dcasa_hero`; la portada puede
  estar guardada por el editor, así que las secciones nuevas van en plantillas con `t-call`), estilos en
  `static/src/scss/dcasa.scss`, interacciones como `static/src/js/carril.js`.

## Pendientes menores que quedaron de la campaña

- Revisión adversarial, tercera vuelta, no bloqueantes: **I-B** (una cotización abierta de la campaña sirve para
  líneas nuevas hasta 30 días después del fin; arreglo: calcular con la fecha de creación de la línea en pedidos que
  no son de la web) y los textos «Ver todo el …» / «me interesa del …» con nombres en femenino.
- `dcasa_conversaciones/tests/test_panel_visual.py`: las referencias `panel-lista-390` y `panel-conexiones-390` fallan
  en local (vienen de un PR viejo, no de esta ronda): regenerarlas con su script tras mirarlas.
- La Guía (`dcasa_guia`) falla en local si no se instalan todos los módulos (la tarea «planilla» es de nómina): no es
  una falla real, en el CI pasa.
