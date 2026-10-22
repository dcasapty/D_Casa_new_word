# Lector de códigos de barras (`dcasa_barras`)

El «Escáner de códigos de barras» de Odoo (`stock_barcode`) es **Enterprise**. Esto es lo que D'CASA necesita, hecho con
lo que sí trae Odoo Community. Responde a los issues #9, #11, #13 y #14 del repositorio: los tres últimos están
cerrados (construidos y en staging); #9, #10 y #12 siguen abiertos hasta probar los lectores con las etiquetas reales
y decidir cómo se imprimen.

## Qué hay

| Dónde | Qué hace | Quién |
|---|---|---|
| **Inventario › Escáner** | Escaneas (o escribes) un código y sale la foto, el nombre, la referencia, el precio «+ ITBMS», las existencias por ubicación y si está *disponible*, con *pocas* o *agotado*. | Quien usa Inventario (la Vendedora lo es) |
| **Escáner › Contar** | Escribes lo contado, ves la diferencia con lo que dice el sistema y confirmas. Se registra el ajuste de inventario de Odoo. Ahí mismo, Gerencia puede **cambiar el precio** (sin ITBMS, con confirmación «antes → nuevo»; queda anotado en el producto). | Gerencia |
| **Escáner › botón «Cámara»** | Lee el código con la cámara del celular, igual que la pistola (la primera vez el navegador pide permiso para usar la cámara). | Quien usa el Escáner |
| **Escáner › Asignar** | Escaneas una etiqueta numerada del rollo (`DC0001`…), eliges el producto y ese número queda como su código de barras. Se puede pasar a otro producto, reemplazar o quitar; el número viejo queda *retirado* y avisa si alguien lo escanea. | Gerencia |
| **Inventario › Configuración › Historial de etiquetas** | Quién asignó, pasó o retiró cada número y cuándo. No se edita ni se borra. | Gerencia |
| **Inventario › Configuración › Códigos de barras** | Llena el código de barras de los productos que no tienen, a partir de su referencia interna (alternativa a las etiquetas numeradas; ver más abajo). | Gerencia |
| **Escáner › QR de un documento** | Escaneas el QR de uso interno que lleva un documento impreso (pedido de compra, factura, cotización, nota de entrega) y se abre ese documento en el sistema. Ver «QR de los documentos» más abajo. | Quien tenga permiso para ver ese documento |
| **Inventario › Bodega** (y el acceso «Bodega» del Inicio) | Las entregas pendientes «Para despachar (envío)» y «Para retirar en tienda», pensado para tablet. Se abre una entrega tocándola o escaneando el QR de su nota, se marca lo que sale (también escaneando cada producto) y se valida; si falta algo, lo demás queda pendiente. Ver «Panel de Bodega» más abajo. | Quien usa Inventario (bodega, la Vendedora, Gerencia) |

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

## Cámara del celular

Junto a «Buscar» sale el botón **Cámara** (solo si el navegador deja usar la cámara; el sitio es HTTPS). Se enfoca el
código y sigue igual que con la pistola. Usa el lector de Odoo (`@web/core/barcode`): si el navegador no trae
`BarcodeDetector`, carga la librería ZXing de Odoo. La pistola sigue siendo lo más rápido para contar muchos productos.

## Cambiar el precio desde «Contar» (pedido de la dueña, 2026-10-16)

1. Escáner › **Contar**, escaneas el producto.
2. En **Precio nuevo, sin ITBMS** escribes el precio (solo números y punto: `399.99`) y pulsas **Revisar precio**.
3. Sale «Precio actual $X + ITBMS · Precio nuevo $Y + ITBMS». Solo al **Guardar precio** se cambia.

* Lo puede hacer **Gerencia**: la misma regla de precios de Productos (`dcasa_base/models/product.py`, administrador de
  Productos). La Vendedora no ve el campo y el servidor lo rechaza aunque alguien lo mande.
* Si mientras lo revisabas otra persona cambió el precio, no se guarda («cambió de X a Y»).
* Un producto con **variantes** (tamaños o colores) se cambia en Productos: su precio base es el de todas.
* Queda una nota en el producto: «Precio cambiado desde el Escáner por (quien): $X → $Y». Cambia para las cotizaciones
  y ventas nuevas y la tienda web; lo ya vendido no cambia.

