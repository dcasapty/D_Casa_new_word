# Control de existencias: mermas, bitácora de bodega y alertas (`dcasa_existencias`)

Módulo nuevo del 2026-10-22 (etapa 4 «Bodega» de [PRIORIDADES.md](PRIORIDADES.md) y la decisión F6 de
[DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md)). El panel de bodega para tablet y el historial de movimientos en
palabras son trabajos aparte.

## 1. Mermas, daños, muestras y regalos (F6)

**Dónde:** Inventario › Operaciones › Ajustes › **Mermas, daños, muestras y regalos** (Gerencia).

- Se elige el producto, cuántos y el **código**: merma, daño, muestra o regalo. «Qué pasó» queda escrito. El
  **proveedor** se propone solo (el primero del producto) para poder reclamarle.
- **«Dar de baja»** lo hace **Gerencia** (el gerente de Inventario): baja la existencia con el desecho de Odoo y queda el
  **costo** (el del movimiento; si no, el costo del producto por la cantidad). Un producto **sin costo no se da de baja**
  (F1: sin costo la pérdida no se vería). Cualquiera con Inventario puede dejar una merma **en borrador** (no mueve nada).
  El «Desechar» de Odoo desde una entrega o recepción también pide el código, y también es solo de Gerencia.
- **El asiento:** con las cuentas elegidas (Inventario › Configuración › **Ajustes de bodega y mermas**): debe la
  **cuenta de las mermas** (la partida propia del estado de resultados, mes a mes y en el año) y haber la **cuenta que se
  rebaja** (inventario, si se lleva al día; compras o costo, si se cuenta a fin de mes: depende de cómo lo lleve la
  contadora). **Vienen vacías**: el plan de cuentas de Panamá no trae una cuenta de mermas y no se inventa (I5: el plan
  se revisa con la contadora). Sin ellas la merma queda registrada con su costo y «Falta la cuenta contable»; la
  pantalla lo dice y, cuando estén, **«Contabilizar las mermas pendientes»** las asienta. Si un asiento no se puede (un
  mes cerrado), la merma igual se da de baja y queda «No se pudo» con el motivo en su historial.
- **Mermas del mes** (Inventario › Reportes): el total del mes por código, **lo comprado** (lo que entró desde
  proveedores, recepciones validadas, a costo y sin ITBMS, menos lo devuelto), el porcentaje y el **aviso del 0.5 %**
  (cifra de la gerencia, F6; se cambia en Ajustes de bodega). Sin compras en el mes, cualquier merma «pasa». Abajo, el
  año mes a mes y, por proveedor, lo que falta reclamar y lo reclamado.
- **El aviso:** la pantalla del mes en rojo, una nota en la merma que lo pasa (una vez al mes), el **Inicio de Gerencia**
  (franja de atención) y, si se encienden, las alertas por Telegram.
- **Reclamo al proveedor:** desde «Mermas del mes» › «Reclamo a un proveedor (PDF)»: proveedor y fechas → el PDF con la
  marca (fecha, producto, cantidad, qué pasó y costo) y «Marcar como reclamadas».

## 2. Bitácora de bodega

**Dónde:** Inventario › Reportes › **Bitácora de bodega** (Gerencia; la Vendedora no la ve, decisión 5 del 16/10).

- Cada ajuste de existencias: **cuándo, quién, producto, antes → después, diferencia, valor a costo, motivo y desde
  dónde** (Inventario físico, Escáner › Contar, Brian, deshacer un ajuste, merma o el sistema).
- **El motivo es obligatorio.** El «Aplicar» del Inventario físico abre una ventana con el motivo **vacío** (Odoo traía
  «Inventario físico» escrito); sin motivo no se aplica. El Escáner manda «Conteo con lector (quién)», Brian el motivo
  que le dice la persona y una merma su código y «qué pasó». Escribir «A la mano» directo (sin «Contado» + «Aplicar»)
  ya no se puede: pide contar y aplicar. Lo que corre el sistema sin persona (una carga del catálogo) queda como
  «Ajuste del sistema».
