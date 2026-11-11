# Prioridades vigentes

Puesto al día el **2026-11-11** (cierre de semana y auditoría visual del panel). Es el orden en que se trabaja: cada sesión lo lee al empezar y lo pone al día al
terminar (ver [LEEME_PRIMERO.md](LEEME_PRIMERO.md)). Aquí va **un solo estado**, el de hoy; lo que pasó cada día está en
la bitácora de LEEME_PRIMERO (y lo más viejo en [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md)).

Cada cosa nueva pasa por capturas a la dueña, su visto bueno, pruebas y staging; a producción, con su «sí» (reglas en
LEEME_PRIMERO §2).

## Estado al 2026-11-11

- **Producción funciona desde el 2026-10-13** y **`dcasapty.com` (y `www`) apunta al sistema nuevo desde el
  2026-10-27** (Desplegar 31). Odoo y el borde: **Desplegar 63** (9 nov, PR #100: enlace para choferes, «Colchones» abre
  WhatsApp y Dependabot). Juan: **Desplegar Juan 20** (11 nov, PR #107). Esa combinación es la **versión estable 4**
  ([VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md)). El contenedor instala 30 de los 31 módulos de `addons/` (todos
  menos `dcasa_fe_pa`, a propósito).
- **Juan atiende WhatsApp (API oficial de Meta), Messenger e Instagram**, con fotos en los tres, y Telegram. WhatsApp
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

000. **Auditoría visual del panel (2026-11-11), a medio camino.** Informe y capturas:
     <https://claude.ai/artifact/QN3GPdAtm7nKxQtu9X64MP>; detalle en la bitácora de LEEME_PRIMERO.
     - **En la rama, sin desplegar** (desde `5dfe55c`): fechas completas en las listas, Brian ya no tapa el Total,
       aviso de lista vacía correcto, listas legibles en el celular, cabecera de formularios en un renglón, Compras y
       contacto en el celular, botones de 44 px en la barra de arriba del celular, pestañas de Contabilidad que bajan
       de renglón en la computadora. **Falta:** el visto bueno de la dueña sobre las capturas → CI con staging →
       PR → Desplegar (cambia Odoo: con `respaldo_previo`).
     - **Tres respuestas de la dueña:** (1) el Inicio nuevo con movimiento
       (<https://claude.ai/artifact/VUKX4zkP16JQ5HVcDwjm6G>): ¿le gusta?, ¿«Claro» o «Azul noche»?; (2) cotización:
       ¿guardar los datos de pocas veces en «Más datos» para que los productos queden arriba?; (3) Sitio web › Páginas
       da «Acceso denegado» a Gerencia: ¿quitarlo de su menú? (toca permisos: con revisión).
     - **Lote 3, por hacer** (ninguno cambia funciones): Conversaciones en tableta nace con la lista reducida a
       iniciales (es a propósito hasta 1100 px, `preferencias.js`: proponer que abra entera mientras no haya un chat
       elegido); en el celular las pestañas de Contabilidad se cortan sin aviso de que hay más; pantallas propias sin
       título en la barra de arriba del celular; «Ingreso esperado $ 0.00 en» queda colgando en la oportunidad en el
       celular; letra de 10,9 px en la franja de Envíos y en «Ctrl K».
     - **Boceto pendiente:** la caja de responder del chat en el celular ocupa un tercio de la pantalla (214 de
       664 px); los botones de 44 px están a propósito para el dedo, así que primero un boceto para la dueña.
     - **Más adelante:** gráficas de Odoo en el azul de D'CASA; tablas dinámicas en el celular; listas estiradas y
       pantallas propias pegadas a la izquierda en 1920 px; el tablero de Compras en el celular (cinco cifras
       apretadas).
00. **La semana que viene, propuesta en este orden** (se confirma con la dueña):
    1. **El aviso «Quedó por enviar» con el motivo real** (hoy dice «el Worker no respondió» para cualquier fallo) y un
       **aviso a Gerencia por Telegram cuando un canal de Meta deja de enviar o recibir**: el 131070 no está entre los
       códigos que avisan (`CODIGOS_DE_CUENTA` en `dcasa_conversaciones/models/mensaje.py`) y el 9 nov nadie se enteró
       a tiempo.
    2. **Dependabot #98** (Juan: `ai` 7.0.164 y `@ai-sdk/*`, parches): con pruebas y Desplegar Juan, un día con alguien
       mirando.
    3. **Privacidad (issues #22 y #23)**, por la Ley 81.
    4. **CRM fase 2:** #21 (cotizaciones hechas fuera del chat ligadas a la oportunidad) y #20 (perdida cuando el
       cliente compró en otro lado) primero.
    5. **Meta (lo hace la dueña):** pedir un nombre visible nuevo de WhatsApp («DCasa Pty» DECLINED; p. ej. «D'Casa
       Panamá»), la verificación del negocio y la revisión de la app (Business Asset User Profile Access y acceso
       avanzado de Messenger e Instagram).
    6. Si la dueña lo pide: respuestas automáticas a comentarios de Instagram (`instagram_manage_comments`).
    La IA de respaldo de Juan (`ANTHROPIC_API_KEY`, `/salud` la da como faltante) y las plantillas de WhatsApp siguen
    como decidió la dueña el 2026-11-07 (punto 4): no son prioridad.
0. **Citas, reenviados, reacciones y palomitas en el chat** (pedido de la dueña del 2026-11-07, bitácora de
   LEEME_PRIMERO): **en producción** desde el 2026-11-07 (PR #94, Desplegar 60 y Juan 10), con la revisión adversarial
   arreglada; la dueña vio las capturas («perfecto, llévalo a producción»). Falta, si se quieren las reacciones de
   Telegram: volver a registrar el webhook con `allowed_updates` ([JUAN_CANALES.md](JUAN_CANALES.md) §2).
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
