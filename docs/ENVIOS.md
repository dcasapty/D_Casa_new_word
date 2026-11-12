# Envíos: la calculadora (`dcasa_envios`)

Pedido de la dueña (2026-11-06): «vamos a poner este sistema en el menú donde están los envíos [el HTML de la propuesta
del 4 nov] … recuerda el problema del scroll … y refactoriza bien este código para que el día de mañana, si tenemos
nuestra propia flota de envíos, el cliente pueda calcular cuánto se le cobrará por envío desde la página web».

## En palabras sencillas

- **Envíos › Calculadora** (todo el equipo): se escribe a dónde va el envío como lo dice el cliente («Villa Lucre»,
  «urb. Costa Verde», «cerca del hospital de Chorrera», «sanmiguelito», con errores de dedo) y sale cada lugar con su
  **precio**, los km desde la tienda, el **desglose**, «**Copiar el precio**» (el texto listo para mandarle al cliente)
  y «**Ver la ruta en Google Maps**» desde la tienda. Filtros por tipo (barrios, edificios y PH, lugares conocidos,
  corregimientos) y por distrito o provincia. Si no lo encuentra: «¿Quisiste decir…?» y «**Agregar este lugar**» (queda
  el nombre de quien lo agregó y la fecha). Abajo, «**Calcular por kilómetros**» (con casilla de peaje) para una
  dirección exacta medida en Google Maps, y la **tabla por tramos**.
- Mientras Gerencia no apruebe la tarifa, arriba dice **«Tarifa en revisión: estos precios todavía no se usan con
  clientes»**. Brian dice lo mismo.
- **Envíos › Lugares** (todo el equipo puede verla; solo Gerencia edita o archiva): la lista completa con el precio de
  hoy. Se exporta a Excel con «Exportar» de Odoo (columna «Precio del envío»), para quien tiene el permiso «Exportar»
  de Odoo (hoy los administradores; se le da a una persona en su ficha de usuario).
- **Envíos › Tarifa** (Gerencia y administradores): el mínimo, los dos precios de referencia («a A km cuesta $X» y «a
  B km cuesta $Y»), el redondeo, «cotizar aparte desde», los **cargos aparte** (viático, honorarios, peaje u otros),
  **subir o bajar todo en %** (±5 % con un toque), **Aprobar la tarifa** (queda quién y cuándo), el historial de cada
  cambio y «**Cargar lugares y tarifa desde el archivo**».
