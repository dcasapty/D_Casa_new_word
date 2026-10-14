# Cargar los datos del sistema anterior (`dcasa_migracion`)

Pantalla de **Ajustes › Cargar datos del sistema anterior** (solo administradores). Carga, **una sola vez**, lo que
deja la receta de migración (Cowork, en la computadora de la dueña): clientes, proveedores, productos, existencias,
precios de proveedor, lo que quedó a medias (ventas por facturar o entregar, compras por recibir o facturar) y la
contabilidad del año (todas las facturas emitidas y los pagos).

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
| Combos de cama y colchón (71 en la lectura de Cowork) | `combos.csv` (y la acción «Armar los combos desde su nombre») | Producto de tipo **Combo** de Odoo con sus piezas enlazadas; **nunca crea** una cama ni un colchón: ver «Combos» más abajo |
| Ventas con algo pendiente (27) | `ventas_pendientes.csv` + `ventas_pendientes_lineas.csv` | Las **por facturar** (24) quedan como factura en **borrador**; las **por entregar** (10) solo se listan |
| Compras con algo pendiente (20) | `compras_pendientes.csv` + `compras_pendientes_lineas.csv` | Las **por recibir** (4) quedan como orden de compra confirmada; las **por facturar** (16), como factura de proveedor en **borrador** |

| Facturas emitidas del año (1,005 de clientes, 14 de proveedores) | `facturas_clientes.csv` + `_lineas.csv`, `facturas_proveedores.csv` + `_lineas.csv` | Quedan **publicadas**, con su número original |
| Cobros y pagos del año (1,141) | `pagos.csv` | Quedan publicados y aplicados a sus facturas |

**Todavía no entra:** la equivalencia entre las cuentas contables del sistema anterior y las de aquí (decisión del
contador): ver «Facturas y pagos del año» más abajo.

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
- **El candado de contactos no se salta.** Si el celular o el correo ya son de otra ficha, esa fila no se crea y el
  informe dice con quién choca; se resuelve a mano (fusionar, o corregir el dato) y se vuelve a cargar.
- **Mismo RUC o cédula = misma persona** («un RUC, una persona»). Esa fila no crea otra ficha: su número del sistema
  anterior queda enlazado a la que ya existe (el mismo id externo `__import__.dcasa_contacto_<n>`), y sus órdenes,
  facturas y pagos se cargan a esa ficha. El informe los lista aparte («Repetidos enlazados…», con el número de la ficha a
  la que se enlazaron) para revisar que de verdad sean la misma persona. Salió del ensayo con la exportación del
  2026-10-12: 4 clientes repetidos por cédula y una venta pendiente de uno de ellos que se habría perdido.
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

## Facturas y pagos del año (`dcasa_migracion/historial.py`)

Cowork entregó (2026-10-13) la exportación de **todas las facturas ya emitidas del año** con la receta
`receta\exportar_facturas.py`, y su `REPORTE.md` cuadra con la contabilidad del sistema anterior. Lo que dice y hay que
tener presente: el sistema anterior solo tiene facturas **desde el 22 de julio** (de enero a julio no hay nada en él);
no hay notas de crédito en el periodo (los archivos están preparados para el día del corte); `referencia_fiscal` y
`condicion_pago` vienen vacías; 2 facturas están a nombre de la propia empresa (no están en `clientes.csv`), 3 facturas
de proveedor tienen total 0 y 3 tienen fecha adelantada; hay 41 cobros sin conciliar con el banco y 7 pagos sin aplicar
a ninguna factura.

**Reglas de la carga**
- **Quedan publicadas con el número que tenían** (`INV/2026/00123`, `BILL/2026/00007`…). La numeración nueva sigue donde
  quedó la última de cada diario: Odoo toma el último número publicado. Las facturas de proveedor siguen con su prefijo
  `BILL/` en vez del `FACTU/` del diario.
