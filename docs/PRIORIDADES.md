# Prioridades vigentes

Puesto al día el **2026-11-14** (avisos de Telegram ordenados, lote 1 de la web, «Busca con una foto», horario de la tienda; Brian de la tienda y lote 2 de la web en camino). Es el orden en que se trabaja: cada sesión lo lee al empezar y lo pone al día al
terminar (ver [LEEME_PRIMERO.md](LEEME_PRIMERO.md)). Aquí va **un solo estado**, el de hoy; lo que pasó cada día está en
la bitácora de LEEME_PRIMERO (y lo más viejo en [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md)).

Cada cosa nueva pasa por capturas a la dueña, pruebas, staging y, si toca dinero, permisos o Socios, revisión adversarial.
**Desde el 2026-11-13 la dueña no pide su visto bueno para pasar a producción** («Y no esperes mi aprobación para pasar
la producción. Apruébalo y punto.»); la revisión adversarial no se salta (reglas en LEEME_PRIMERO §2).

## Estado al 2026-11-14

- **Producción funciona desde el 2026-10-13** y **`dcasapty.com` (y `www`) apunta al sistema nuevo desde el
  2026-10-27** (Desplegar 31). Odoo y el borde: **Desplegar 71** (14 nov, PR #117: avisos de Telegram ordenados con la noche sin clientes, lote 1 de
  la web, «Busca con una foto», el robot como ícono de Brian y el horario de la tienda; antes, Desplegar 70, PR #116:
  comentarios de Instagram y Facebook, apagados; antes, Desplegar 69, PR #115: Juan ya no dice «no lo manejamos» de lo que no está publicado; antes, Desplegar 68, PR #113: Juan cotiza envíos con la promoción, reparto justo y Costos de IA con «Pagar»; antes, Desplegar 67, PR #112: el modo oscuro; el 11 nov, Desplegar 66 con
  entregas igual que Bodega y «Más datos», y antes, Desplegar 65 con el Inicio nuevo, el celular al entrar y la caja del chat, y Desplegar 64 con
  los 21 arreglos de la auditoría visual). Juan: **Desplegar
  Juan 25** (14 nov, PR #117: `sin_leer` con su motivo, el comprobante solo si es un pago hecho y la foto de la tienda;
  Juan 24, 13 nov, PR #116; Juan 23 trajo «no lo manejamos» y Juan 22 la segunda puerta de Instagram, apagada). La **versión estable 4** es la anterior (Desplegar 63 + Juan 20)
  ([VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md)). El contenedor instala 31 de los 32 módulos de `addons/` (todos
  menos `dcasa_fe_pa`, a propósito); con Brian de la tienda serán 32 de 33.
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

0000. **Brian de la tienda y lote 2 de la web, a producción el 2026-11-14 sin hora programada** (la dueña: «vamos a
      subirlo lo antes posible»). Módulo nuevo `dcasa_brian_tienda` (chat de ventas en la web con el motor de Juan,
      ver [BRIAN_TIENDA.md](BRIAN_TIENDA.md)) y, del lote 2, el horario en Visítanos y el pie (sale de Ajustes de
      Juan), el mapa de Google con permiso de cookies y las opiniones de productos aprobadas por Gerencia. Orden:
      **Juan antes que Odoo** (el Durable Object `TiendaSesion` es la migración v2 del Worker). Después:
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