- La pantalla **baja con la rueda y con el dedo** y en el celular deja 16 px de margen, sin scroll de lado.
- **Enlace para choferes** (Envíos › Tarifa, abajo; Gerencia y administradores): un solo enlace para todos los
  choferes, sin usuario ni clave. Buscan el lugar y ven **solo** el nombre, la zona, el precio **desde D'CASA** y la
  ruta en Google Maps; nunca los km ni la tabla. «Usar mi ubicación» viene **apagado** y solo Gerencia lo enciende.
  Ver [Enlace para choferes](#enlace-para-choferes).
- **Los datos no están en el repositorio** (es público y la dueña no dio su «sí» para subir la matriz ni los precios):
  Gerencia sube el archivo.

## Cargar los datos

1. Envíos › **Tarifa** › «**Cargar lugares y tarifa desde el archivo**» (o, si la calculadora está vacía, el botón que
   sale ahí mismo para Gerencia).
2. Subir el mismo **`envios-dcasa.html`** de la propuesta (o un JSON `{"lugares": [...], "ajustes": {...},
   "agregados": [...]}`; también sirve solo la lista de lugares). Se leen sus tres bloques `<script
   type="application/json">`: `lugares`, `ajustes` (la tarifa) y `agregados-datos` (lo que se agregó a mano en el HTML).
3. Elegir si se cargan los lugares, la tarifa o los dos, y tocar **Cargar**. Al terminar sale un resumen (y queda en el
   historial de la tarifa): nuevos, actualizados, sin cambios, archivados, respetados y omitidos con su motivo.

Volver a cargar es seguro:

- **No duplica.** Cada lugar del archivo tiene una llave: nombre + tipo + distrito + corregimiento, sin tildes ni
  mayúsculas. Si dos lugares distintos comparten la llave (el archivo real tiene 140 casos, p. ej. dos «El Cigual» en
  Los Díaz), se emparejan por sus coordenadas.
- **No toca lo de Odoo:** ni los lugares que el equipo agregó en Odoo, ni los del archivo que Gerencia cambió o archivó
  en Odoo (quedan marcados «Cambiado en Odoo»; para que el archivo vuelva a mandar en uno, su ficha tiene «Que mande el
  archivo otra vez»).
- **Archiva** (no borra) los que ya no vienen en el archivo; si vuelven, vuelven a la lista.
- **La tarifa** del archivo reemplaza a la de Odoo solo si se marca. Si cambia algo, vuelve a revisión. El «aprobada»
  del archivo no cuenta: se aprueba en Odoo.
- Si la tarifa del archivo trae un número que no sirve, no se cambia nada (ni los lugares).
- Medido con el archivo real (11 299 lugares): la primera carga tarda unos 2 s y volver a cargarlo, menos de 1 s.

## La fórmula (`motor/tarifa.py`)

Se define con tres precios que Gerencia conoce: el **mínimo** y dos puntos, «a A km cuesta $X» y «a B km cuesta $Y»:

```
por_km = (Y − X) / (B − A)          salida = X − A × por_km          f = 1 + ajuste % / 100
base(km) = máx( redondear(mínimo × f), redondear( máx(mínimo, salida + por_km × km) × f ) )
total = base + cargos aparte
```

- `redondear` lleva al múltiplo de $1, $5 o $10, hacia arriba o al más cercano; «No redondear» deja los centavos.
- Cargos aparte, cada uno con su forma: fijo por viaje, por cada km, fijo si el viaje llega a cierto km, por km después
  de cierto km, o solo si la ruta pasa por peaje. Cuentan si están marcados «Se cobra» y el monto es mayor que cero;
  con «Sube con el %», también los mueve el ajuste.
- Sin precio (se **cotiza aparte**): más lejos que «cotizar aparte desde», sin carretera, no encontrado o sin medir.
  Con lancha sí tiene precio (y la etiqueta «+ lancha»).
- Nada de cifras de fábrica: una tarifa nueva nace vacía (sin precios) hasta que se carga el archivo o se escriben.

## El buscador (`motor/buscador.py`)

El mismo del HTML: sin tildes ni mayúsculas, abreviaturas («urb.», «res.», «bda.», «hosp», «sanmi»), palabras que
sobran («cuánto cuesta», «llevar», «cerca», «hola»), errores de dedo (Damerau-Levenshtein), nombres escritos juntos o
separados distinto, sinónimos de los tipos de lugar («mall», «super», «policlínica», «metro») y de las zonas
(«chorrera», «la ciudad», «oeste»). Pesa más el nombre que el tipo de lugar y este más que la zona; buscar un distrito o
una provincia trae primero sus corregimientos; a igual puntaje sale el más cercano. Sin resultados, «¿Quisiste
decir…?» por trigramas.

El índice se arma una vez por base de datos y por proceso, en memoria (unos 30 MB y menos de medio segundo con los
11 299 lugares), y se vuelve a armar cuando cambia el parámetro `dcasa_envios.version_lugares`, que sube (con un valor
al azar, no un contador) en cada alta, cambio o baja de un lugar o de la tarifa. Funciona con varios procesos: cada uno
compara su versión con la de la base en cada búsqueda. Buscar no recorre los 11 000 lugares, solo los que comparten
alguna palabra (el resultado es el mismo); con el índice armado, una búsqueda tarda de 5 a 70 ms.

## Una sola fuente de verdad: el motor

`addons/dcasa_envios/motor/` es Python puro, **sin imports de Odoo**: la fórmula (`tarifa.py`), el buscador
(`buscador.py`), lo que se muestra de cada lugar (`tarjeta.py`: chips, zona, precio, desglose, texto para el cliente y
la ruta en Google Maps), los redondeos de JavaScript (`texto.py`) y la lectura del archivo (`archivo.py`). Lo usan la
pantalla (por RPC: no repite la fórmula en JavaScript), Brian (`cotizar_envio`) y, mañana, la web y Juan.

### Paridad con el HTML

El motor es un puerto fiel: mismos pesos, mismo orden de las operaciones y los mismos redondeos de JavaScript
(`Math.round`, `toFixed`, `toLocaleString('es-PA')`, la suma de izquierda a derecha).

- `scripts/envios/paridad.mjs` saca el JavaScript del propio HTML y lo corre en node sobre los datos; escribe los
  esperados (los primeros 10 lugares de cada búsqueda con su tarjeta, las sugerencias, una tabla de km → precio con 8
  tarifas distintas, los tramos y los textos de la regla).
- `scripts/envios/comparar.py` compara con el motor y da el porcentaje.
- En el repositorio solo va un **fixture sintético** (`addons/dcasa_envios/tests/datos/fixture_envios.json`: 39 lugares
  inventados, precios de juguete) con sus esperados sacados del JavaScript en node; `tests/test_motor.py` los compara
  sin base de datos. Para regenerarlos (hace falta el HTML de la dueña, que no está en el repositorio):

```
node scripts/envios/paridad.mjs envios-dcasa.html addons/dcasa_envios/tests/datos/consultas_motor.json \
     addons/dcasa_envios/tests/datos/esperados_motor.json addons/dcasa_envios/tests/datos/fixture_envios.json
```

Resultado el 2026-11-06 con los **datos reales** (en local, sin subirlos): 945 de 946 comparaciones iguales (99.9 %): 54
de 55 búsquedas (con sus 427 tarjetas), 448 precios, 8 tablas de tramos y 8 textos de la regla. La única diferencia es
a propósito: buscar «constructor» rompía el HTML (lee `ABREV['constructor']`, que en JavaScript es una función del
prototipo, y falla); el motor busca normal. Con el fixture: 486 de 486.

## El punto de entrada para la web (mañana)

Datos puros, iguales para cualquier usuario (no dependen de las reglas de quien pregunta):

```python
Lugar = env['dcasa.envio.lugar'].sudo()          # la web llamará con sudo; el equipo, como sí mismo
Lugar.buscar_para_cotizar('villa lucre', tipo=None, distrito=None, limite=20)
# {'texto', 'total', 'resultados': [{id, nombre, tipo, zona, chips, km, km_txt, con_precio, base, extras,
#   total, total_txt, desglose, texto_cliente, url_mapa, dist, prov, corr, cat, ...}], 'sugerencias': [{id, nombre}],
#   'tarifa': {configurada, aprobada, aviso}}

Tarifa = env['dcasa.envio.tarifa'].sudo()
Tarifa.cotizar_lugar(lugar)       # un registro, un id o un dict con la forma del HTML
Tarifa.cotizar_km(34.1, peaje=True)
# {'con_precio', 'km', 'base', 'extras': [{nombre, monto}], 'total', 'total_txt', 'desglose', 'tarifa', ...}
```

Sin `sudo` los puede llamar quien ve los lugares (todo el equipo); un usuario del portal recibe «acceso denegado».

### Cómo se encendería en el sitio (NO está hecho)

Todavía **no hay ninguna ruta pública para clientes** ni nada en el sitio (sería superficie de abuso). La única ruta
pública de envíos es el [enlace para choferes](#enlace-para-choferes), que exige su secreto. El día que D'CASA tenga su
flota y Gerencia lo pida:

1. **Interruptor apagado de fábrica:** un parámetro (p. ej. `dcasa_envios.web_activa`, en Ajustes del sitio, solo
   Gerencia) que por defecto es «no». Apagado, la ruta responde 404.
2. **Solo con la tarifa aprobada:** si `tarifa.aprobada` es falso, la ruta no da precios (responde «escríbenos por
   WhatsApp»), aunque el interruptor esté encendido. Un cambio de precios la devuelve a revisión y la web deja de
   cotizar sola.
3. **La ruta:** `POST /envios/cotizar` (JSON, `auth='public'`, con CSRF del sitio), que recibe `texto` (máx. 120
   letras) o `km`, y devuelve solo los primeros 5 lugares con su `total_txt`, `zona` y `texto_cliente` (sin ids ni
   coordenadas). Por dentro: `buscar_para_cotizar(...)` con `sudo()`.
4. **Límite de peticiones:** en el borde (`edge/`, Worker de Cloudflare) y en Odoo, p. ej. 20 por minuto por IP, con
   Turnstile si se pasa; caché corta de respuestas iguales.
5. **Atribución:** donde se muestren resultados, «Datos de mapas © colaboradores de OpenStreetMap (ODbL) y GeoNames
   (CC BY 4.0)» (los barrios, edificios y lugares conocidos salieron de ahí).
6. **CTA único:** al lado del precio, «Escríbenos por WhatsApp» (+507 6026-1919), como manda la marca.
7. Capturas a la dueña, pruebas (incluida la del límite) y su «sí» antes de staging.

**Juan** tampoco cotiza todavía: espera a que Gerencia apruebe la tarifa. Cuando se encienda, usaría las mismas dos
funciones (y diría «en revisión» si no está aprobada, como Brian).

## Enlace para choferes

Pedido de la dueña (2026-11-09): «generarle un link de calculadora a los choferes … que no vean la tabla de
kilometraje, solamente busquen el lugar y confirmen si ese es el precio, o vean el precio y la dirección en Google Maps
… que la persona desde donde está dé clic y se ponga su ubicación y a partir de ahí se calcule». Decidido: **un solo
enlace secreto para todos** (sin usuario de Odoo) y «Usar mi ubicación» = **el lugar de la tabla más cercano** por sus
coordenadas (gratis, sin API de mapas).

Después (2026-11-09): «quiero que la ubicación por defecto sea nuestra ubicación de D'CASA … por defecto inamovible,
que solamente ellos puedan calcular desde D'CASA hasta el punto … Y si nosotros queremos que ellos desde cualquier
punto de su ubicación puedan medir, que nosotros lo decidamos». Por eso **«Usar mi ubicación» viene apagado** y solo
Gerencia lo enciende (Envíos › Tarifa › «Permitir "Usar mi ubicación"»). El precio siempre es desde la tienda.

### Lo que ve el chofer

- Arriba (en azul): «¿Cuánto cuesta el envío?», la caja **«Busca el barrio, edificio o lugar»** (el mismo buscador de
  la calculadora: sin tildes, abreviaturas, errores de dedo) y la línea «El precio es desde D'CASA hasta el lugar que
  busques». Solo si Gerencia lo permitió: el botón amarillo **«Usar mi ubicación»**, con la línea «Tu ubicación solo se
  usa para buscar el lugar más cercano; no se guarda» (apagado, el botón no sale y `…/cerca` responde 404).
- Cada lugar (hasta 8): el **nombre**, la **zona** («corregimiento · distrito»), el **precio** (el mismo `total_txt` de la
  calculadora, p. ej. «$15»; con lancha, «$70 + lancha») y el botón **«Ver en Google Maps»** (la ruta en carro desde la
  tienda, como la calculadora). Sin resultados: «No encontramos…» y «¿Quisiste decir…?».
- **Sin precio** cuando no toca: si la tarifa no está aprobada, ningún lugar trae precio y arriba dice **«Tarifa en
  revisión: confirma el precio con la tienda»** (el aviso sigue al servidor en cada búsqueda); lo que se cotiza aparte
  (lejos, sin carretera, sin medir) dice **«Se cotiza aparte: confirma con la tienda»**.
- **«Usar mi ubicación»** (solo encendido por Gerencia): el navegador pide permiso; con él, los **3 lugares de la tabla más cercanos a no más de
  3 km**, con su distancia **en metros** («a 300 m de ti»), su precio y la ruta. Si no hay ninguno: «No hay un lugar de
  la tabla cerca de ti: búscalo por nombre o confirma con la tienda». Sin permiso, sin GPS o si tarda, lo dice en
  palabras sencillas y sugiere buscar por nombre.
- **Nunca** ve en la página: los km, la tabla por tramos, el desglose, la fórmula, «Calcular por kilómetros»,
  «Agregar este lugar», ni ids. En la página no aparece la palabra «km». (Ojo: la ruta de «Ver en Google Maps» lleva
  las coordenadas del lugar y Google Maps muestra los km por carretera; ver «Lo que no se puede impedir» abajo.)
- Una página sola (sin el sitio ni el panel), para el celular, con la marca (azul, amarillo solo sobre azul, Anton /
  Oswald / Inter, plana). **Baja con scroll** (el documento entero, sin `overflow: hidden`): probado con el dedo y la
  rueda de verdad.

### Encenderlo, copiarlo y cambiarlo (Gerencia)

Envíos › **Tarifa**, sección **«Enlace para choferes»** (solo Gerencia y administradores la ven):

1. **Encendido** (apagado de fábrica). Encenderlo la primera vez crea el enlace.
2. **Permitir «Usar mi ubicación»** (apagado de fábrica): apagado, los choferes solo buscan el lugar y ven el precio
   desde D'CASA; encendido, también pueden ver el lugar de la tabla más cercano a donde están.
3. **Enlace para choferes**: la dirección completa con su botón de copiar, para mandarla por WhatsApp a los choferes.
4. **Búsquedas de hoy**: cuántas lleva el enlace hoy, de un tope de 1 500 por día (se cuenta desde que arrancó el
   servidor). Al llegar al tope, el enlace responde «llegó a su límite de hoy» hasta el día siguiente y a quien lo creó
   le llega una nota: es mucho más de lo que buscan los choferes, así que puede que el enlace se haya filtrado.
5. **«Crear un enlace nuevo»**: el anterior deja de funcionar al instante (por ejemplo, si se perdió un teléfono, alguien
   dejó de trabajar con la tienda o llegó la nota del tope). Hay que mandarles el nuevo; empieza de 0 búsquedas.

Queda en el historial de la tarifa quién lo encendió o apagó, quién creó cada enlace y cuándo (nunca el secreto: el
historial lo lee todo el equipo). En la Guía: «Darle a los choferes el enlace de la calculadora».

### Seguridad

- **El secreto es la llave:** `secrets.token_urlsafe(24)` (192 bits al azar) en un campo de la tarifa que solo leen
  Gerencia y los administradores (`groups`), también por RPC; `write` ignora el secreto, quién y cuándo si llegan en los
  valores, y también `create`; quien no puede escribir en la tarifa recibe «sin permiso» antes de tocar nada (ni la
  versión del buscador). Se compara en tiempo constante (`hmac.compare_digest`).
- **Rutas** (`controllers/choferes.py`, `auth='public'`, sin sesión: `save_session=False`):
  `GET /envios/choferes/<enlace>` (la página), `POST …/buscar` `{"texto"}` (hasta 60 letras y 6 palabras) y
  `POST …/cerca` `{"lat", "lon"}` (números dentro de Panamá con margen; 404 si Gerencia no permitió la ubicación).
  **Apagado o con otro secreto, las tres responden el mismo 404** de texto plano. Sin CSRF porque el secreto autentica
  (no hay cookie que otra página pueda usar). Cuerpo de a lo sumo 2 KB (`max_content_length`: más grande, 413); un
  JSON roto, anidado mil veces o con un número gigante es un 400, nunca un error del servidor.
- **Solo lo que ve el chofer:** `motor/choferes.py` arma una lista blanca (`nombre`, `zona`, `precio`, `aviso`, `mapa`
  y, cerca, `distancia`). Los lugares se leen con `sudo()` por los métodos privados `_choferes_buscar` y
  `_choferes_cerca` (no se llaman por RPC) **después** de comprobar el enlace; el ACL del portal y del público no cambió.
- **Límites** (en la memoria del proceso de Odoo, como el de Brian; se reinician si el servidor se reinicia):
  60 peticiones por minuto por IP entre las tres rutas (una IPv6 cuenta por su red /64); 300 por minuto entre todas las
  IP (cuenta solo a quien tiene el enlace: sin él nadie se lo gasta a los choferes); **a lo sumo 2 búsquedas a la vez**
  (la tercera recibe «ocupada» al instante, así nadie con el enlace frena el resto de Odoo, que en producción es un
  solo proceso); y **1 500 búsquedas por día** por enlace (ver arriba). Después, 429 con `Retry-After`. Búsqueda: a lo
  sumo 8 lugares; cerca, 3.
- **Nada se guarda ni se indexa:** `Cache-Control: no-store`, `X-Robots-Tag: noindex, nofollow`,
  `Referrer-Policy: no-referrer` (Google Maps no recibe el enlace al tocar «Ver en Google Maps») y CSP con nonce
  (`default-src 'none'`). El borde (`edge/src/routing.ts`) nunca guarda `/envios/choferes/` en caché y escribe
  `/envios/choferes/:token` en su registro (también con idioma delante, `/es/envios/…`, o con letras codificadas). El
  registro de Odoo no guarda las peticiones en producción (`werkzeug` en WARNING, `docker/entrypoint.sh`). La
  ubicación del chofer no se guarda en ningún lado. **Los registros propios de Cloudflare** (Workers Logs, encendidos
  en `edge/wrangler.jsonc`) sí guardan la dirección completa de cada petición, con el secreto, durante su retención:
  los ve solo quien entra al panel de Cloudflare de D'CASA (la dueña y quien ella autorice).
- **Quien tenga el enlace puede abrirlo** (es como una llave compartida): por eso se puede apagar y cambiar en un toque.

#### Lo que no se puede impedir (revisión de seguridad, 2026-11-09)

Quien tenga el enlace ve el precio de cada lugar que busque, y «Ver en Google Maps» lleva las coordenadas del lugar y de
la tienda: Google Maps le muestra los km por carretera. Con mucha paciencia, alguien con el enlace podría ir copiando
lugares y precios y, de ahí, adivinar la fórmula. Una prueba con el índice real: copiar la mitad de los lugares pide
unas 3 900 búsquedas. Con el tope de 1 500 por día eso tarda varios días, y el primer día ya le llega la nota a
Gerencia, que lo corta con «Crear un enlace nuevo». Es lo que se paga por darles el precio sin usuario: el enlace se
manda solo a choferes de confianza.


| | Equipo (vendedora, Caja…) | Gerencia | Administrador |
|---|:---:|:---:|:---:|
| Usar la calculadora, ver la lista de lugares, cotizar por km | Sí | Sí | Sí |
| Agregar un lugar que falta (barrio, edificio o PH, lugar conocido; queda su nombre) | Sí | Sí (también corregimientos) | Sí |
| Editar o archivar un lugar | No | Sí | Sí |
| Borrar un lugar | No | No (se archiva) | Sí |
| Ver, cambiar y aprobar la tarifa; cargar el archivo | No | Sí | Sí |
| Exportar la lista a Excel | Con el permiso «Exportar» de Odoo | Con el permiso «Exportar» | Sí |
| Ver, encender, copiar y cambiar el enlace para choferes | No | Sí | Sí |

El servidor lo exige en cada llamada (no solo el menú): `_exigir_gerencia`, los permisos del modelo y, al agregar un
lugar, solo los campos que la persona puede escribir (el origen, quién lo agregó y cuándo los pone el servidor). «Quién
aprobó» lo pone siempre el servidor, aunque alguien mande otra cosa por RPC. Los métodos públicos están en la lista
blanca de `dcasa_base/tests/test_superficie_rpc.py`.

## Brian

`cotizar_envio(lugar? | km? + peaje?, distrito?, limite?)` (lectura, todo el equipo): busca el lugar como lo dice el
cliente o recibe los km; devuelve el precio con su desglose y el texto para el cliente, y dice «en revisión: estos
precios todavía no se usan con clientes» mientras Gerencia no apruebe. Ver [BRIAN.md](BRIAN.md).

## Pruebas

`addons/dcasa_envios/tests/`: el motor sin base de datos (paridad con el HTML y los redondeos de JavaScript), la carga
del archivo (idempotente, respeta lo de Odoo, la tarifa vuelve a revisión), los permisos (también por RPC), cotizar
(el índice se reusa y se rearma con otra versión), el menú y la pantalla en el navegador (buscar, copiar el precio,
«¿Quisiste decir…?», agregar un lugar, calcular por km, el celular sin scroll de lado y **que la pantalla baja con
scroll**: `overflow-y: auto` y `scrollTop` que de verdad se mueve). `dcasa_interfaz/tests/test_scroll.py` también
vigila su regla fuerte.

El enlace para choferes: `tests/test_choferes.py` (el motor sin base de datos: la distancia, los más cercanos y el corte
de 3 km, qué ubicación vale, la lista blanca de claves; las rutas: el mismo 404 apagado u otro secreto, el enlace nuevo
deja sin efecto el anterior, nunca km ni ids, sin tarifa aprobada no hay precios, coordenadas y textos que no sirven,
los límites (por IP y por red IPv6, entre todas las IP, 2 a la vez, el tope del día con su nota a Gerencia), cuerpos
rotos o gigantes sin error del servidor, las cabeceras, «Usar mi ubicación» apagado de fábrica; quién lo ve y lo
cambia, también por RPC, y que nadie elige el secreto al crear la tarifa; la Guía) y `tests/test_choferes_navegador.py`
(a 390 px: busca, ve el precio sin «km», 16 px de margen, **baja con el dedo de verdad**; en la computadora con la
rueda; «Usar mi ubicación» con y sin permiso).

```
PGPASSWORD=odoo TEST_TAGS=/dcasa_envios,/dcasa_interfaz:TestInicioScroll scripts/test.sh dcasa_envios,dcasa_interfaz
```

## Juan cotiza el envío y la promoción del mes

Con el «sí» de la dueña (2026-11-12: «tienes mi sí»; Juan pregunta, como un vendedor, «¿quieres que te lo sume a la
cotización?»). Lo de Juan está en [JUAN.md](JUAN.md) › Reglas (3); aquí, lo de Envíos.

* **Cuándo da precio:** tarifa **aprobada**, el interruptor «Cotizar envíos» de Ajustes de Juan encendido (de fábrica) y un
  lugar claro y **revisado**. Si el lugar es dudoso (varios con el mismo nombre y distinto precio, o más coincidencias de
  las que se muestran), pide un punto de referencia; si es «Cotizar aparte», está «Por revisar» o la tarifa no está
  aprobada, «te lo confirma una vendedora». La dirección exacta del cliente se quita antes de buscar y de la auditoría.
* **`agregar_envio`** pone la línea del envío (transportista «Entrega a domicilio», producto `DCASA-ENTREGA`, con los
  impuestos que diga la posición fiscal de la venta) en la cotización abierta de **esa** conversación y manda el PDF nuevo.
  Solo suma un lugar que `cotizar_envio` cotizó en esa misma conversación; con más de una cotización abierta, pregunta a
  cuál. Nunca toca una venta confirmada ni la de otro cliente.
* **Promoción de envío** (Envíos › Promoción de envío, Gerencia; modelo `dcasa.envio.promocion`, cuentas en
  `motor/promocion.py`): fechas (inclusive, hora de Panamá), compra mínima **sin ITBMS y después de descuentos y premios
  de Socios** (más de, no igual), provincias con envío gratis, abono fijo para las demás y «no aplica con colchón». La de
  noviembre de 2026 viene cargada (del 1 al 30; más de $200; Panamá y Panamá Oeste gratis; $20 de abono en Colón y el
  interior; no con colchón). En la cotización sale como una línea aparte («Promoción de envío: abono de $20»), exenta del
  tope de descuento de la vendedora **solo mientras siga valiendo**: al cambiar las líneas y antes de confirmar se vuelve a
  revisar (`_dcasa_promocion_sincronizar`); si la compra bajó del mínimo, lleva colchón, se quitó el envío o quedó en $0,
  la línea se quita con una nota en la cotización. **Lo prometido se respeta** (la dueña, 2026-11-12: una cotización de
  noviembre que se confirma en diciembre conserva su envío gratis): la línea guarda el día en que se sumó y los términos
  con que se sumó (`dcasa_promocion_terminos`: promoción, mínimo, zona, gratis o abono y su monto, regla del colchón), y
  la revisión mide la compra contra esos términos, no contra la promoción de hoy, hasta el «Vence el» que tenía la
  cotización cuando se sumó, **nunca más de 30 días** después (si no tenía, 30 días; `vale_hasta`, hora de Panamá).
  Cambiar «Vence el» después no lo alarga ni lo revive; pasado ese día, se vuelve a mirar con la promoción de hoy. Sumar el envío después de que
  terminó la promoción no la da. Si Gerencia cambia o archiva la promoción, vale solo para las cotizaciones nuevas (la
  ficha dice cuántas abiertas la tienen) y una venta confirmada nunca cambia. La marca del lugar de la línea del envío
  solo la escribe el servidor. Al duplicar, la promoción se calcula otra vez con la copia.
* **La frase** (la dueña, 2026-11-12: que no se preste a pensar que no hay descuento) dice el precio normal, lo que D'CASA
  regala o abona, las condiciones y hasta cuándo: «El envío a [lugar] cuesta normalmente $105. Con la promoción de
  noviembre, en compras de más de $200 sin ITBMS, D'CASA te abona $20 del envío: te queda en $85. La promoción es hasta el
  30 de noviembre; después, el envío vuelve a su precio normal. No aplica si la compra lleva colchón.» (cifras de ejemplo).
* **La entrada del Conocimiento** de la promoción no tiene fecha de fin: se borra o archiva al terminar (el precio que da
  Juan sí se apaga solo).

### Lugares «Por revisar»

Un lugar que agrega alguien que no es Gerencia ni administrador nace **«Por revisar»** (la dueña, 2026-11-12). La
calculadora lo usa como siempre, pero Juan no le da ese precio a un cliente («te lo confirma una vendedora») hasta que
Gerencia toque **«Marcar revisado»** en su ficha (queda quién y cuándo; filtro «Por revisar (Gerencia)» en la lista). Los
kilómetros y la provincia de un lugar solo los cambian Gerencia y los administradores. La migración `19.0.1.2.0` dejó
«Por revisar» los lugares que ya había agregado el equipo; los de la tabla cargada nacen revisados.

## Decisiones pendientes de la dueña / Gerencia

- **Aprobar la tarifa** (y decidir el redondeo, el viático, los honorarios y el peaje): hasta entonces, «en revisión».
- **Hasta dónde se envía:** decidido (2026-11-06): **«Cotizar aparte desde» = 100 km**. Hasta Colón son unos 90 km
  y cuesta alrededor de $90 (el segundo precio de la tarifa), y es lo más lejos que D'CASA envía; los 100 km dejan un
  margen sobre Colón. Más allá, la calculadora (y Brian) dicen «Cotizar aparte». Lo cambió la dueña en Envíos › Tarifa;
  como todo cambio de la fórmula, la tarifa vuelve a «en revisión» hasta aprobarla otra vez.
- **Bajar la lista a Excel:** decidido (2026-11-06): «es innecesario». La lista se ve en Envíos › Lugares; el «Exportar»
  de Odoo queda solo para quien ya tiene ese permiso (los administradores) y no se agrega un botón propio.
- **La web:** encenderla cuando haya flota propia (pasos de arriba), con su «sí».
- **Enlace para choferes:** hecho (2026-11-09), apagado de fábrica. Falta que Gerencia lo encienda y lo mande a los
  choferes; los precios salen cuando la tarifa esté aprobada.
- ~~**Juan:** que cotice cuando la tarifa esté aprobada~~: hecho (2026-11-12, arriba). Falta saber de la contadora si el
  envío lleva ITBMS (hoy `DCASA-ENTREGA` no lo lleva).