## Contar

1. Escáner › **Contar**, escaneas el producto.
2. Eliges *dónde contaste* (bodega o tienda) y escribes la cantidad.
3. **Revisar** muestra «el sistema decía X, tú contaste Y, se ajusta ±Z». Solo al **Confirmar** se guarda.

* Usa el *Inventario físico* de Odoo: el ajuste queda en el historial de movimientos con el nombre «Conteo con lector (quien
  contó)» y el stock del producto (`dcasa_stock`, lo que dice Juan y lo que ordena Marketing) se actualiza solo.
* **Solo Gerencia ajusta existencias a mano**, también en Inventario › Inventario físico (desde el 2026-10-16 el modelo lo exige: la Vendedora recibe un aviso si intenta editar o aplicar un conteo). Validar entregas y recepciones no cambia.
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

## Etiquetas numeradas (el rollo del proveedor de etiquetas)

La forma pensada para D'CASA: el proveedor de etiquetas imprime un **rollo con códigos numerados** que todavía no son de
ningún producto. Cada etiqueta se pega en el mueble de exhibición (o en la caja) y el sistema aprende de quién es.

1. **Pegas** la etiqueta en el mueble.
2. **Escáner › Asignar**, escaneas la etiqueta. Si es nueva, dice *Sin producto*.
3. **Escribes el nombre o la referencia** del producto y lo eliges (se ve su foto para confirmar que es ese).
4. **Asignar etiqueta** (el botón, o Enter con el cuadro de arriba vacío). Desde ese momento, escanear esa etiqueta en
   **Consultar** o **Contar** saca ese producto.

Si en cualquier paso escaneas otra etiqueta, se toma como una etiqueta nueva: nada se asigna por error.

Si el mueble cambia: pegas otra etiqueta y la asignas al producto (o vuelves a escanear la vieja y eliges **Pasarla a otro
producto** / **Quitar la etiqueta**). La etiqueta que se deja de usar queda **retirada**: si alguien la escanea, el
sistema dice «la etiqueta DC0001 está retirada: era de «X»» en vez de «no existe».

Reglas:

* Solo **Gerencia** (administra Inventario y Productos: el código se escribe en el producto, con sus permisos).
* Un número es de un solo producto. **Pasarlo a otro** o **usar uno que estuvo retirado** pide confirmación; mientras no
  se confirma, no cambia nada. La confirmación vale **solo para lo que viste**: si otra persona pasó la etiqueta mientras
  mirabas la pantalla, no se hace nada y te vuelve a preguntar con lo nuevo.
* El número se guarda en **mayúsculas** y la búsqueda no distingue mayúsculas (un lector con las mayúsculas invertidas
  escribe `dc0001` y encuentra lo mismo).
* El número no puede traer espacios ni letras con tilde ni símbolos raros, ni ser de 64 caracteres o más.
* El código de un **empaque** de otro producto no puede ser una etiqueta.
* Cada cambio queda en **Inventario › Configuración › Historial de etiquetas** (número, qué pasó, producto, quién, cuándo),
  **venga de donde venga**: del Escáner, de la ficha del producto (si alguien borra o cambia el código a mano), de la
  asignación desde la referencia o de eliminar el producto. Ese historial no se edita ni se borra; es lo que permite
  decir «estuvo retirada».
* Un producto archivado sigue siendo el dueño de su etiqueta: reutilizarla pide confirmación, y escanearla en Consultar
  dice «es del producto X, que está archivado» (el mueble puede seguir en bodega con su etiqueta).
* La pestaña **Asignar** solo la ve Gerencia.

### Qué pedirle al proveedor de etiquetas

