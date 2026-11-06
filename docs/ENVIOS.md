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

Todavía **no hay ninguna ruta pública** ni nada en el sitio (sería superficie de abuso). El día que D'CASA tenga su flota
y Gerencia lo pida:

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

## Permisos

| | Equipo (vendedora, Caja…) | Gerencia | Administrador |
|---|:---:|:---:|:---:|
| Usar la calculadora, ver la lista de lugares, cotizar por km | Sí | Sí | Sí |
| Agregar un lugar que falta (barrio, edificio o PH, lugar conocido; queda su nombre) | Sí | Sí (también corregimientos) | Sí |
| Editar o archivar un lugar | No | Sí | Sí |
| Borrar un lugar | No | No (se archiva) | Sí |
| Ver, cambiar y aprobar la tarifa; cargar el archivo | No | Sí | Sí |
| Exportar la lista a Excel | Con el permiso «Exportar» de Odoo | Con el permiso «Exportar» | Sí |

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

```
PGPASSWORD=odoo TEST_TAGS=/dcasa_envios,/dcasa_interfaz:TestInicioScroll scripts/test.sh dcasa_envios,dcasa_interfaz
```

## Decisiones pendientes de la dueña / Gerencia

- **Aprobar la tarifa** (y decidir el redondeo, el viático, los honorarios y el peaje): hasta entonces, «en revisión».
- **Quién exporta la lista a Excel:** hoy solo quien tiene el permiso «Exportar» de Odoo (los administradores).
- **La web:** encenderla cuando haya flota propia (pasos de arriba), con su «sí».
- **Juan:** que cotice cuando la tarifa esté aprobada.
