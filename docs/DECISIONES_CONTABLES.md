# Decisiones contables de la gerencia (respuestas del 17 oct 2026)

Respuestas del jefe a las preguntas contables (A1–H5). Aquí van **las reglas**, sin nombres de personas ni cifras del
negocio (el repositorio es público): los montos y los casos uno a uno se ven en Odoo con la gerencia. Las preguntas
I1–L8 siguen sin respuesta.

## Ventas y cobro (A)

| # | Decisión | Qué cambia en el sistema |
|---|---|---|
| A1 | «Vendido» = **todas las facturas publicadas** y, debajo, cuántas salieron de un pedido de una vendedora (opción C). | Choca con el comparador en producción (cuenta pedidos): se le pregunta a la dueña cómo quedan «Completadas / Con abonos». |
| A2 | La venta se cuenta **el día de la factura** (como hoy). | Igual que «Con abonos»; «Completadas» cuenta el día del último pago (decisión de la dueña del 17 oct): confirmar. |
| A3 | Crédito solo a clientes que abonan o a personas o empresas **autorizadas por Gerencia**. Abono: **anticipo mínimo del 50 %** y **30 días continuos** para completar el pago; ese vencimiento lo ve el cliente. Menos del 50 %: lo autoriza Gerencia. | El vencimiento del abono pasa de «un mes» a 30 días; el primer abono menor al 50 % solo lo registra Gerencia. |
| A4 | Igual que A3. | — |
| A5 | **El cobro solo en Caja** por ahora. | Las vendedoras no registran cobros (con el paquete de permisos). Falta confirmar si también dejan de facturar. |
| A6 | Pasar a borrador o anular una factura publicada: **solo Gerencia**. | Regla en el servidor. |
| A7 | Devolver dinero, dar saldo a favor o cambiar el producto, según el caso; **lo autoriza en el sistema Gerencia**. | Notas de crédito y reembolsos solo Gerencia. |

## Saldos iniciales e historia (B)

- B1/C7: los saldos de bancos empiezan **en una fecha que se definirá**, en la mañana, después de las acreditaciones.
- B1/C6: el punto de venta del banco cobra una **comisión por tipo de tarjeta** y **retiene ITBMS**; al registrar la
  forma de pago debería restarse y acreditarse al libro de bancos, por **lote diario cerrado** en cada punto de venta.
  La tabla de días y porcentajes la entrega la gerencia. Yappy acredita el día hábil siguiente.
- B2: solo desde la fecha de inicio (saldos, cuentas por pagar por proveedor, etc.).
- B3: el balance inicial se revisa en reunión (mobiliario e inversiones que no están en el sistema).
- B4: la **numeración de cuentas sigue la del sistema anterior**.
- B5: **conforme** con cargar la historia; los cobros sin cruzar y los pagos sin aplicar se revisan **uno a uno** con la
  gerencia.
- B6: por ahora los libros los lleva la contadora; se llevarán **ambos** (contadora y Odoo).

## Bancos y caja (C)

- C1: faltan **Tafi** y **Crediviva** (financian directo al cliente): formas de pago nuevas.
- C2/C3: los extractos se bajan del banco y de Yappy. El efectivo casi nunca se deposita (C5).
- C4: **fondo fijo de caja** al inicio y cierre de cada turno; hoy se cuadra en un formato propio (físico, documentos
  contra sistema) que la gerencia mostrará.
- C8: entran y salen aportes y retiros de los dueños: una **partida propia** que se integre al estado de resultados.
- C9: cada transferencia se asocia a un documento de venta y se coteja con el cierre de caja diario y el banco.

## Clientes (D)

- D1: **ajustar** los saldos de un centavo. Idea de la gerencia: que un cajero tenga un tope de descuento y, si lo
  pasa, llegue un mensaje al teléfono de la gerencia con una **clave para autorizar**; al crecer, un gerente de tienda
  con reportes diarios, semanales, mensuales y anuales a la junta.
- D2: los saldos a favor se revisan juntos.
- D3: abonos a 30 días; **correo 5 días antes del vencimiento** y, si se puede, **WhatsApp**.
- D4: no hay facturas dadas por perdidas identificadas.

## Compras y proveedores (E)

- E1/E2: las compras por validar y las recepciones atrasadas se revisan **una a una** con la gerencia.
- E3: los pagos a proveedores los autoriza la gerencia; el banco depende de la disponibilidad.
- E4: hay proveedores del exterior; se costean en una hoja de cálculo propia; moneda: dólar.
- E5: hay compras con y sin factura. E6: hay anticipos a proveedores que hoy no están en el sistema.

## Costos e inventario (F)

- F1: **ningún producto con costo 0** (altera la utilidad); los costos están en una hoja de cálculo de la gerencia.
- F2: **costo promedio** (a confirmar la práctica contable).
- F3: el costo incluye **flete, aduana, descargue y todo gasto asociado**.
- F4: el inventario va en el balance **sin ITBMS**, con opción de verlo con ITBMS. Hubo un conteo aleatorio reciente.
- F5: **nombres de productos en MAYÚSCULAS** y unificar los repetidos.
- F6: mermas, daños, muestras y regalos: una partida con código, costo, en el estado de resultados mensual y anual,
  para reclamar a proveedores; **aviso si pasa del 0.5 % de lo comprado**.
- F7: no hay consignación (podría haber).

## Gastos y planilla (G)

- G1/G3: la lista de gastos está en una hoja de cálculo; cada gasto a su cuenta; **recibos de caja chica** para pagos a
  eventuales.
- G2: los gastos se registran **desde el 1 de noviembre**.
- G4: planilla **quincenal**, se paga por banco; aún no se ha corrido en Odoo; **comprobante de pago** imprimible o por
  correo para cada empleado.
- G5: las tasas las validan los contadores. G6: comisiones los **5 primeros días de cada mes**. G7: puede haber
  adelantos o préstamos a empleados: el sistema debe controlarlos. G8: reembolsos, los autoriza Gerencia.

## Impuestos y reportes (H)

- H1: ITBMS mensual, lo llevan los contadores. H2: sin exentos ni retenciones por ahora. H3: otros impuestos, a
  validar con los contadores para el estado de resultados.
- H4: ya tienen **máquina fiscal**: hace falta una integración selectiva.
- H5: la gerencia mostrará el reporte que lleva para los socios.
