# Lector de códigos de barras (`dcasa_barras`)

El «Escáner de códigos de barras» de Odoo (`stock_barcode`) es **Enterprise**. Esto es lo que D'CASA necesita, hecho con
lo que sí trae Odoo Community. Responde a los issues #9, #11, #13 y #14 del repositorio.

## Qué hay

| Dónde | Qué hace | Quién |
|---|---|---|
| **Inventario › Escáner** | Escaneas (o escribes) un código y sale la foto, el nombre, la referencia, el precio «+ ITBMS», las existencias por ubicación y si está *disponible*, con *pocas* o *agotado*. | Quien usa Inventario (la Vendedora lo es) |
| **Escáner › Contar** | Escribes lo contado, ves la diferencia con lo que dice el sistema y confirmas. Se registra el ajuste de inventario de Odoo. | Gerencia |
| **Inventario › Configuración › Códigos de barras** | Llena el código de barras de los productos que no tienen, a partir de su referencia interna. | Gerencia |

## Los lectores

Los dos aparatos de la compra (el escáner inalámbrico Tera y el Android con lector Rayoungtek) **escriben el código
como si fuera un teclado** y terminan con Enter. La pantalla del Escáner tiene siempre el cuadro de arriba con el foco:
se apunta, se dispara y sale el producto. También sirve escribir el código a mano y pulsar Buscar, que es como se prueba
sin aparato.

* Si el lector escribe símbolos distintos (guion por guion bajo, etc.) porque su teclado está en otro idioma, **igual
  encuentra el producto**: la búsqueda tolera símbolos y mayúsculas (`xht022_t_w` = `XHT022-T-W`).
* Si el código no existe, avisa y ofrece productos parecidos por nombre.
* Si el producto salió de un código **parecido** (no igual: se ignoraron símbolos o mayúsculas), lo dice y **no deja
  contar** hasta pulsar «Sí, es este»: así no se ajusta el producto equivocado.
* Si el lector dispara varios códigos seguidos, **gana el último** y el cuadro queda listo para el siguiente.
* Si dos productos tienen el mismo código o referencia, muestra los dos para elegir.

## Qué se busca

En este orden: código de barras · referencia interna (hoy **ningún** producto tiene código de barras pero casi todos
tienen referencia, así que ya sirve desde el primer día) · código del empaque · el mismo código sin símbolos.

## Contar

1. Escáner › **Contar**, escaneas el producto.
2. Eliges *dónde contaste* (bodega o tienda) y escribes la cantidad.
3. **Revisar** muestra «el sistema decía X, tú contaste Y, se ajusta ±Z». Solo al **Confirmar** se guarda.

* Usa el *Inventario físico* de Odoo: el ajuste queda en el historial de movimientos con el nombre «Conteo con lector (quien
  contó)» y el stock del producto (`dcasa_stock`, lo que dice Juan y lo que ordena Marketing) se actualiza solo.
* Si coincide con lo que decía el sistema, no se crea ningún movimiento.
* **Si mientras contabas el sistema cambió** (una venta, una entrada), no se guarda: dice «cambió de X a Y» y hay que
  escanear y contar de nuevo. Contar sobre un número viejo dejaría el inventario mal.
* La cantidad se escribe **solo con números y punto** (nada de comas: «1,200» se leería como 1.2). Si el producto se
  cuenta en unidades enteras, no admite decimales.
* La confirmación dice **en qué ubicación** se contó.
* Si el producto tiene varias líneas de existencia en la misma ubicación (por dueño, paquete o repetidas), no se cuenta
  aquí: Odoo ajustaría solo una y el total no quedaría en lo contado (Inventario › Inventario físico).
* Los productos que se controlan por **lote o serie** y los que **no controlan inventario** no se cuentan aquí
  (se cuentan en Inventario › Inventario físico).
* Una cantidad que no es un número, es negativa o pasa de 100,000 se rechaza (es un error de dedo).

## Asignar los códigos de barras

Hoy 0 de 652 productos tienen código de barras. Sin código el lector solo encuentra por referencia.
Inventario › Configuración › **Códigos de barras** › Nuevo:

1. **Revisar productos**: muestra qué se haría, sin cambiar nada.
2. **Asignar los códigos**: escribe la referencia interna como código de barras (Code 128 la admite).
3. **Deshacer**: quita lo asignado, solo en los productos que siguen con ese mismo código.

Reglas: **nunca pisa un código que ya existe**; una referencia repetida en dos productos, o igual al código que ya tiene
otro, **no se asigna** (se informa); sin referencia se informa (hay que completarla); solo caracteres imprimibles sin
espacios; las medidas (Twin, Full, Queen, King) son variantes con su propia referencia y quedan con códigos distintos;
se puede repetir sin miedo.

## Qué falta decidir (los issues #9, #12 y #14)

* **Qué se hace primero con los lectores**: contar (ya está), recibir mercancía o cobrar en mostrador. Recibir y cobrar
  con lector **no están hechos**: Ventas e Inventario ya encuentran un producto por su código en el buscador de
  productos (un lector tipo teclado funciona ahí).
* **Etiquetas** (#12): Odoo trae «Imprimir etiquetas» en la ficha del producto. Falta decidir el tamaño y la
  impresora (¿térmica o pegatinas en hoja normal?) antes de hacer una etiqueta con la marca; **sin precio inventado**
  (el precio sale del sistema, con «+ ITBMS»).
* **Qué código lleva cada producto**: hoy se usa la referencia del proveedor tal cual. Si se prefiere un número propio
  de D'CASA, se cambia la regla de asignación.
* **Cámara del celular** como lector: no está (los dos aparatos ya traen lector).

## Seguridad

Todo lo que lee o escribe el Escáner lo comprueba el servidor (no solo el menú): consultar pide ser usuario de Inventario;
contar y asignar piden ser administrador de Inventario (Gerencia). El lector **nunca** muestra el costo del producto.
No usa `sudo()`: los permisos de Odoo siguen mandando. La lista de métodos públicos está en
`addons/dcasa_base/tests/test_superficie_rpc.py`.