* **Code 128 o QR.** Las dos sirven: el lector las lee como teclado y manda el texto, y esta pantalla no se entera de cuál
  era. Si es Code 128, porque las referencias llevan letras y guiones (el formato de tienda, EAN, solo admite números). Si
  es **QR**: el lector tiene que ser **2D** (un lector solo de barras 1D no lee QR; confirmar en el manual que el QR esté
  activado y que mande Enter al final), y **el contenido del QR debe ser solo el número en texto** (`DC0001`), sin enlace
  ni datos extra: el precio, la foto y las existencias salen del sistema en el momento y una etiqueta impresa se
  desactualiza. Un QR tiene la ventaja de leerse aunque la etiqueta esté rayada o sucia (corrección de errores) y en poco
  espacio; con un número de 6 caracteres basta un QR chico, pero no más pequeño de unos 2 × 2 cm (dejando el borde blanco).
* **Un prefijo de letras y un número** (por ejemplo `DC0001` a `DC1000`): así no se confunde con ninguna referencia que sea
  un número suelto. Hoy hay 652 productos y cada medida (Twin, Full, Queen, King) es un producto aparte: pedir más de
  1,000, con números de sobra para etiquetas dañadas y productos nuevos.
* **El número escrito debajo de las barras**, para teclearlo si una etiqueta se daña.
* **Cada número dos veces** (una para el mueble de exhibición y otra para la caja en bodega): el sistema no tiene
  problema con que dos etiquetas digan lo mismo.
* Adhesivo que agarre bien en cartón y madera, y **10 etiquetas de prueba** para ensayar con los dos lectores antes de
  imprimir el rollo completo.
* No lleva precio: el precio sale del sistema («+ ITBMS») y una etiqueta impresa se desactualiza.

### Si se usa el rollo numerado, no apliques «Revisar productos»

La asignación a partir de la referencia (más abajo) escribe la **referencia** como código de barras en los productos que no
tienen ninguno. Con etiquetas numeradas no hace falta, y mezclarlas confunde: un producto con la referencia como código
tendría que cambiarse al pegar su etiqueta. Se puede seguir revisando el informe, pero no aplicarlo.

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
* **Qué código lleva cada producto**: decidido, un **número propio de D'CASA** en etiquetas del rollo (arriba). La
  asignación por referencia queda como alternativa, sin aplicar.
* **Cámara del celular** como lector dentro del Escáner: no está (los dos aparatos ya traen lector). Para los **QR de
  documentos** no hace falta: la cámara normal del teléfono los abre en el navegador (ver «QR de los documentos»).

## QR de los documentos (uso interno)

Decisión de la dueña: el QR de un documento es **para el equipo**, no para el cliente. Lo escaneas y se abre ese mismo
documento en el sistema. **No lleva ningún dato del cliente** (ni nombre, ni teléfono, ni montos): solo el tipo y el
número del documento.

**Qué contiene.** Una dirección corta y estable:

```
<dirección del sistema>/dcasa/doc/<TIPO>/<REFERENCIA>

FAC  factura y nota de crédito de cliente   …/dcasa/doc/FAC/INV/2026/00001
COT  cotización o pedido de venta           …/dcasa/doc/COT/S00007
COM  pedido de compra                       …/dcasa/doc/COM/P00012
ENT  entrega (albarán)                      …/dcasa/doc/ENT/WH/OUT/00005
```

La «dirección del sistema» es la de *Ajustes › Técnico › Parámetros del sistema › `web.base.url`*. Si algún día cambia
el dominio, los papeles impresos antes siguen apuntando al dominio viejo (la cámara del teléfono abre esa dirección);
el Escáner, en cambio, solo mira el tipo y el número, así que lee igual los QR de antes.

**Dónde se imprime.** Pequeño (unos 2 cm), plano, azul marino sobre blanco, con la nota «Uso interno». En la factura y
la cotización va **a la derecha de los textos de garantía, cambios y términos** (en la misma franja: no pide más alto
en la hoja); si la empresa no escribió esos textos, va al final de la hoja a la derecha. En la nota de entrega y el
pedido de compra, al final de la hoja a la derecha. No se mueve nada más (los textos de garantía solo se ensanchan un
poco menos). Con una factura de muchos renglones, que justo llena la hoja, el QR puede mandar esa franja a la página
siguiente: pasa con un renglón más o menos del límite.

