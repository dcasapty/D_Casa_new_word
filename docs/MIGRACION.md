# Cargar los datos del sistema anterior (`dcasa_migracion`)

Pantalla de **Ajustes › Cargar datos del sistema anterior** (solo administradores). Carga, **una sola vez**, lo que
deja la receta de migración (Cowork, en la computadora de la dueña): clientes, proveedores, productos, existencias,
precios de proveedor y lo que quedó a medias (ventas por facturar o entregar, compras por recibir o facturar).

> **Los datos de las personas nunca pasan por GitHub, por el repositorio ni por el chat.** El archivo de clientes se
> sube desde el navegador, directo a Odoo, con la sesión de un administrador. El módulo no trae ningún dato de personas
> (una prueba lo vigila) y el servidor no escribe nombres en sus registros: solo cantidades.

## Qué se carga y qué no

| Entra | Archivo | Cómo |
|---|---|---|
| Clientes con compras (958 en la exportación del 2026-10-12) | `clientes.csv` | Una ficha por cliente, con su número del sistema anterior |
| Proveedores con facturas u órdenes de compra | `proveedores.csv` | Mismo formato que `clientes.csv`; quien es cliente y proveedor tiene una sola ficha |
| Productos activos (555) | `productos.csv` | Mismas reglas del inventario anterior |
| Existencias (444 filas) | `inventario.csv` | Se reemplazan por las del archivo |
| Precios de proveedor (251) | `precios_proveedor.csv` | `id_proveedor_viejo, codigo_producto, precio` y, si hay, `cantidad_minima` |
| Ventas con algo pendiente (27) | `ventas_pendientes.csv` + `ventas_pendientes_lineas.csv` | Las **por facturar** (24) quedan como factura en **borrador**; las **por entregar** (10) solo se listan |
| Compras con algo pendiente (20) | `compras_pendientes.csv` + `compras_pendientes_lineas.csv` | Las **por recibir** (4) quedan como orden de compra confirmada; las **por facturar** (16), como factura de proveedor en **borrador** |

**Todavía no entra:** la **contabilidad** (todas las facturas del año, pagos y plan de cuentas): ver el final de este
documento. Se agrega a esta misma pantalla, con su propio cuadre contra el balance de comprobación del sistema viejo y la
firma del contador.

**No entra, a propósito:** el historial de ventas ya cerradas, los movimientos viejos de inventario, la configuración del
sistema anterior y sus ~2,700 adjuntos (las fotos de productos ya están en el catálogo).

## Paso a paso (el día del corte)

1. Exportar de nuevo el sistema anterior y correr la receta (`LEEME_RECETA.md`): deja `clientes.csv`, `productos.csv` e
   `inventario.csv` (UTF-8, coma, punto decimal). No abrirlos con Excel y guardarlos: subirlos tal cual.
2. **Ajustes › Cargar datos del sistema anterior**: subir los archivos. Conviene hacerlo **por pasadas** (primero
   `clientes.csv` y `proveedores.csv`, después `productos.csv` con `inventario.csv`, luego `precios_proveedor.csv` y al
   final las ventas y compras pendientes, que usan a los contactos y a los productos): cada pasada es una sola petición y
   tarda menos. Con
   datos del tamaño de la exportación del 2026-10-12, en una copia local: 958 clientes ≈ 20 s; 555 productos nuevos
   ≈ 105 s (si ya existen, solo se ajustan existencias y tarda menos). El informe dice cuánto tardó cada pasada.
3. **Revisar (no cambia nada).** Corre la carga completa y la deshace; el informe dice qué pasaría. Mirarlo con calma.
4. **Cargar.** Solo se habilita después de revisar con exactamente los mismos archivos y casillas. Si se cambia algo,
   hay que revisar otra vez.
5. Contar con el **Escáner** (Inventario › Escáner) lo que el informe marque: existencias negativas, productos sin código.

Primero se ensaya en **staging** con los archivos reales. En producción se carga una sola vez, **antes de vender**.

## Reglas

**Clientes**
- La llave es el número del sistema anterior (`id_viejo`), guardado como id externo `__import__.dcasa_contacto_<n>` (de
  «__import__», como los de la importación de Odoo, para que quitar esta pantalla algún día no borre clientes) y en la
  nota de la ficha. Volver a cargar el mismo archivo no crea nada y **no pisa** lo que ya se cambió aquí.
- **El candado de contactos no se salta.** Si el celular, el correo o el RUC/cédula ya son de otra ficha, esa fila no se
  crea y el informe dice con quién choca; se resuelve a mano (fusionar, o corregir el dato) y se vuelve a cargar.
- El campo Teléfono del sistema anterior es texto libre: el primer número con cifras suficientes va al teléfono; los demás
  van a la nota de la ficha (no se pierden). Un correo o un DV mal escritos tampoco se pierden: van a la nota.
- Todos llevan la etiqueta **«Sistema anterior»** (sirve para filtrar y, si hiciera falta, revertir).
- Un proveedor es una ficha con el papel de proveedor; si el mismo número aparece en `clientes.csv` y en
  `proveedores.csv`, es **una sola ficha** con los dos papeles.
- Un cliente **no es un socio**: no se le pone PIN ni celular de Socios, así que no reclama ficha ni junta puntos. Y no se
  le escribe nada: Juan solo contesta a quien le escribe.