- Todo lleva la marca **«Cargada del sistema anterior»** (`dcasa_historica`, filtro en Facturas y aviso en el
  formulario). Es historia: **no se manda a la DGI** aunque la factura electrónica esté operando, **no da puntos de
  Socios** y no marca páginas de la tienda. Ni el número de FE ni el CUFE se cargan (la exportación no los trae).
- **Una factura solo entra si Odoo arma los mismos importes del archivo** (base, impuesto y total, con 2 centavos de
  tolerancia). Si no cuadra, no entra y el informe dice cuánto difiere: nada entra al libro con otro total.
- **Impuestos:** el nombre exacto, o cualquier «ITBMS 7%», es el ITBMS de la empresa (venta o compra); sin impuesto es una
  línea exenta; otro nombre es un error que dice cuál (créalo con ese nombre o cámbialo en el archivo).
- **Cuentas contables:** las de aquí (la del producto, la del diario, la del cliente o proveedor). Las equivalencias con
  las cuentas del sistema anterior son decisión del contador y **todavía no se aplican**: hasta entonces el cuadre es
  por factura, por saldo y por el libro de cuentas por cobrar y por pagar, no cuenta por cuenta.
- Una línea cuyo código no está en el catálogo entra sin producto, con el nombre del archivo. Un cliente o proveedor que
  no está cargado deja esa factura como error (así salen las 2 de la propia empresa: o se agrega la empresa a
  `clientes.csv`, o se registran a mano). Total 0 y fecha futura **sí entran**, pero salen en «Entraron, pero conviene
  mirarlas».
- **Notas de crédito:** montos en positivo, `tipo = nota_credito`, enlazadas a su `factura_original`. Odoo aplica la nota
  a su factura al publicarla.
- **Pagos:** el diario se busca **por nombre** entre los diarios de banco y efectivo (si no existe, el informe lo nombra:
  créalo con ese nombre en Contabilidad). Un pago **conciliado** con el banco entra directo a la cuenta del banco; uno
  **sin conciliar** queda como pago en tránsito esperando el extracto, igual que estaba. Se aplica a las facturas que
  decía pagar, en ese orden; lo que sobra, o un pago sin facturas, queda como saldo a favor de la ficha. Un pago que cita
  una factura que no está cargada entra igual y el informe lo lista.
- **Idempotente:** cada factura guarda su número anterior como id externo (`__import__.dcasa_factura_<número>`); cada pago,
  también: si `pagos.csv` trae la columna opcional `numero` (el del asiento del pago en el sistema anterior, lo ideal), el
  id sale de ese número; si no, de los datos del propio pago (fecha, monto, contacto, diario, referencia y facturas). Si se
  carga con una forma y después con la otra, los pagos se duplican: hay que usar siempre la misma. El asiento de cada pago
  también queda marcado como histórico. Volver a cargar no repite nada, y un pago que había quedado a medias se aplica
  cuando su factura llega.
- **Por tandas.** Una factura o un pago tarda ~0.2 s; ~2,100 documentos son ~8 minutos, demasiado para una sola
  petición. Cada «Cargar» trabaja ~40 segundos y dice cuántos faltan; se pulsa de nuevo hasta que ya no falte nada
  (unas 14 veces con los datos del año; en una copia local con 1,005 facturas y 1,141 pagos inventados tardó 9 minutos
  en total, sin errores, y el cuadre dio igual al archivo). **Revisar** corre una tanda y la deshace, pero su sección «Antes de cargar» abarca todo el archivo
  (contactos, impuestos, diarios o productos que faltan, facturas que los pagos citan y no están).
- **Cuadre al terminar:** base, impuesto, total y saldo del archivo contra lo cargado, las facturas que quedaron con otro
  saldo y lo que el libro mayor dice que deben los clientes (o se les debe a los proveedores). Si el libro no coincide con
  la suma de saldos del archivo, la diferencia son pagos sin aplicar o notas de crédito aplicadas distinto: lo revisa el
  contador y firma.

