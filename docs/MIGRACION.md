# Cargar los datos del sistema anterior (`dcasa_migracion`)

Pantalla de **Ajustes › Cargar datos del sistema anterior** (solo administradores). Carga, **una sola vez**, lo que
deja la receta de migración (Cowork, en la computadora de la dueña): clientes, proveedores, productos, existencias y
precios de proveedor.

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

**Todavía no entra** (se agrega a esta misma pantalla, un cargador por grupo; el formato de cada archivo lo define el
módulo, no Cowork): las **órdenes de venta abiertas** (entrega o factura pendiente), las **órdenes de compra abiertas**
(recepción o factura pendiente) y la **contabilidad** (facturas de clientes y de proveedores, pagos), esta última con su
propio cuadre contra el balance de comprobación del sistema viejo y la firma del contador.

**No entra, a propósito:** el historial de ventas ya cerradas, los movimientos viejos de inventario, la configuración del
sistema anterior y sus ~2,700 adjuntos (las fotos de productos ya están en el catálogo).

## Paso a paso (el día del corte)

1. Exportar de nuevo el sistema anterior y correr la receta (`LEEME_RECETA.md`): deja `clientes.csv`, `productos.csv` e
   `inventario.csv` (UTF-8, coma, punto decimal). No abrirlos con Excel y guardarlos: subirlos tal cual.
2. **Ajustes › Cargar datos del sistema anterior**: subir los archivos. Conviene hacerlo **por pasadas** (primero
   `clientes.csv` y `proveedores.csv`, después `productos.csv` con `inventario.csv`, y al final `precios_proveedor.csv`,
   que usa a los proveedores y a los productos): cada pasada es una sola petición y tarda menos. Con
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

## Qué falta: órdenes abiertas y contabilidad histórica

Las **órdenes de venta y de compra abiertas** se definen con la descripción que entregue Cowork (hay que decidir cómo
traerlas sin duplicar contabilidad ni mover el stock dos veces).

### Contabilidad histórica

Las facturas de clientes (1,006), las de proveedores (18) y los pagos (1,144) del sistema anterior **entran** en una segunda
etapa, con sus números originales y cada pago enlazado a su factura. Antes: el plan de cuentas, los diarios y los
impuestos del sistema anterior contra los de aquí, y el balance de comprobación al día del corte. Cuando termine la
carga, el total por cuenta de este sistema debe **cuadrar al centavo** con el del anterior, y el contador lo firma. Las
facturas viejas no deben reenviarse a la DGI ni dar puntos de Socios, y las facturas nuevas deben continuar la numeración.
