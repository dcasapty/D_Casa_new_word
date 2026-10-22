# Decisiones contables de la gerencia (respuestas del 17 y del 18 oct 2026)

Respuestas del jefe a las preguntas contables (A1–H5 el 17 oct; I1–L8 el 18 oct: ya no queda ninguna sin responder).
Aquí van **las reglas**, sin nombres de personas ni cifras del negocio (el repositorio es público): los montos y los
casos uno a uno se ven en Odoo con la gerencia. Donde la respuesta dice una persona, aquí va su cargo (Gerencia).

**En producción desde el 2026-10-18** (Desplegar 19, PR #55): A3 (30 días y anticipo del 50 %), A5 (el cobro solo en Caja), A6 (anular o pasar a borrador
solo Gerencia), A7 (notas de crédito, devoluciones y saldo a favor solo Gerencia) y C1 (Tafi y Crediviva). Cómo quedó
cada una, abajo («Hecho»); qué ve cada rol, en [PERMISOS.md](PERMISOS.md).

## Ventas y cobro (A)

| # | Decisión | Qué cambia en el sistema |
|---|---|---|
| A1 | «Vendido» = **todas las facturas publicadas** y, debajo, cuántas salieron de un pedido de una vendedora (opción C). | Choca con el comparador en producción (cuenta pedidos): se le pregunta a la dueña cómo quedan «Completadas / Con abonos». |
| A2 | La venta se cuenta **el día de la factura** (como hoy). | Igual que «Con abonos»; «Completadas» cuenta el día del último pago (decisión de la dueña del 17 oct): confirmar. |
| A3 | Crédito solo a clientes que abonan o a personas o empresas **autorizadas por Gerencia**. Abono: **anticipo mínimo del 50 %** y **30 días continuos** para completar el pago; ese vencimiento lo ve el cliente. Menos del 50 %: lo autoriza Gerencia. | **Hecho.** El abono vence a los **30 días continuos** del primer abono (parámetro `dcasa_invoice.abono_dias`, 30 de fábrica, 0 = no vence; la migración pasa el viejo `abono_meses`: 1 mes → 30 días). El papel de ABONO, las Condiciones, «Mi cuenta», los correos y Brian leen la misma función (`_dcasa_estado_abono`). El **primer abono** (factura sin pagos) es al menos **la mitad del total**; menos, solo Gerencia o un administrador (el asistente «Pagar» lo avisa; Brian y el Inicio pasan por lo mismo). Los abonos siguientes y el pago completo son libres. La conciliación bancaria no se frena: deja una nota en la factura para que Gerencia la revise. Crédito a personas o empresas autorizadas: **falta** (no hay regla en el sistema). |
| A4 | Igual que A3. | — |
| A5 | **El cobro solo en Caja** por ahora. | **Hecho.** Registran cobros de clientes **Caja, Gerencia, contabilidad y los administradores**. La Vendedora ya no cobra por ningún camino (asistente, botón, cobro suelto, aplicar un cobro que ya estaba, Brian, Inicio, RPC), con «ver solo lo suyo» encendido o apagado; su factura dice «El cobro lo registra Caja». **Sigue facturando y cotizando** (confirmado por la dueña el 17 oct). |
| A6 | Pasar a borrador o anular una factura publicada: **solo Gerencia**. | **Hecho.** Regla en el servidor para facturas, notas y recibos de clientes publicados (botones y escritura directa del estado): solo Gerencia y administradores; a Caja, contabilidad y la Vendedora les sale «… lo hace solo Gerencia. Pídeselo a Gerencia.». Lo de proveedores no cambia. |
| A7 | Devolver dinero, dar saldo a favor o cambiar el producto, según el caso; **lo autoriza en el sistema Gerencia**. | **Hecho.** Notas de crédito de clientes (crearlas o publicarlas), devolverle dinero a un cliente (cobro saliente o «Pagar» una nota), cobrar de más dejando saldo a favor y dar una factura por pagada con una diferencia: solo Gerencia y administradores. |

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

- C1: faltan **Tafi** y **Crediviva** (financian directo al cliente): formas de pago nuevas. **Hecho:** diarios de banco
  «Tafi (financiamiento)» y «Crediviva (financiamiento)», activos y en el asistente «Pagar» (una vez por base, sin pisar
  uno que ya exista). **La contadora debe revisar su cuenta contable** (el sistema les creó una cuenta de banco propia
  a cada una) y cómo se cruza lo que la financiera deposita después.
- C2/C3: los extractos se bajan del banco y de Yappy. El efectivo casi nunca se deposita (C5).
- C4: **fondo fijo de caja** al inicio y cierre de cada turno; hoy se cuadra en un formato propio (físico, documentos
  contra sistema) que la gerencia mostrará.
- C8: entran y salen aportes y retiros de los dueños: una **partida propia** que se integre al estado de resultados.
- C9: cada transferencia se asocia a un documento de venta y se coteja con el cierre de caja diario y el banco.

## Clientes (D)