| Documento | ¿Lleva QR? |
|---|---|
| Pedido de compra | **Siempre** (lo pidió la dueña; no toca la factura) |
| Factura y nota de crédito | Solo si la empresa enciende **«Mostrar el código QR en la factura y la cotización»** |
| Cotización y pedido de venta | Igual: solo con ese interruptor |
| Nota de entrega (también la del «Imprimir documentos») | Igual: solo con ese interruptor |
| Factura en borrador | Nunca (todavía no tiene número) |

El interruptor está en *Ajustes › Empresas › D'CASA Panamá › pestaña «Documentos D'CASA»* y viene **apagado**: apagado, la
factura, la cotización y la nota de entrega salen **exactamente como siempre** (hay un test que lo vigila). Detalle y
qué cambia al encenderlo: [CATALOGO.md](CATALOGO.md#código-qr-y-código-público-en-la-factura-y-la-cotización).

**Cómo se lee.**

* **Con el Escáner** (lector que escribe como teclado, o el Android con lector): se escanea igual que un producto y,
  si tienes permiso para ver ese documento, se abre. Si no, dice «No tienes permiso para ver esta factura…» y no
  muestra nada del documento; si el número no existe, «No encontramos ese documento». Funciona en *Consultar* y en
  *Contar*; en *Asignar* se rechaza con «Ese es el código QR de un documento, no una etiqueta de producto» (así un QR
  de documento nunca queda como código de barras de un producto). Lo que no es un documento (barras de producto,
  etiquetas `DC0001`, código público `DC-K7M4PX`) se escanea **como siempre**. Como una dirección lleva muchos
  símbolos (`:` `/` `.`) y un lector con el teclado en otro idioma los cambia (`/` sale `-`, `:` sale `Ñ`…), el Escáner
  reconoce el documento por lo que sí llega (las letras y los números: `dcasa`, `doc`, el tipo y el número del
  documento) y lo abre igual.
* **Con la cámara del teléfono** (la app normal de cámara): abre el navegador en esa dirección. Si no hay sesión, pide
  la clave y, al entrar, **vuelve al documento**. Con sesión y permiso, lo abre; sin permiso, una pantalla con «No tienes
  permiso» (403); si el número no existe, «No encontramos el documento» (404).

**Permisos.** Siempre los de la persona: el servidor comprueba que pueda leer ese documento (la vendedora ve sus propias
cotizaciones, no las de otra; quien no maneja compras no abre un pedido de compra). Un cliente con acceso al portal no
abre nada por esta ruta. Quien no puede ver un tipo de documento recibe el mismo aviso exista el número o no (no hay
cómo averiguar si un documento existe).

**Detalles técnicos** (para quien mantiene el sistema). El QR se genera con el generador estándar de Odoo (el de
`/report/barcode`, reportlab) y se **incrusta en el propio HTML del documento** (`data:image/png`): wkhtmltopdf no tiene
que pedir nada más al servidor, así que sale igual en el PDF, en la vista previa y en las pruebas. Nivel de corrección
«M» (aguanta un doblez o una mancha). La ruta es `dcasa_invoice/controllers/documento.py`; la lectura de la dirección y la
búsqueda con permisos, `dcasa_invoice/models/documento.py` y `documento_abrir.py` (los usa también el Escáner:
`dcasa_barras` depende de `dcasa_invoice`). El Worker del borde no bloquea `/dcasa/doc/*` y no lo guarda en caché (solo
guarda assets públicos). Este QR **no** es el de la factura electrónica de la DGI (`dcasa_fe_pa`, que no se toca) ni el
`/codigo/DC-K7M4PX` del producto para el cliente (ver [CATALOGO.md](CATALOGO.md)): son otras cosas.

## Panel de Bodega (pedido de la dueña, 2026-10-22)

> «Un solo panel que muestre las entregas pendientes por despachar o retirar; que en bodega puedan abrir muy fácilmente
> las órdenes de entrega, muy bien optimizado para una tablet; que abran la orden y fácilmente puedan validar la
> entrega, que funcione con el QR de la nota de entrega.»

**Dónde:** *Inventario › Bodega* (dirección `/odoo/bodega`; `/odoo/bodega/<id>` abre esa entrega) y el acceso
**Bodega** del Inicio (justo antes de Escáner, con cuántas entregas esperan). Lo ve quien usa Inventario: bodega, la
Vendedora (todas despachan) y Gerencia. Pensado primero para **tablet** (vertical y horizontal); sirve en celular y
computadora.

**La lista.** Las salidas a clientes que no están hechas ni canceladas (las mismas «Entregas pendientes» del Inicio,
sin las devoluciones a proveedores), de la más antigua a la más nueva. Cada tarjeta: número de la entrega, cliente,
pedido, fecha (*Prometida* si el pedido tiene «Fecha de entrega»; si no, *Programada*; en rojo si ya pasó), envío o
retiro, estado en palabras sencillas (*Lista para salir*, *Falta una parte*, *Esperando producto*), los productos con su
cantidad (los tres primeros y «y N más») y el botón grande **Abrir**. Nunca precios.

* **Envío o retiro.** Arriba: «Todas», «Para despachar (envío)», «Para retirar en tienda» y, si hay alguna, «Sin definir».
  Lo dice el **método de entrega** del pedido: el que tiene marcado **«Es retiro en la tienda»** (*Inventario ›
  Configuración › Métodos de envío*; el «Retiro en tienda (La Chorrera)» de la tienda web viene marcado) es retiro y
  cualquier otro es envío. Sin método, una línea de **flete** en el pedido la hace «envío». Si no hay ninguna de las dos
  cosas, **no se adivina**: sale «Sin definir» (la vendedora lo arregla poniendo el método de entrega en el pedido).
* **Estado.** «Listas para salir» (todo apartado en bodega) o «Esperando producto» (falta todo o una parte).
* **Solo pedidos con pago o abono** (decisión de la dueña, 2026-10-22: «solo pueden ver el pedido si pagaron o
  abonaron»). La lista muestra, y el panel abre y valida, solo las entregas cuyo pedido tiene al menos un **cobro de
  verdad** conciliado con su factura (las notas de crédito no cuentan) o un pago de la tienda web confirmado o
  autorizado. Las demás no salen; si escanean su QR, el panel dice en rojo **«Este pedido (S0…) todavía no tiene pago ni
  abono: no se entrega»**, y el servidor también se niega a abrirla o validarla. Si tiene abono y le falta una parte,
  la tarjeta lo dice (**Con abono: falta una parte**), sin montos. Una entrega que **no viene de un pedido** de venta
  tampoco se despacha aquí (la valida Gerencia en *Inventario › Entregas*). El **crédito autorizado por Gerencia** no
  está registrado en el sistema (A3 en [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md)): un pedido a crédito sin
  ningún abono no sale hasta que exista esa regla.
* **Buscar** por cliente, número de entrega, pedido o producto (sin tildes ni mayúsculas). Enter abre la entrega si
  queda una sola. Escanear el **código de un producto** deja solo las entregas que lo llevan.
* Se **actualiza sola** cada minuto (y al volver a la pantalla); el botón **Actualizar** lo hace ya.

**El QR de la nota de entrega.** Con el lector (escribe como teclado) o con el botón **Cámara** (el lector de Odoo, con
el arreglo del iPhone de `camara.js`): el QR de la nota abre **esa entrega** en el panel. También sirven el QR de la
**factura** o de la **cotización/pedido** (abren su entrega pendiente; si tiene varias, deja solo esas en la lista) y el
número de la entrega o del pedido escrito a mano. Los permisos son los del Escáner (`dcasa.documento`): quien no puede
ver facturas recibe «No tienes permiso…» y nada del documento. Una entrega ya hecha avisa «ya se entregó el …» y dónde
quedó lo que faltó. **Fuera del panel también** (decisión de la dueña, 2026-10-22): el QR de la nota leído con la
**cámara normal del teléfono** (`/dcasa/doc/ENT/…`) o con el **Escáner** abre la entrega en Bodega (`/odoo/bodega/<id>`)
para quien usa Inventario; quien no lo usa, una recepción, la factura y el pedido siguen abriendo su formulario de
Odoo.

**Abrir una entrega.** Cliente, teléfono (se toca para llamar), dirección, pedido, fecha, envío o retiro, la nota de la
entrega y la lista de productos con **foto**, código y cantidad pedida. Se marca lo que sale:

* con un toque (**Marcar** → **Sale**) si es una pieza; con **−** / **+** y **Todas** si son varias;
* **escaneando el producto** (código de barras, referencia, código público o empaque, igual que el Escáner): suma una
  pieza; si el producto **no es de esa entrega**, avisa con un pitido grave («no es de esta entrega»);
* **Marcar todo**, para quien ya revisó la mercancía a la vista.

Un producto que según el sistema no está en bodega lo dice («El sistema dice que no hay en bodega. Si lo tienes,
márcalo igual»): sale igual (como en Odoo) y la entrega queda con una nota para que Gerencia cuente ese producto.

**Validar entrega** (abajo, en la barra azul, siempre a la vista):

* Todo marcado → se valida. Aviso verde en la lista: «Listo: WH/OUT/00005 quedó entregada completa», con **Imprimir nota
  de entrega**.
* Falta algo → pregunta en sencillo **«¿Entregar solo lo marcado?»** con lo que falta y dos botones: **Sí, entregar solo
  lo marcado** (lo demás queda en una **entrega pendiente** nueva de Odoo, que sale en la lista como «Resto de …») o
  **Volver**.
* Nada marcado → «Marca lo que sale antes de validar».
* Lo que Odoo pediría con asistentes (crear la entrega pendiente, el aviso de los SMS) lo contesta el panel; si un
  producto lleva **número de serie o de lote** que el sistema no apartó, o la entrega pide otro paso, dice en sencillo que
  la valide Gerencia desde *Inventario › Entregas*. D'CASA no usa números de serie hoy.
* Queda **quién la validó**: Odoo valida con los permisos de la persona (sin `sudo`) y la entrega lleva la nota
  «Despachada desde el panel de Bodega por …», con lo que faltó y dónde quedó.
* La **nota de entrega** se imprime desde la entrega abierta o desde el aviso de éxito (la misma de Inventario).

**Tablet sin lector.** El cuadro donde escribe el lector tiene el foco siempre, pero en una pantalla táctil **no saca
el teclado** hasta que lo tocas para escribir (`inputmode="none"`).

**Brian:** `entregas_por_despachar` (ver [BRIAN.md](BRIAN.md)). **Guía:** «Despachar una entrega en bodega».

**Detalles técnicos.** `dcasa_barras/models/bodega.py` (`dcasa.bodega`: `pendientes`, `abrir`, `leer`, `validar`;
`delivery.carrier.dcasa_es_retiro`), `models/tablero.py` (el acceso del Inicio), `static/src/js/bodega.js`,
`xml/bodega.xml`, `scss/bodega.scss`. Validar marca cada renglón (`quantity` y `picked`) y llama a `button_validate`
con `skip_backorder` (la pregunta ya la contestó la persona) y `skip_sms`; si Odoo devuelve otro asistente, no se hace
nada. Pruebas: `tests/test_bodega.py` (servidor) y `tests/test_bodega_ui.py` (navegador a tamaño tablet, tablet
acostada, celular y computadora).

## Seguridad

Todo lo que lee o escribe el Escáner lo comprueba el servidor (no solo el menú): consultar pide ser usuario de Inventario;
contar y asignar piden ser administrador de Inventario (Gerencia). El lector **nunca** muestra el costo del producto.
Asignar etiquetas pide además administrar Productos (el código se escribe en el producto). Los productos se escriben
con los permisos de la persona; el único `sudo()` es el que anota el historial de etiquetas, después de comprobar el
permiso. Abrir un documento desde su QR comprueba, también en el servidor, que quien escanea pueda leerlo (y los
métodos que lo hacen son privados: no se llaman por RPC). El panel de Bodega exige ser usuario de Inventario en cada
método y valida con los permisos de la persona. Los permisos de Odoo siguen mandando. La lista de métodos
públicos está en `addons/dcasa_base/tests/test_superficie_rpc.py`.