**Contabilidad completa (Cowork, 2026-10-13, `receta\exportar_contabilidad.py`):** el detalle de todas las líneas de
asiento (5,971 en 2,162 asientos) confirma que el libro del año son **solo** los asientos de las 1,005 facturas de cliente,
las 14 de proveedor y los 1,141 pagos, más 2 movimientos de extracto de banco en el diario de efectivo; **no hay asientos
manuales ni de apertura**. Debe y haber cuadran (347,725.70) en total y en cada asiento. Por eso cargar las facturas y los
pagos reproduce el libro; lo único que no cubre el cargador son esos 2 movimientos de efectivo, que esperan la equivalencia de
cuentas del contador. El archivo `balance_de_comprobacion.csv` (por cuenta y mes) y `plan_de_cuentas.csv` son la base del
cuadre cuenta por cuenta. Dos documentos que se registraron mientras Cowork exportaba (la factura `INV/2026/01018` y su cobro)
salieron en los zip pero no en las cabeceras: la exportación del día del corte los trae completos.

**El día del corte** (receta de Cowork): con los zip nuevos del sistema anterior en una carpeta, `python corte.py --datos
"..\CORTE_2026-xx-xx"` corre todo en orden (repetidos, clientes y productos, facturas y contabilidad), verifica que entren
`INV/2026/01018` y su cobro y que no quede ninguna línea sin asiento, y deja el resultado en `RESUMEN_CORTE.md`. **Exportar con
Odoo quieto**: nadie facturando ni cobrando mientras sale la exportación; si algo se registra durante ella, el resumen lo
avisa y se repite. `pagos.csv` ya trae la columna `numero` (la primera): el cargador la usa como id del pago.

**Para la prueba en staging:** crear antes los diarios de banco y efectivo con los nombres de la columna `diario` de
`pagos.csv`; subir los 5 archivos reales en esa pantalla (después de clientes, proveedores y productos); Revisar; leer
«Antes de cargar»; Cargar hasta que no falte nada; mirar el cuadre. Las facturas nuevas deben salir con el número que
sigue al último cargado, y ninguna debe aparecer en la cola de la DGI.

**Ensayo en producción con la exportación del 2026-10-12 (2026-10-14, «Revisar», nada se guardó):** contactos, productos,
precios de proveedor, ventas y compras pendientes y la primera tanda de facturas de clientes salieron sin errores
inesperados (70 s la última). Lo que dejó para decidir:
- **4 clientes repetidos por cédula** quedaron enlazados a la ficha que ya existía (antes eran error). Los otros ~120 grupos
  de repetidos del Excel no chocan por cédula, celular ni correo: se cargarían como fichas separadas; se resuelven antes
  del corte, marcándolos para la receta (`corte.py`), o se fusionan después con la lista de duplicados de Contactos.
- **El cliente n.º 1 del sistema anterior no está en `clientes.csv`:** 2 facturas del año y 4 documentos más no entran.
  Decisión de la dueña y el contador (¿son ventas a la propia empresa?).
- **Productos que no están en el catálogo:** sobre todo archivados y «Descuento» (168 líneas); esas líneas entran sin
  producto, con el nombre del archivo. Sin problema de contabilidad; sí hay que mirar los que siguen vendiéndose.
- **Cobertura del ensayo:** solo la primera tanda (~180 facturas de ~1,005). Los pagos, las facturas de proveedores y el
  cuadre contra el archivo y el libro **solo se ven con la carga de verdad**. Por eso la primera carga completa conviene
  hacerla donde se pueda mirar sin consecuencias (staging) o el día del corte.
- Los 10 pedidos de venta con mercancía por entregar no se cargan (se entregan o se rehacen a mano), y 15 facturas de
  proveedor en borrador necesitan el número de factura del proveedor antes de publicarse.