**Precios de proveedor:** se enlazan por el número del proveedor y por el código del producto (los dos ya cargados). Un
producto con varias medidas recibe el precio en la medida del código. Volver a cargar no repite nada y **no cambia** un
precio que ya existe para ese proveedor, producto y cantidad mínima. Lo que no se pudo enlazar sale en el informe.

**Productos y existencias** (las reglas de la dueña del 2026-10-02, en [CATALOGO.md](CATALOGO.md))
- La llave es el **código**; sin código, el nombre exacto. Mismo código = mismo producto: se actualizan las existencias y
  **no** el nombre ni las fotos. Código nuevo = producto nuevo (publicado solo si tiene foto).
- Por defecto el **precio y el costo de un producto que ya existe no se tocan** (el catálogo nuevo puede tener precios que
  la dueña ajustó después). La casilla «También cambiar precio y costo…» los pasa a los del archivo.
- Un precio o un costo en 0 o vacío significa «no se registró»: no se usa. Un costo 0 nunca borra el real.
- Los archivados no se cargan. Las existencias de códigos que no son un producto activo se listan, no se cargan.
- Un producto activo **sin código** no recibe existencias (no se puede enlazar): se cuenta a mano. Igual las filas del
  inventario sin código.
- Existencias negativas entran en 0 y se listan. Un código repetido: solo entra el primero.
- Sin `inventario.csv` no se toca ninguna existencia.

**Ventas y compras pendientes** (`dcasa_migracion/documentos.py`). Solo se carga **lo que falta por hacer**, nunca el
historial ya cerrado:
- **Ventas por facturar → factura de cliente en borrador**, una por orden, con las cantidades `pendiente_facturar`. El
  borrador no tiene número, no va a la DGI ni suma puntos de Socios: quien factura la revisa y la publica, y recién ahí
  sale con el número que sigue en la numeración nueva. Lleva el número de la orden vieja en «Documento origen». El
  impuesto es el del producto; una línea sin producto (un servicio suelto, un código que no existe) lleva el nombre del
  archivo y el ITBMS de venta por defecto. Si la orden se factura completa y su total no coincide con el del archivo,
  el informe lo marca «revisar antes de publicar».
- **Ventas por entregar:** no se cargan. El informe las lista (orden, cliente, producto y cantidad) para entregarlas o
  rehacerlas a mano: esa mercancía ya cuenta en `inventario.csv`, y entregarla desde una orden cargada la descontaría
  dos veces.
- **Compras por recibir → orden de compra confirmada**, una por orden, solo con las cantidades `pendiente_recibir` y con
  la fecha y el número del proveedor del archivo. Al recibir la mercancía entra al inventario. Odoo no confirma una orden
  con líneas sin producto: si falta un producto, esa orden sale como error con el código que falta y se carga cuando el
  producto exista. Si el sistema anterior ya la había facturado (total o parcialmente), la nota de la orden dice
  «NO la factures otra vez» y el informe la lista. *El ensayo puede saltar números de órdenes de compra y de
  recepciones (las secuencias de Odoo no se deshacen); no importa, no son documentos fiscales.*
- **Compras por facturar → factura de proveedor en borrador**, una por orden, con las cantidades `pendiente_facturar`.
  Lleva el número del proveedor (`referencia_proveedor`); si el archivo no lo trae, el informe la lista para ponérselo a
  mano. La fecha de la factura la pone quien la registra (es la que trae el papel del proveedor).
- Todo es **idempotente**: cada documento guarda el número de la orden vieja como id externo (`__import__.dcasa_venta_<n>`,
  `dcasa_compra_<n>`, `dcasa_factura_compra_<n>`). Volver a cargar no repite nada, y borrar un documento permite cargarlo
  de nuevo.

## Qué falta: contabilidad histórica

Cowork entregó (2026-10-13) la exportación de **todas las facturas ya emitidas del año**, con la receta
`receta\exportar_facturas.py`: `facturas_clientes.csv` (1,005), `facturas_clientes_lineas.csv` (1,637),
`facturas_proveedores.csv` (14), `facturas_proveedores_lineas.csv` (40) y `pagos.csv` (1,141), más un `REPORTE.md` cuyo
cuadre coincide con la contabilidad del sistema anterior. Lo que dice el reporte y hay que tener presente:

- El sistema anterior solo tiene facturas **desde el 22 de julio**; de enero a julio no hay nada en él (si se facturó en
  otro programa, eso es otra conversación).
- No hay notas de crédito en el periodo; los archivos están preparados para incluirlas el día del corte.
- `referencia_fiscal` (número de factura electrónica) viene vacía y `condicion_pago` también en las de cliente.
- 2 facturas están a nombre de la propia empresa (su cliente no está en `clientes.csv` a propósito); 3 facturas de
  proveedor tienen total 0 y 3 tienen fecha contable adelantada: se listan para revisar, no se cargan a ciegas.
- 41 cobros sin conciliar con el banco y 7 pagos sin aplicar a ninguna factura.

El cargador de esta etapa respeta los números originales de cada factura, enlaza cada pago a su factura, **no reenvía
nada a la DGI ni da puntos de Socios**, y deja que las facturas nuevas continúen la numeración. Antes de escribirlo
quedan por decidir con el contador: cómo se relacionan las cuentas del sistema anterior con las de aquí, qué hacer con
los pagos sin conciliar y las facturas raras de arriba, y el balance de comprobación al día del corte contra el cual
cuadra el total por cuenta (al centavo, firmado por el contador).
