# El CRM que se ajusta solo (diseño, fallas del plan y cómo se cierran)

Pedido de la dueña (2026-10-10): «me gustaría pensar que el CRM no depende de las vendedoras». Esta página es el
diseño que se construyó y, antes, **las fallas que se encontraron en el plan original** leyendo el código real
(no hay nada de esto que sea suposición: cada punto cita el archivo). Módulo: `addons/dcasa_conversaciones`.

## El plan original (lo que se propuso en el chat)

1. Etapas de la oportunidad que se mueven solas con hechos verificables (cotizada, ganada).
2. Datos que Juan anota solo: producto, presupuesto, zona de entrega, para cuándo.
3. Prioridad caliente / tibio / frío con hechos, y la lista «a quién escribirle hoy».
4. Brian informante: «¿cómo va el CRM esta semana?».

## Fallas del plan (y qué se hizo con cada una)

| # | Falla | Dónde se vio | Cómo se cierra |
|---|---|---|---|
| 1 | **Ninguna cotización estaba ligada a la oportunidad.** Ni la que arma Juan ni la que se crea desde la pantalla ponían `sale.order.opportunity_id`: «cotizada» y «ganada» no se habrían podido deducir. | `herramientas_juan_cotizacion._j_crear_cotizacion`, `conversacion_panel_catalogo.crear_cotizacion` | Las dos rutas ligan la cotización a la oportunidad de la conversación. |
| 2 | **Se puede cotizar sin oportunidad.** Juan cotiza aunque nunca llamó a `crear_oportunidad`: sin oportunidad no hay seguimiento (regla de la dueña) ni etapa. | `herramientas_juan_cotizacion._juan_cotizar` | Pedir la cotización **es** interés concreto: si no hay oportunidad abierta, se crea (o se reutiliza la reciente) y se liga. |
| 3 | **«Ganada» no la marca Odoo.** `sale_crm` solo sube el ingreso esperado al confirmar (`_update_revenues_from_so`); y confirmar no es vender (los **apartados** web se confirman sin pagar). | `vendor/odoo/addons/sale_crm/models/crm_lead.py` | «Ganada» = una **factura pagada de una cotización ligada** (la misma idea de «ya es cliente» del seguimiento: `paid` o `in_payment`). |
| 4 | **Enganchar la lógica a facturas, ventas o inventario puede romperlos.** Las facturas calculan `payment_state` con campos calculados que ni siquiera pasan por `write`. | `account.move` | **Cero overrides** en facturación, ventas o inventario. Un **cron** (cada 15 min) lee los hechos y aplica cambios idempotentes; más llamadas directas desde el código nuestro (cotizar). Todo en `savepoint` con `try/except`: un fallo se registra y **nunca** llega a quien llamó. |
| 5 | **Pelea con la vendedora.** Si ella mueve la etapa o cambia la temperatura y el cron la vuelve a mover, la automatización pisa a la persona. | — | **«La persona manda»:** cualquier cambio de etapa o de temperatura hecho por una persona apaga la automatización **solo en esa oportunidad** (`dcasa_auto_off`) y se ve con un aviso y un botón «Que Juan la maneje de nuevo». Solo avanza, nunca retrocede. |
| 6 | **«Perdida» por lo que la IA interpreta es peligroso**: un falso positivo cancela el seguimiento y la saca de las listas. | — | Perdida **solo por hechos**: N días sin ningún mensaje en la conversación y sin nada pendiente de una vendedora (tarea, conversación en sus manos o pedido confirmado sin pagar) (`crm_dias_para_perdida`: 30 por defecto, 0 = nunca, mínimo 14 para que los seguimientos —que terminan en menos de una semana— ya se hayan hecho). Se archiva (se recupera con «Restaurar») con el motivo «Sin respuesta». **No** hay perdida por «ya compré en otro lado» (queda en un issue). |
| 7 | **Etapas renombradas o borradas.** La dueña puede cambiarlas; buscar por nombre se rompería. | `crm_stage` real: New, Qualified, Proposition, Won (4 etapas de Odoo; sin personalizar) | Se buscan por **id externo** (`crm.stage_lead3`, y la etapa «ganada» por `is_won`); si no existen, no se hace nada y queda un aviso en el registro. |
| 8 | **El «próximo seguimiento» queda desactualizado** al cambiar la oportunidad por fuera de la conversación (el `write` de la conversación solo mira `oportunidad_id`). | `conversacion.write` | Al cambiar etapa, activo o probabilidad de una oportunidad, se recalcula el seguimiento de sus conversaciones. (El cron ya revisaba todo al enviar: nunca se enviaba de más.) |
| 9 | **La IA inventa datos** (zona, para cuándo) o **pisa lo que escribió una persona.** | `herramientas_juan._juan_crear_oportunidad` | Solo lo que el cliente dijo (lo exige la descripción de la herramienta), texto plano de hasta 80 letras, **nunca pisa un dato que ya tiene valor** (si difiere, queda una nota). |
| 10 | **La zona de entrega es un dato personal** (Ley 81) y borrar la conversación **no** borra la oportunidad (decisión anterior: «son registros del negocio»). | `conversacion_panel.py` (borrado) | Se pide lo mínimo (distrito o corregimiento, nunca la dirección exacta) y se documenta que, para un pedido de borrado, Gerencia también elimina la oportunidad (`docs/JUAN_ODOO.md › Privacidad`). |
| 11 | **Prioridad nativa (estrellas) vs. la nuestra.** Odoo ya usa `priority` en tableros y reportes. | `crm.lead.priority` | Campo propio `dcasa_temperatura` (1 frío, 2 tibio, 3 caliente; ordena bien) con insignia de color; la nativa no se toca. |
| 12 | **Contrato de herramientas para modelos pequeños** (≤ 5 parámetros, tipos simples, descripción < 260). | `dcasa_brian/tests/test_herramientas.py` | `crear_oportunidad` queda en exactamente 5 (`resumen`, `interes`, `presupuesto`, `zona`, `cuando`). Las nuevas de Brian son de lectura y con ≤ 3 parámetros. |
| 13 | **Costo de IA.** Más herramientas o más llamadas suben el gasto. | — | La temperatura, las etapas y la pérdida son **reglas fijas** (cero llamadas a la IA). Solo se agregan 2 parámetros opcionales a una herramienta que ya existe. |
| 14 | **Migración.** Oportunidades que ya existen en staging o producción. | — | Campos nuevos vacíos: sin temperatura y con la automatización **encendida**; el cron las evalúa con las mismas reglas. Hay un interruptor general en Ajustes de Juan (`crm_automatico`) para apagar todo de un clic. |
| 15 | **Carreras** entre el cron y una vendedora que edita. | — | Cada oportunidad se procesa en su propio `savepoint`; un error de serialización se registra y se reintenta en la siguiente vuelta. |
| 16 | **Ruido en el historial.** Un mensaje por cada cálculo llenaría la ficha. | — | Solo se anota cuando **cambia** algo (etapa, ganada, perdida, temperatura), con la causa en una frase. |

