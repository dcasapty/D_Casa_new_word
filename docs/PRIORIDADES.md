# Prioridades vigentes

Puesto al día el **2026-11-06**. Es el orden en que se trabaja: cada sesión lo lee al empezar y lo pone al día al
terminar (ver [LEEME_PRIMERO.md](LEEME_PRIMERO.md)). Aquí va **un solo estado**, el de hoy; lo que pasó cada día está en
la bitácora de LEEME_PRIMERO (y lo más viejo en [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md)).

Cada cosa nueva pasa por capturas a la dueña, su visto bueno, pruebas y staging; a producción, con su «sí» (reglas en
LEEME_PRIMERO §2).

## Estado al 2026-11-06

- **Producción funciona desde el 2026-10-13** y **`dcasapty.com` (y `www`) apunta al sistema nuevo desde el
  2026-10-27** (Desplegar 31). El último despliegue es Desplegar 54 con Desplegar Juan 7 (6 nov, PR #87: Camila etapa 2). El mismo
  día: Camila etapa 1 (PR #85), la varita (PR #84), envíos (PR #83) y WhatsApp (PR #82).
  El contenedor instala 30 de los 31 módulos de `addons/` (todos menos `dcasa_fe_pa`, a propósito).
- **Juan atiende el WhatsApp de la tienda por la API oficial de Meta** desde el 2026-11-02 (modelo «contributor» de
  Meta, llave permanente). Telegram también funciona. Messenger e Instagram tienen el código listo pero no están
  conectados. El puente de WhatsApp por QR (`puente-wa/`) **nunca se desplegó** a producción. Ver
  [JUAN_CANALES.md](JUAN_CANALES.md).
- **Sofía, la asistente del CRM**, está en producción desde el 2026-11-05 ([SOFIA.md](SOFIA.md)).
- **El correo a clientes (Resend) está encendido** desde el 2026-10-27 ([CORREO.md](CORREO.md)).
- Lo último que entró (noviembre): Valor del inventario y cobrado por forma de pago; medios, Origen y cotizaciones que
  vencen solas en Conversaciones; tres paneles en el Inicio; reparto solo a vendedoras activas; clientes repetidos
  («Es esta persona»); tasa de cierre en el Resumen de Juan; Sofía. Detalle en la bitácora.

## Lo que sigue, en orden

1. **Camila (mail marketing)** ([CAMILA.md](CAMILA.md)): etapas 1 y 2 **en producción** desde el 2026-11-06 (Desplegar
   52 y 54, con Juan 7). La clave de campañas ya está y Odoo la tomó (Desplegar 53). Nada sale sin que alguien de
   Marketing o Gerencia apruebe la campaña. Falta de la dueña: la primera campaña y confirmar el «Sí, quiero» de dos
   toques. Sigue: etapa 1b (que Juan pregunte el permiso por WhatsApp), cumpleaños, «tu cotización sigue aquí» y la
   etapa de la página web.
2. **Brian al día** con lo nuevo (la dueña: «indispensable, pero desactualizado»). La vuelta a la **pantalla de Sofía**
   está hecha en su rama (2026-11-06 (7), solo interfaz): falta que la dueña vea las capturas antes/después y diga que
   sí, y después CI, staging y producción.
3. **Que el equipo use lo nuevo** (lo hace la dueña con el equipo; ver «Lo que falta de la dueña»): el Reparto
   «Parejo», el Telegram de cada vendedora, «Revisar ahora» de Sofía y los mensajes de Sofía.
4. **Respaldo de la IA de Juan:** `ANTHROPIC_API_KEY` en el Worker `dcasa-juan` por si Meta pasa su límite o se cae (hoy
   el cliente recibiría «una vendedora te atiende» y la varita dice «La IA no está disponible… la IA de respaldo no
   tiene clave»), una alerta de gasto en Meta y **plantillas de WhatsApp** aprobadas por
   Meta para escribir después de 24 horas (también para los seguimientos de Juan, que hoy no salen fuera de esa ventana).
5. **Brian: topes de dinero** (issue #26: `ajustar_puntos`, `crear_factura`, `ajustar_existencias` sin tope) y la cifra
   del tope mensual de gasto de IA (hoy en 0 = sin tope). Esperan las cifras de la dueña.
6. **Conversaciones: permisos de escritura y seguimiento por persona** (issue #25).
7. **Contabilidad:** el menú raíz propio «Contabilidad» (reportes, bancos, cierre de mes, en un solo lugar) y las
   **facturas del sistema anterior** (el importador está listo; espera a la contadora: ver abajo).
8. **Messenger e Instagram:** conectarlos con la guía de [JUAN_CANALES.md](JUAN_CANALES.md).
9. **Códigos de barras:** etiquetas del proveedor y prueba de los lectores (issues #9, #10 y #12); con eso, verificar el
   despacho con el escáner ([BARRAS.md](BARRAS.md)).
10. **Envíos:** la calculadora (`dcasa_envios`, [ENVIOS.md](ENVIOS.md)) está **en producción** desde el 2026-11-06
    (Desplegar 50). Sigue: que Gerencia cargue el archivo en Envíos › Tarifa y **apruebe la tarifa** (redondeo,
    viático, honorarios y peaje); después, con su «sí», que Juan cotice y la sección de envíos del sitio (cuando haya
    flota propia).
11. **Siguiente etapa de Sofía:** mensajes con IA, plantillas de WhatsApp para después de 24 horas y su herramienta de
    Brian.
12. **Privacidad (issues #22 y #23):** borrar la oportunidad junto con la conversación y lo que «Eliminar conversación»
    todavía no borra.
13. **Juan: hallazgos menores** que quedaron para después (issue #24).
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
    - en Conversaciones (computadora), el botón flotante de Brian tapa en parte el botón «Enviar» de la caja (se vio
      en las capturas de la varita del 2026-11-06);
    - los PR de Dependabot abiertos (#7 del borde; #78 a #81 de Juan y del puente, abiertos el 2026-11-06): revisarlos
      y probarlos antes de unir (el grupo «ia» de Juan toca los clientes de la IA);
    - `abrir` de Bodega no exige pago a una entrega en borrador (hoy no hay entregas de venta en borrador);
    - «Rastrear inventario»: la prueba de la Vendedora con el mensaje exacto y el motivo en el historial del movimiento;
    - «Cobrado» suma `amount` y todo cobro entrante (igual que la Caja de hoy); no hay prueba con costo FIFO;
    - Brian sin huecos: descuentos, facturar desde una cotización, fusionar contactos, margen por producto, recibir
      compras.

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
| #9, #10, #12 | Lectores y etiquetas de códigos de barras | 8 |
| #15 a #21 | CRM, fase 2: seguimiento de cotizaciones sin respuesta (#16), invitar a la tienda (#17), posventa (#18), Brian y oportunidades (#19), perder oportunidades (#20), cotizaciones fuera de la conversación (#21) | 13 |
| #22, #23 | Privacidad (Ley 81): zona de entrega y borrar la oportunidad con la conversación; lo que «Eliminar conversación» todavía no borra | 11 |
| #24 | Juan: hallazgos que quedaron para después | 12 |
| #25 | Conversaciones: permisos de escritura y seguimiento por persona | 5 |
| #26 | Brian: topes de gasto, de archivos y de dinero | 4 |
| #27 | Puerta del equipo `/master` | Sin fecha |
