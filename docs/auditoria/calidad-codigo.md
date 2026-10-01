# Auditoría de calidad de código (agente `calidad-codigo`)

Fecha: 2026-09-30 · Alcance: `addons/*` (Python, XML, JS/OWL, SCSS), `edge/` (TypeScript), `scripts/`, CI.
Solo lectura sobre el código; este informe y la bitácora son lo único escrito.

## 1. Resumen ejecutivo

El código propio está en muy buen estado: **ruff limpio, 132 .py compilan, 54 XML bien formados, 8 manifiestos
completos, todo modelo concreto con ACL, sin sintaxis obsoleta de Odoo 19, y los 264 tests de Odoo pasan contra
Odoo 19 real** (lo conseguí instalar aquí, ver 2.1). El borde (edge) pasa 20 tests y `tsc`. Las
funciones son cortas (la mayor en `addons/`: 63 líneas) y los `except Exception` son solo 4, todos con
registro en log y motivo.

No hay nada CRÍTICO ni ALTO en esta área. Lo más relevante:

1. **MEDIO** — El CI **omite en silencio los 4 tests de navegador** (los únicos que ejercitan el JS/OWL: panel de
   Brian, barra lateral, filtros rápidos): falta `websocket-client`. El JS (1.794 líneas, 8 componentes OWL) no
   tiene ningún otro test.
2. **MEDIO** — `read_group` está deprecado en Odoo 19 y lo usa el tablero de inicio (2 sitios; el log de tests ya
   emite `DeprecationWarning`).
3. **BAJO/MEDIO** — El borde no pone cabeceras de seguridad a las respuestas servidas desde/para caché (`handler.ts`).
4. Varios BAJO: textos sin traducir contra la regla de CLAUDE.md, dependencias solo transitivas, XPath/parches
   frágiles ante una actualización de Odoo, fuentes duplicadas, N+1 pequeños, huecos de cobertura.

## 2. Resultados de las herramientas (salida real, resumida)