## Reglas (todas fijas y con prueba: `models/crm_reglas.py`, `tests/test_crm_automatico.py`)

**Etapas** (solo avanzan; solo con la oportunidad activa y pendiente; solo si nadie tomó el control):

- **Cotizada** → etapa «Propuesta» (`crm.stage_lead3`) cuando hay una cotización ligada **enviada** (`sent`) o confirmada.
- **Ganada** → etapa ganada (`is_won`) cuando una cotización ligada tiene una factura **pagada** (`paid` / `in_payment`).
  Anota quién pagó qué factura.
- **Perdida** → archivada con el motivo «Sin respuesta» (ver falla 6).

**Temperatura** (`1` frío · `2` tibio · `3` caliente), por puntos:

| Hecho | Puntos |
|---|---|
| Hay una cotización enviada o confirmada | +3 |
| El cliente dijo para cuándo lo quiere | +2 |
| El cliente dijo su zona de entrega | +1 |
| Escribió en las últimas 48 horas | +1 |
| Escribió 4 o más veces en la última semana | +1 |
| Lo atiende una persona | +1 |

5 o más = caliente · 3 o 4 = tibio · menos de 3 = frío. **Se enfría con el tiempo:** sin mensajes del cliente en más de 7 días,
como mucho tibio; en más de 14 días, frío. Se recalcula cada 15 minutos y al cotizar. La causa queda en
`dcasa_temperatura_motivo` («pidió cotización, dijo para cuándo»).

**A quién escribirle hoy:** oportunidades pendientes, **tibias o calientes**, de una conversación, a las que **ninguna vendedora
les ha escrito en las últimas 24 horas** (campo calculado `dcasa_para_hoy`; la misma regla sirve al filtro, al Inicio y a Brian).
No se usa «el último mensaje es del cliente», porque Juan contesta al instante y casi nunca se cumpliría. Están ordenadas de
más caliente a más fría en **Conversaciones › Oportunidades**, en el acceso del Inicio y en Brian (`para_hoy`).

## Lo que se corrigió después de la auditoría (`docs/auditoria/ronda8/crm-juan-brian.md`)

- **Lo que ya existía no se adopta.** Las oportunidades de conversaciones que había antes de esta versión (migración `19.0.1.1.0`) y
  las que una vendedora abrió **a mano** y luego se ligaron a una conversación quedan «en manos de una persona»
  (`dcasa_auto_off`) y salen como «fría — la maneja una persona». Para que Juan las maneje: desmarcar *Una persona tomó el control*.
- **El cron revisa todas**, de la más vieja a la más nueva, por tandas de 200, cerrando la transacción entre tanda y tanda.
- **«Propuesta» solo con una cotización que sí salió.** La cotización de Juan nace en borrador y pasa a *Enviada* cuando el PDF ya
  está en el hilo; si el PDF falla, queda en borrador (ligada a la oportunidad, para que la vendedora la encuentre) y nada avanza.
- **«A quién escribirle hoy»** solo cuenta mensajes de una vendedora que sí le llegaron al cliente (no notas internas, ni
  programados, ni fallidos).

## Lo que NO se hace en esta fase (queda escrito en issues del repositorio)

- Seguimiento específico de cotizaciones sin respuesta.
- Invitar a la tienda y agendar la visita.
- Posventa (cómo salió la entrega, recompra, puntos de Socios).
- Que Brian cierre o gane oportunidades (hoy solo lee).
- «Perdida» cuando el cliente dice que compró en otro lado (necesita revisión humana).

## Cómo apagarlo

*Conversaciones › Configuración › Ajustes de Juan › «CRM que se ajusta solo»*: desmarcar y guardar. Deja de moverse todo; lo
ya anotado queda como estaba. Para una sola oportunidad: moverla de etapa a mano (apaga la automatización en ella).