**Pendiente con el contador:** la equivalencia de cuentas (viejas → nuevas), qué hacer con los 41 cobros sin conciliar y
los 7 pagos sin aplicar, la revisión de las facturas raras de arriba y el balance de comprobación al día del corte, contra
el cual se firma el cuadre.

## Carga real en producción (2026-10-14)

Cargada una sola vez, por pasadas (cada una con «Revisar» antes de «Cargar»), con la exportación del 2026-10-13 de
Cowork y el Excel de repetidos marcado (51 fichas unidas). Nadie había vendido ni en el sistema anterior ni en el nuevo.
**No se vuelve a cargar**: los archivos ya están dentro. Solo cifras; los datos de personas quedan en Odoo.

| Pasada | Resultado |
|---|---|
| Clientes y proveedores | 971 fichas nuevas + 1 enlazada por el mismo RUC; 6 proveedores; 0 errores |
| Productos y existencias | 26 productos nuevos (21 con foto, publicados; 5 sin foto y 69 combos sin publicar); 106 con existencias; 0 errores |
| Precios de proveedor | 242 nuevos; 3 con precio 0 y 6 de productos archivados no se cargaron |
| Ventas y compras pendientes | 26 facturas de venta en borrador; 4 órdenes de compra por recibir; 16 facturas de proveedor en borrador |
| Facturas de clientes | 1,025 publicadas; total 158,706.48 contra 158,706.33 del archivo (redondeo del ITBMS) |
| Pagos | 1,166 |
| Facturas de proveedores | 14 publicadas; total 28,703.82 y saldo por pagar 23,247.06 = libro mayor |

**Lo que se aprendió**
- Un archivo en la casilla equivocada (las líneas de compras en la de ventas) se nota en «Revisar»: salían 242 líneas «sin su
  orden». Mirar el nombre que muestra cada casilla antes de pulsar.
- Una variante con varias medidas guarda el código en cada variante (`…-FULL`); las facturas buscan el código exacto. Se
  igualó el código a mano antes de cargar y se devuelve después (los enlaces van por el producto, no por el texto).
- 3 facturas de proveedor traían el número con el mes de una fecha contable dos meses posterior a la de la factura y Odoo las
  rechazó («la fecha no coincide con la secuencia»). Se cargaron conservando la fecha real y cambiando solo el número; el
  número viejo quedó en la referencia.

**Lo que sigue abierto (para el contador y para la dueña)**
- Saldos iniciales (bancos, caja, inventario, capital): el sistema anterior solo tiene facturas desde el 22 de julio, así que el
  balance general necesita un asiento de apertura. Ventas, ITBMS y cuentas por cobrar y por pagar ya salen completos.
- El libro mayor dice que los clientes deben 1,558.18 y las facturas abiertas suman 3,703.68: la diferencia son pagos sin aplicar
  a ninguna factura (los 7 conocidos y el cobro de 244.65 que quedó suelto cuando se borró en el sistema anterior la factura
  `INV/2026/00995`; su orden `S01156` volvió a estar pendiente). `INV/2026/00809` quedó en 0.00 y el archivo decía 77.01.
- 41 cobros sin conciliar con el banco (quedan en tránsito hasta importar el extracto).
- Documentos de la propia empresa (cliente n.º 1), fuera de la carga: 2 facturas y 4 pagos por 513.57.
- 13 ventas con mercancía por entregar (no se cargan): entregarlas o rehacerlas a mano; la lista con nombres se guardó fuera del
  repositorio. La línea de `S00295` quedó sin producto: se corrige a mano en el borrador.
- 15 facturas de proveedor en borrador necesitan el número de factura del proveedor; `P00029` sale 7 % más alta (ITBMS) y
  `P00006` ya tenía factura del proveedor.
- Conteo con el Escáner: 9 productos con existencia negativa (entraron en 0), 82 productos activos sin código y 5 filas de
  inventario sin código (64 unidades).