- **Nadie la edita ni la borra** (ni Gerencia): la escribe el sistema. Un conteo que coincide no se anota (no es un
  ajuste).

## 3. El hueco del Inventario físico (etapa 1, decisión 6)

Desde la etapa 1 el servidor ya no dejaba a la Vendedora escribir cantidades (`dcasa_base/models/stock_quant.py`).
Quedaban otros caminos, cerrados aquí, en el servidor y en la pantalla:

| Camino | Antes | Ahora |
|---|---|---|
| Menú Inventario › Ajustes › Inventario físico | Visible para la Vendedora (el servidor rechazaba) | Solo Gerencia |
| Menú Desechos y «Desechar» desde una entrega | Cualquiera con Inventario daba de baja | Solo Gerencia confirma |
| «Deshacer el ajuste» del historial de movimientos | Cualquiera con Inventario | Solo Gerencia, y queda en la bitácora |
| Un movimiento hacia o desde «Ajuste de inventario» o «Desecho» por RPC | Lo podía crear quien tuviera Inventario | Solo Gerencia (stock.move y stock.move.line) |

Entregas, recepciones y devoluciones siguen igual para todos (no son ajustes).

## 4. Alertas diarias por Telegram a Gerencia

**Dónde:** Inventario › Configuración › **Ajustes de bodega y mermas** (Gerencia).

- **Apagadas de fábrica y sin umbrales.** Cada alerta sale solo si la dueña la enciende y pone su número; si un día no
  hay nada que avisar, no llega nada.
  - **Productos por agotarse:** «cuando queden estas unidades o menos» (0 = solo los agotados).
  - **Ajustes grandes:** desde cuántas unidades y/o desde cuánto dinero (a costo), desde la revisión anterior.
  - **Mes sin cerrar:** desde qué día del mes siguiente (la gerencia decidió cerrar a más tardar el día 5, I1; el día del
    aviso lo pone ella).
  - **Mermas sobre el tope** (el 0.5 % de arriba).
- Llegan cada mañana (acción planificada «D'CASA: alertas diarias de bodega», 7:00 de Panamá) por el bot de Brian a
  cada persona de **Gerencia** que vinculó su Telegram (respeta la lista de chats permitidos de Brian). Un fallo de
  Telegram nunca rompe nada: queda en el log. La pantalla muestra el último mensaje enviado.

## 5. Brian

`resumen_de_mermas`, `registrar_merma` (con confirmación), `bitacora_de_bodega`; y `ajustar_existencias` /
`ajustar_existencias_en_bloque` piden ahora el motivo. Ver [BRIAN.md](BRIAN.md).

## 6. Técnico

- `models/merma.py` (`stock.scrap`: `dcasa_motivo`, `dcasa_costo`, `dcasa_proveedor_id`, `dcasa_reclamo`,
  `dcasa_contabilidad`, `dcasa_asiento_id`; `_dcasa_resumen_mes`, `_dcasa_compras_del_mes`), `models/bitacora.py`
  (`dcasa.bitacora.bodega` y los candados en `stock.quant`, el asistente del motivo, `stock.move`, `stock.move.line`),
  `models/config.py` (`dcasa.existencias.config`, uno por empresa), `models/alertas.py` (cron), `models/tablero.py`
  (franja del Inicio), `wizard/resumen.py` y `wizard/reclamo.py`, `report/reclamo.xml`.
- Valoración: Odoo 19 de fábrica es periódica (costo estándar). El costo de la merma sale del movimiento de Odoo; el
  asiento es propio y no usa la cuenta de la ubicación de desecho (si alguien le pone una, Odoo haría su propio asiento
  al cierre de inventario: no se hace las dos cosas).
- Pruebas: `scripts/test.sh dcasa_existencias` (`test_mermas.py`, `test_bitacora.py`, `test_alertas.py` y
  `test_pantallas.py` en Chrome a 1366 y 390 px).