### 2.1 Odoo real: SÍ se pudo correr
`git submodule update --init --depth 1 vendor/odoo` funcionó (commit `ba91c87`, Odoo 19.0), `apt-get install
postgresql` (16) también, y `pip` con binarios para las dependencias (hubo que saltar `docopt`/`ofxparse`, que no
compilan con el `setuptools` actual; no afecta a los módulos de D'CASA). Con Python 3.11 (el CI usa 3.12):

```
$ scripts/test.sh            # 8 módulos dcasa_* + 100 módulos de Odoo, base limpia, ~4 min
odoo.service.server: 264 post-tests in 136.07s, 36475 queries
odoo.tests.stats: dcasa_base 22 · dcasa_brian 91 · dcasa_catalogo 18 · dcasa_contabilidad 21 ·
                  dcasa_interfaz 14 · dcasa_invoice 13 · dcasa_socios 84 · website_dcasa 63
odoo.tests.result: 0 failed, 0 error(s) of 264 tests
✔ Tests OK (dcasa_base,dcasa_brian,dcasa_catalogo,dcasa_contabilidad,dcasa_interfaz,dcasa_invoice,dcasa_socios,website_dcasa)
```
- La instalación limpia carga todos los XML/CSV/vistas heredadas (todos los `ref=` y XPath resolvieron).
- **4 tests saltados** (`websocket-client module is not installed`; además aquí no hay Chrome, no pude instalarlo:
  `cdn.playwright.dev` bloqueado): `TestInterfazBrian.test_chat_en_el_navegador`,
  `test_sin_clave_muestra_aviso_y_sigue_usable`, `TestInterfazWeb.test_barra_lateral_tercer_nivel`,
  `test_filtros_rapidos_en_productos`. Esos 4 no se ejecutaron.
- Warnings de los módulos propios en el log: 2 `DeprecationWarning` de `read_group` (`tablero.py:102,121`); un aviso
  de CSRF esperado en un test (`/dcasa/carrito/agregar`) y un aviso del proveedor de IA de prueba (esperado).
- Compilación de bundles con SCSS real (`odoo-bin shell`, `_get_asset_bundle`): `web.assets_backend` (CSS 1,18 MB,
  JS 6,9 MB), `web.assets_frontend` y `web.report_assets_common`: **0 errores SCSS**.
- No pude correr el `update` (-u) sobre una base con datos ni las migraciones `post-migrate.py` (no hay base previa).

### 2.2 Lint y sintaxis
| Herramienta | Resultado |
|---|---|
| `ruff check addons` (ruff 0.15.20, config del repo: E,F,W,I,B,UP,PL) | `All checks passed!` |
| `ruff check addons scripts` | `All checks passed!` (CI solo revisa `addons`) |
| `python -m py_compile` sobre 132 .py (addons + scripts) | OK, 0 errores |
| XML bien formado (lxml) sobre 54 archivos | 0 malformados |
| JSON de datos (catalogo, fichas, puntos, resenas) | válidos |
| `node --check` sobre los 12 .js | 0 errores de sintaxis |
| Manifiestos: archivos `data/views/report/wizard/security` no listados / listados inexistentes / assets inexistentes | 0 / 0 / 0 en los 8 módulos |
| Modelos concretos sin línea en `ir.model.access.csv` | 0 (los 6 abstractos no la necesitan) |
| Sintaxis obsoleta (`attrs=`, `<tree>`, `groups_id` como campo, `_sql_constraints`, `t-raw`, `states=`, `name_get`, `@api.multi`) | 0 usos reales (`groups_id` aparece solo como cadena prohibida en `politica.py:173`) |
| Exploratorio `ruff --select C901,BLE,S,PERF,SIM,RUF,TRY,DTZ,ARG,ERA,T20` | 9 C901 (11–12 sobre 10), 0 `S` real (ver abajo), resto ruido de estilo |

Falsos positivos descartados: `S608` en `dcasa_socios/models/res_partner.py:140` (el operador SQL sale de una
lista blanca y el valor va parametrizado: correcto), `S704` `Markup` en `dcasa_invoice/models/res_company.py:41` (solo
reemplaza una URL en un `Markup` ya existente), `ARG001 version` en las migraciones (la firma la impone Odoo).

### 2.3 Edge (TypeScript)
```
$ cd edge && npm ci && npm test && npm run typecheck
Test Files 2 passed (2) · Tests 20 passed (20)   (vitest 5.0.2)
tsc --noEmit  → sin errores (typescript 7.0.2)
npm audit --omit=dev → found 0 vulnerabilities
```

## 3. Hallazgos priorizados

### Q-01 · MEDIO · El CI salta en silencio los tests de navegador (no se prueba nada del JS/OWL)
- Evidencia: `.github/workflows/ci.yml:62-76` instala solo `vendor/odoo/requirements.txt`; ese archivo no incluye
  `websocket-client`, y Odoo **salta** `browser_js` sin él. Reproducido aquí: 4 `skipped ... websocket-client module is
  not installed`. El `scripts/test.sh` solo falla con `ERROR/CRITICAL`, no con `skipped`.
- Efecto: `brian_panel.js` (622 líneas), `barra_lateral.js`, `filtros_rapidos.js` y el resto (1.794 líneas JS propias)
  pueden romperse y el CI sigue en verde. Además no hay tests unitarios JS (sin `static/tests`, sin tours).
- Arreglo: `pip install websocket-client` en el job `odoo-tests` (Chrome ya viene en `ubuntu-24.04`); en `test.sh`
  fallar si el log tiene `skipped .*websocket|Chrome`. A mediano plazo, tests `hoot` para `conciliacion.js`,
  `reportes.js` y `brian_panel.js`.

### Q-02 · MEDIO · `read_group` deprecado en Odoo 19
- Evidencia: `addons/dcasa_interfaz/models/tablero.py:102` y `:121`. `vendor/odoo/odoo/orm/models.py:2754`:
  `@api.deprecated("Since 19.0, read_group is deprecated… use _read_group … or formatted_read_group")`; el log de tests
  emite `DeprecationWarning` para ambas líneas. Se pierde en Odoo 20.
- Arreglo: `self.env['sale.order.line']._read_group(dominio, ['product_id'], ['product_uom_qty:sum'])` (tuplas, sin
  `g['product_id'][0]`) y lo mismo con `account.payment` agrupado por `journal_id` (el resto del repo ya usa `_read_group`
  bien, p. ej. `reportes.py:153`).

### Q-03 · BAJO/MEDIO · Borde: respuestas de caché (y su relleno) salen sin cabeceras de seguridad
- Evidencia: `edge/src/handler.ts:31` (`return hit`) y `:38` (`return response`) devuelven la respuesta cruda; solo la
  rama no cacheable (`:41`) pasa por `withSecurityHeaders`. Como lo cacheable son `/web/assets`, `/static`,
  `/web/image`, no salen `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, etc. en esos recursos. Ningún
  test lo cubre (`handler.test.ts` solo verifica cabeceras en la página, línea 15).
- Arreglo: `return withSecurityHeaders(hit)` / `withSecurityHeaders(response)` (cuidando de guardar en caché la copia sin
  cabeceras o con ellas, da igual) y un test. Además, `handler.ts:36` usa un ternario como sentencia
  (`deps.waitUntil ? … : await put`); mejor un `if`. (Coordinar con `@seguridad`.)

### Q-04 · BAJO · Textos sin traducir contra la regla de CLAUDE.md (`self.env._`)
- Evidencia: 14 `UserError('…')` literales: `dcasa_contabilidad/wizard/importar_extracto.py:40,63,85,93` y 10 en
  `dcasa_socios/controllers/main.py` (líneas 142–200); el resto del repo sí usa `self.env._` (111 usos). `importar_extracto.py:63`
  además usa f-string dentro del aviso (no extraíble por gettext). En JS no hay ningún `_t()` (avisos de `brian_panel.js`,
  `conciliacion.js`, `sin_odoo.js`…). No hay ningún `.po` propio (`dcasa_base/i18n/.gitkeep` solamente).
- Matiz: el producto es monolingüe en español y el idioma fuente ya es español, así que el impacto práctico es bajo; pero
  la regla escrita y el código divergen. Decidir: o se aplica la regla (`self.env._('Fila %s: …', n)` y `_t`) o se
  documenta que el código es «español-solo» y se quita la regla.

### Q-05 · BAJO · Dependencias entre módulos solo transitivas
- `dcasa_interfaz/models/tablero.py:150-156` usa `dcasa_socio_codigo` (campo de `dcasa_socios`) y
  `dcasa_catalogo/models/sale_order.py:4` importa `odoo.addons.dcasa_socios.models.reglas`, pero ni `dcasa_interfaz` ni
  `dcasa_catalogo` declaran `dcasa_socios` en `depends` (llega por `dcasa_catalogo → website_dcasa → dcasa_socios`). Hoy
  funciona; si alguien recorta esa cadena el tablero se rompe al instalar. Arreglo: declararlo explícito.
  Menor: `dcasa_brian/__manifest__.py` `external_dependencies: {'python': []}` es ruido; el código usa `requests` (ya en Odoo).

### Q-06 · BAJO · Puntos de acoplamiento frágil a internos de Odoo (vigilar en cada actualización)
Mitigado porque `vendor/odoo` está fijado por commit y la instalación limpia + tests ejercitan casi todo; el riesgo es al subir de versión.
- `dcasa_interfaz/static/src/js/sin_odoo.js:11-16,44-47`: parchea `UpgradeBooleanField`, `ActionHelper`, `SaleActionHelper`, `StockActionHelper`, `Dialog.defaultProps` (rutas internas; las verifiqué, existen hoy). Ver además el hallazgo de `ui-backend` sobre el efecto funcional del parche de `showDefaultHelper`.
- `dcasa_base/__init__.py` (`_dcasa_base_post_init`): sustituye `env.registry._auto_install_template` (atributo privado; ya protegido con `hasattr`).
- XPath posicionales/estructurales: `website_dcasa/views/layout_templates.xml:23` (`//header/*[1]`), `dcasa_invoice/views/report_invoice.xml:157` (`//tr[hasclass('o_subtotal')]/td[1]/span`), `dcasa_interfaz/views/login_templates.xml:5` (por `href` con `utm_source`), `website_dcasa/views/paginas_templates.xml:12,25,46` (`s_title`, `p.lead`, `offset-lg-1` sin más contexto); y `replace` de bloques enteros (`//div[@id='footer']`, `//div[@id='wrap']`). El resto (≈60 XPath) usa `@name`/`@id`/`hasclass`, que es lo recomendado.
- Arreglo: checklist «al subir Odoo: `scripts/test.sh` + revisar estos 6 puntos»; donde se pueda, anclar con `@id`/`t-set`.

### Q-07 · BAJO · Rendimiento: N+1 pequeños y una búsqueda que carga todo
- `dcasa_interfaz/models/tablero.py:94-99`: 7 `search` (uno por día) para las barras de la semana; un solo `_read_group` por `date_order:day` lo resuelve. Se ejecuta en cada carga del inicio.
- `dcasa_socios/models/res_partner.py:144-145`: `_search_dcasa_saldo` hace `Movimiento.sudo().search([]).partner_id.ids` (carga **todo** el libro) cuando el saldo 0 cumple el filtro. Mejor `SELECT DISTINCT partner_id` en la misma consulta SQL y usar `NOT IN` en SQL, o un subdominio. Crece con el libro mayor.
- `dcasa_contabilidad/models/reportes.py:158-161` (`libro_mayor`): un `search` por cuenta (limitado a `limite+1` líneas c/u, aceptable); `conciliacion.py:170-171` y `dcasa_brian/models/herramientas_contabilidad.py:510-512`: un `search_count` por diario (pocos diarios: irrelevante hoy); `presupuesto.py:104-107` `_compute_real`: un `search` por línea de presupuesto (decenas, aceptable).
- `dcasa_socios/models/dcasa_canje.py:208-211` (cron de cumpleaños): consulta por socio candidato; bien mientras sean pocos al día.
- Reconocimiento: el resto usa `_read_group`, `mapped` y `filtered` bien; no hay N+1 graves.

### Q-08 · BAJO · Duplicación de binarios
- Mismas fuentes byte a byte en dos módulos (md5 idéntico): `Inter-{Regular,SemiBold,Bold}.ttf` en `dcasa_base` y `dcasa_invoice` (≈204 KB) y `Anton-Regular.ttf` en `dcasa_interfaz` y `dcasa_invoice` (25 KB), más sus licencias. `dcasa_invoice` ya depende de `dcasa_base`. Arreglo: dejar las fuentes en `dcasa_base/static/src/fonts` y referenciarlas desde el SCSS del reporte.
- Código duplicado entre módulos (funciones con el mismo AST ≥5 líneas): 0 hallazgos. Helpers parecidos pero con propósito distinto (`c.moneda` en Brian vs `monto_en_letras`): no se consideran duplicados.

### Q-09 · BAJO · Cobertura de tests: lo que no tiene test
Hay 264 tests y todos los módulos tienen carpeta de tests; 51 clases con `@tagged('post_install', '-at_install')`, ninguna sin etiqueta, ningún test sin aserción. Huecos:
- JS/OWL: solo los 4 tests de navegador saltados (Q-01). `conciliacion.js`, `reportes.js`, `inicio.js`, `animaciones.js`, `brian_markdown.js` sin pruebas.
- `dcasa_contabilidad/controllers/main.py:100` (`/dcasa/contabilidad/excel`, ruta HTTP con `auth='user'`): se prueba `libro_excel` (función) pero no la ruta ni su control de acceso; `report/reportes_pdf.py` (PDF de reportes) no tiene test (el PDF del cheque sí).
- `dcasa_socios/models/ir_http.py`: el `?ref=DCA…` en cualquier página no se prueba (solo `/r/<código>`, `test_app.py:40`).
- Migraciones `post-migrate.py` (10 archivos en base/catálogo/website): ninguna probada; `_dcasa_*_post_init` solo indirectamente vía la instalación.
- `edge/src/index.ts` (mapa de variables del contenedor, `OPTIONAL_CONTAINER_VARS`, cron) sin test; el resto del borde está bien cubierto (20 tests).
- `scripts/importar_catalogo.py` (245 líneas, `main` con 95 líneas y complejidad 12) sin test; `demo_data.py` y `preview_shots.py` son utilidades de vista previa.
- Tests potencialmente frágiles: `dcasa_base/tests/test_configuracion.py:71-72` comparan conteos antes/después (robustos); los de fechas usan `fields.Date.today()`/`Datetime.now()` y `datetime(…)` sin tz en `dcasa_socios/tests/test_canjes.py:104`, `test_reglas.py:132` (por verificar: cerca de medianoche UTC/Panamá podrían diferir). No encontré `sleep`, orden aleatorio ni dependencia de datos demo.

### Q-10 · BAJO · Pequeñas deudas de estilo y mantenimiento
- Complejidad (C901 > 10): `conversacion.py:586 _neutro` (11), `politica.py:212 _revisar_secretos` (12), `proveedores.py:106 _post` (12), `proveedores.py:183 mensajes` (12), `telegram.py:305 procesar_update` (11), `catalogo.py:92 cargar_catalogo` (11), `importar_extracto.py:32 leer_csv` (11), `socios/controllers/main.py:138 _registrar` (11), `scripts/importar_catalogo.py:147 main` (12, 95 líneas). Nada alarmante; `main` del script es lo único a partir.
- Los 4 `# noqa: BLE001` (`mcp.py:310`, `telegram.py:49`, `conversacion.py:492`, `registro.py:216`) están marcados como «sin usar» porque `BLE` no está activado en ruff: añadir `BLE` a `select` hace que el `noqa` tenga sentido y vigile nuevos `except Exception`.
- Código comentado: `herramientas_contabilidad.py:203` y `telegram.py:211` son solo banners de sección (falso positivo de ERA001).
- Mezcla de estilos de comandos ORM: `Command.*` (10) frente a tuplas `(0,0,…)/(6,0,…)` (23). Preferir `Command` (Odoo 19).
- `clearTimeout/setTimeout` globales en `conciliacion.js:99-100` sin limpieza al desmontar el componente (el resto usa `browser.setTimeout`/`onWillUnmount`); `sin_odoo.js` y otros con avisos sin `_t`.
- `scripts/demo_data.py` se declara «nunca contra producción» pero no lo impone (PIN fijo `482915`, cliente demo): añadir un aborto si la base no es la de vista previa (`PREVIEW_URL` ausente → salir). Solo se lanza desde `.github/workflows/preview.yml`.
- `dcasa_brian/models/telegram.py:437`, `reportes.py:217,284`, `tienda.py:89`: argumentos no usados (`update_id`, `desde`, `borradores`, `proveedor`): firmas heredadas de una interfaz; revisar si se pueden quitar.
- CI: el job de lint solo hace `ruff check addons`; incluir `scripts` (también pasa) y dejar la verificación XML con `lxml` no hace falta (el script del CI con `ElementTree` es suficiente).

## 4. Lo que está bien hecho
- Convenciones Odoo 19 aplicadas de forma consistente: `<list>`, `invisible=`, `models.Constraint`, `group_ids`, `self.env._`, `t-out`, `_read_group` en casi todo, `@tagged('post_install','-at_install')` en todos los tests.
- Manifiestos impecables: orden de `data` correcto (seguridad → datos → vistas → menús), `assets` por bundle correcto, hooks de instalación idempotentes (`_configurar_*` «se puede repetir»).
- ACL y reglas de registro completas y con mínimo privilegio razonable (p. ej. movimientos de socios de solo lectura para vendedora/contabilidad; reglas de Brian por propietario).
- Manejo de errores cuidadoso: solo 4 `except Exception` (con `savepoint`, log con traza y motivo); el resto captura tipos concretos (`ValueError`, `requests.RequestException`, `AccessError`). Ningún `except: pass` que trague errores (el único `try/except/pass` es una conversión numérica, `proveedores.py:131`).
- Funciones pequeñas y nombres claros en español consistente; documentación (docstrings) que explica el porqué; cero código muerto detectado por ruff/ARG fuera de firmas heredadas.
- Suite de tests amplia (264) y rápida (136 s), con pruebas de regla de negocio reales (factura 00821, libro inmutable, candados de PIN, política de Brian); pruebas de sintaxis de bundle (`test_bundle_backend_incluye_la_interfaz`).
- Edge: lógica pura separada y testeada, `strict` de TypeScript, 0 vulnerabilidades, caché solo para respuestas `public` sin cookie.
- SCSS de los 3 bundles compila sin errores; todos los JS usan `@odoo-module` y `patch`/`registry` de forma estándar.

## 5. Plan de arreglo ordenado
1. Q-01: instalar `websocket-client` en CI y fallar si hay tests de navegador saltados (30 min).
2. Q-02: migrar `read_group` → `_read_group` en `tablero.py` (30 min), y de paso Q-07 (1 consulta para la semana).
3. Q-03: `withSecurityHeaders` en las ramas de caché + test (30 min).
4. Q-05: declarar `dcasa_socios` en `depends` de `dcasa_interfaz` y `dcasa_catalogo`.
5. Q-09: test de ruta Excel y del `?ref=`, test del mapa de variables de `index.ts`, tests de migraciones al menos de humo.
6. Q-04: decidir política de traducción (aplicar `self.env._`/`_t` o documentarla como solo español).
7. Q-06/Q-08/Q-10: lista de control de actualización de Odoo, deduplicar fuentes, activar `BLE`, guarda en `demo_data.py`.