- D1: **ajustar** los saldos de un centavo. Idea de la gerencia: que un cajero tenga un tope de descuento y, si lo
  pasa, llegue un mensaje al teléfono de la gerencia con una **clave para autorizar**; al crecer, un gerente de tienda
  con reportes diarios, semanales, mensuales y anuales a la junta.
  **Hecho (rama `datos-clientes`, 2026-10-22):** (1) **Descuento con clave:** la Vendedora y Caja siguen con su tope
  (Ajustes de Ventas); para más, en la cotización «Pedir descuento a Gerencia» (un % sobre el total o un importe fijo,
  con el motivo). A cada persona de Gerencia le llega por Telegram (el bot de Brian, solo a chats vinculados) **su propia
  clave** de 6 números con la cotización, el total antes y después y el motivo; quien pidió la escribe y el descuento
  se aplica solo. Vale **una vez**, solo para **esa cotización y ese total**, vence a los minutos de Ajustes de Ventas
  (10 de fábrica) y cinco claves equivocadas la bloquean. Sin Telegram, la pantalla dice que Gerencia lo apruebe en
  persona: **Ventas › Descuentos por autorizar** (aprobar y aplicar, o rechazar). Queda registrado quién pidió, a quién
  le llegó, quién autorizó (por su clave), cuánto y cuándo, también en el historial de la cotización. Después del
  descuento autorizado, la vendedora no puede empeorarlo. (2) **Saldos de centavos:** Contabilidad › Clientes › Saldos
  de centavos: facturas, notas y cobros de clientes con **1 a 5 centavos** de redondeo (rango fijo: el ITBMS por línea y
  el vuelto en monedas; más ya no es redondeo), vista previa y cierre con un asiento de ajuste contra las cuentas de
  diferencias de la empresa. Lo hacen Gerencia y contabilidad. Brian: `pedir_descuento_a_gerencia`,
  `aplicar_descuento_con_clave`, `descuentos_por_autorizar`, `decidir_descuento`, `saldos_de_centavos`,
  `cerrar_saldos_de_centavos`.
- D2: los saldos a favor se revisan juntos.
- D3: abonos a 30 días; **correo 5 días antes del vencimiento** y, si se puede, **WhatsApp**.
  **Hecho (rama `datos-clientes`, 2026-10-22):** el correo de recordatorio 5 días antes, uno por abono y vencimiento,
  apagado mientras no haya clave de Resend (`docs/CORREO.md`, 6b); la lista **Facturación › Clientes › Abonos por
  vencer** con un botón que abre WhatsApp con el mensaje listo (lo manda una persona). El WhatsApp automático queda
  apagado: por el puente QR es lo que más riesgo de bloqueo da, y por la API oficial hace falta Meta (plantillas).
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
- F5: **nombres de productos en MAYÚSCULAS** y unificar los repetidos. **Hecho (rama `datos-clientes`, 2026-10-22):**
  lo nuevo se guarda en mayúsculas; lo de antes, con vista previa en Ventas › Productos › Nombres en MAYÚSCULAS; los
  repetidos (mismo código, código de barras o nombre) en Ventas › Productos › Productos repetidos, con el asistente para
  unirlos sin perder historia (`docs/CATALOGO.md`).
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

## Cierres y control (I)

- I1: los meses de agosto y septiembre **no se han cerrado** porque no se sabía cómo se hace en el sistema. El cierre lo
  hace Gerencia (o alguien que ella autorice), **nunca después del día 5 del mes siguiente** (idealmente el mismo día
  del fin de mes). Antes, explicarle a la gerencia qué abarca un cierre (pantalla de cierre de `dcasa_contabilidad`).
- I2: el año fiscal termina el **31 de diciembre** (lo que ya usa el sistema).
- I3: validar compras, anular facturas, registrar cobros, ver toda la contabilidad y cerrar meses: **Gerencia**.
- I4: la gerencia pidió entender el segundo factor y la cuenta genérica «admin» antes de decidir (explicado en el chat
  del 18 oct; pendiente su respuesta).
- I5: el plan de cuentas se revisa juntos; hace falta un **inventario de bienes muebles** (mobiliario, equipos, marca).
  Anticipos de clientes: la gerencia propone «Bancos y efectivo» o una similar; **lo decide la contadora** (en Odoo la
  cuenta de anticipos de clientes es un pasivo, no un banco).
- I6: los comprobantes se guardan durante el año fiscal y después se mandan **todos en un ZIP** de respaldo por **5
  años** (lo que exige la DGI).

## Socios y Vendedores (J)

- J1: el costo real de cada premio y el valor del punto en dólares están **por desarrollar** con los productos a
  otorgar (`puntos.json` no cambia hasta tener las cifras).
- J2: los puntos y las comisiones se anotan como **gasto de marketing al acreditarse** (afectan el estado de resultados).
- J3: **el canje por efectivo queda descartado**: en efectivo el costo es el 100 %; en producto, lo que el socio percibe
  vale más que lo que le cuesta a D'CASA. `canje.efectivoHabilitado` sigue apagado y ya no se espera un dictamen
  para encenderlo (el de los negocios externos, `canje.externosHabilitado`, sigue esperando al abogado).

## Lo que quiere ver la gerencia (K)

- K1: además de los números ya acordados, el **ticket promedio** y las **unidades vendidas por tipo** (camas,
  colchones, etc.) hasta un total.
- K2: arrancar **2027 con presupuesto** (plan contra real) de ventas y de gastos operativos.
- K3: por ahora no hay otra empresa ni otra moneda (se contemplan a futuro).
- K4: los reportes van al **socio** de la empresa.

## Cómo trabajará la extensión contable (L)

- L1/L2: la extensión puede dejar cosas **en borrador** sola; publicar, validar, pagar, cerrar un mes o conciliar lo
  **aprueba solo Gerencia** (una sola persona aprueba por ahora).
- L3: entra con un **usuario propio**, de permisos limitados y con **segundo factor**: todo queda a su nombre.
- L4: puede corregir durante todo el ejercicio fiscal y **hasta 4 meses después** del cierre fiscal.
- L5: **copia de seguridad antes de cada tanda**, siempre.
- L6: de acuerdo con el orden de trabajo propuesto. L7: sin cuentas, clientes ni proveedores vedados, sin tope por día.
- L8: al terminar cada tanda, un **resumen corto con el antes y el después** de cada cifra importante.
