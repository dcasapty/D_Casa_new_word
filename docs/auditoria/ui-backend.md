# Auditoría `ui-backend` — interfaz, UX y accesibilidad del panel (sin la barra lateral)

Fecha: 30/09/2026 · Auditoría **estática** (lectura de código contra el fuente de Odoo 19 de `vendor/odoo`, que sí está presente; no se ejecutó la app ni se vio en pantalla). Lo que depende de ver el render va marcado `(por verificar)`.

Alcance: `dcasa_interfaz` (Inicio, filtros rápidos, login, tokens, global.scss, sin_odoo.js), vistas y OWL de `dcasa_socios`, `dcasa_contabilidad`, `dcasa_catalogo`, `dcasa_invoice`, `dcasa_base`, y la app del socio `/socios`. La barra lateral la cubre `navbar`.

## Resumen ejecutivo

El panel está bastante mejor que cuando se hizo `docs/AUDITORIA_UX.md` (29/09): la mayoría de los 100 problemas de la vendedora y la dueña se corrigieron de verdad (español, descuentos, cobros por forma de pago, búsqueda por celular y por varias palabras, WhatsApp desde la cotización, Inicio con tablero, factura sobria). La base visual (tokens, foco, estados vacíos, chips de filtro, `aria-pressed`, `prefers-reduced-motion`) es coherente y cuidada.

Lo que queda pesa en tres frentes:

1. **Un parche global anula los textos de ayuda propios**: todas las listas vacías muestran «Toca «Nuevo»…» aunque no exista botón Nuevo, y el `help` específico de cada acción (en español, bien escrito) jamás se ve (UI-01).
2. **Roles sin definir**: la vendedora con solo «Ventas: usuario» no puede registrar un cobro (Odoo no le da `account.payment`), pero el Inicio le ofrece «Registrar cobro» y le dice «Todavía no hay cobros registrados hoy» en vez de «no tienes acceso». Además ve reportes antifraude y el pasivo del programa (UI-02, UI-03).
3. **Accesibilidad de teclado y foco**: el indicador de foco (`--dc-foco`) mide 1.5:1 contra blanco, y todas las tablas de reportes contables son clicables solo con ratón (UI-04, UI-05).

Conteo: 0 críticos · 3 altos · 8 medios · 11 bajos.

---

## Hallazgos priorizados

### ALTO

**UI-01 · ALTO · El parche de «lista vacía» borra el `help` de todas las acciones y manda a un botón que no existe**
- `addons/dcasa_interfaz/static/src/js/sin_odoo.js:38-40` fuerza `get showDefaultHelper() { return true; }`. En `vendor/odoo/addons/web/static/src/views/action_helper.xml` la rama `t-else` (`props.noContentHelp`, o sea el `help` de la acción) solo se dibuja si `showDefaultHelper` es falso. Resultado: nunca.
- Consecuencia: los textos escritos a medida quedan muertos: «Aún no hay socios…» (`dcasa_socios/views/res_partner_views.xml:116-117`), «Todavía no hay compras con puntos» (`dcasa_compra_views.xml:110-111`), «Crea tu primer presupuesto» (`presupuesto_views.xml:99-100`), «Todavía no hay cobros registrados hoy» (`dcasa_base/views/hoy_views.xml:22`), etc.
- Peor: el texto genérico (`sin_odoo.js:45`) dice «Toca «Nuevo» para crear el primero» también en listas sin botón Nuevo (`create="false"`): Libro de puntos (`dcasa_movimiento_views.xml:7`), Compras (`dcasa_compra_views.xml:7`), Canjes (`dcasa_canje_views.xml:7`), Cobros de hoy. Y «Toca» es vocabulario táctil en una herramienta de escritorio.
- Arreglo: que `showDefaultHelper` devuelva `!this.props.noContentHelp` (conserva el `help` propio cuando existe) y que el texto genérico diga «Pulsa «Nuevo»…» solo si la vista permite crear (o texto neutro: «No hay registros con estos filtros»).

**UI-02 · ALTO · Rol «vendedora» sin definir: con solo Ventas no puede cobrar, y el tablero lo disimula**
- El fuente de Odoo (`vendor/odoo/addons/sale/security/ir.model.access.csv:8`) da al `sales_team.group_sale_salesman` solo **lectura** de `account.move` y **ningún** acceso a `account.payment`. Registrar un cobro exige `account.group_account_invoice` (Facturación), que además abre vendor bills y el menú de Facturación completo.
- En `dcasa_interfaz/models/tablero.py:61-62` el tablero solo omite «Cobrado hoy» si no hay `read` en `account.payment`; pero `dcasa_interfaz/static/src/xml/inicio.xml:22-25` (botón «Registrar cobro», sin condición) y `inicio.xml:71-79` (panel «Caja de hoy» con `d.cobros.length` vacío) siguen visibles: la vendedora ve «Todavía no hay cobros registrados hoy» (`inicio.xml:79`) aunque se cobró todo el día, y el botón falla con «Access Error».
- El test `dcasa_interfaz/tests/test_interfaz.py:33-39` ratifica justo ese estado (vendedora solo con Ventas ve «su tablero») sin afirmar que pueda cobrar.
- No hay grupos ni usuarios de rol en ningún `data/` (`grep group_account_invoice|group_sale` en `addons/*.xml`: solo 4 usos en `hoy_views.xml`, `menus.xml`). `AUDITORIA_UX.md` #14/#83 sigue sin resolverse en código.
- Arreglo: definir en `dcasa_base` dos roles documentados (Vendedora = Ventas usuario + Facturación «Invoicing»; Gerencia = Ventas administrador + Contabilidad) y probar con un test el flujo vender→cobrar con ese usuario. En el Inicio, ocultar «Registrar cobro» y «Caja de hoy» cuando no hay permiso (enviar `puede_cobrar` desde `obtener_datos`) o decir «No tienes acceso a cobros».

**UI-03 · ALTO · La vendedora ve el control antifraude (todas las vendedoras) y el pasivo del programa**
- `dcasa_socios/views/menus.xml:5` (raíz «Socios» para `group_sale_salesman`) y `menus.xml:14-18`: el submenú «Reportes» (Puntos por vendedora, Pasivo del programa) no lleva `groups`. El ACL `dcasa_socios/security/ir.model.access.csv:2,4` da lectura de `dcasa.compra` y `dcasa.movimiento` a toda vendedora.
- `dcasa_socios/views/dcasa_compra_views.xml:120` lo describe como «el control antifraude: si una vendedora emite el triple que las demás, aquí se ve»: justamente lo que la vendedora no debe ver. El «Pasivo del programa» (deuda en puntos de la empresa) tampoco es de su nivel. También ve «Compras» y «Libro de puntos» de todos los socios con `autor`.
- Arreglo: `groups="sales_team.group_sale_manager"` en `menu_dcasa_reportes` (y regla de registro o ACL solo-gerente para el pivot por vendedora). Decisión de negocio por confirmar: si la vendedora debe ver el libro completo o solo el de la ficha que consulta.

### MEDIO

**UI-04 · MEDIO · Indicador de foco de 1.5:1 (WCAG 2.4.7/1.4.11)**
- `dcasa_interfaz/static/src/scss/tokens.scss:43`: `--dc-foco: 0 0 0 3px var(--dc-azul-200)` (#C3D2F6 sobre blanco = 1.51:1; mínimo 3:1). Es el **único** indicador de foco (con `outline: none`) en: botones `global.scss:58`, tarjetas de cifras `interfaz.scss:135`, barras del gráfico `interfaz.scss:221,225`, apps `interfaz.scss:342`, lista «lo más vendido» `interfaz.scss:293`, chips `filtros_rapidos.scss:40`, pestañas y movimientos de contabilidad `contabilidad.scss:70,108,327,380`.
- Un usuario de teclado casi no ve dónde está. Se hereda también a la barra lateral (ver `navbar`).
- Arreglo: `--dc-foco: 0 0 0 2px #fff, 0 0 0 4px var(--dc-azul-600)` (azul-600 sobre blanco ≈ 9:1). Un solo cambio en el token arregla todo.

**UI-05 · MEDIO · Reportes contables: filas clicables solo con ratón**
- `dcasa_contabilidad/static/src/xml/reportes.xml:77,107,128,157,164,195,212` y `conciliacion.xml:82`: `<tr t-on-click>` sin `tabindex`, `role` ni `t-on-keydown`; `reportes.xml:157` pone `aria-expanded` sobre un `<tr>` sin rol de botón (inválido). Sin ratón no se puede bajar de un renglón del estado de resultados al detalle, ni abrir/cerrar cuentas del libro mayor. (En conciliación la casilla interna sí es alcanzable y tiene `aria-label`: bien.)
- Además `reportes.xml:21-28` y `conciliacion.xml:20,63` declaran `role="tablist"` con hijos sin `role="tab"` (el segmento de «Facturas / Sin factura» ni siquiera lleva `aria-selected`), y los chips de periodo (`reportes.xml:32-35`) no indican cuál está activo más que por color (falta `aria-pressed`).
- Arreglo: poner un botón (o `tabindex="0" role="button"` + Enter/Espacio) en la celda del nombre; `aria-pressed` en chips y segmento; quitar `role=tablist` o completar el patrón.

**UI-06 · MEDIO · «Ventas de hoy» (menú) y «Vendido hoy» (tablero) no coinciden: el menú usa UTC**
- `dcasa_base/views/hoy_views.xml:8`: `date_order >= context_today().strftime('%Y-%m-%d')`. Para un campo Datetime, esa cadena se interpreta a las 00:00 **UTC**, que en Panamá son las 19:00 del día anterior (y no hay cota superior). El tablero sí usa los límites correctos en hora de Panamá (`tablero.py:32-36`, `_limites_del_dia`).
- Efecto: el pedido web confirmado a las 9 p. m. de ayer aparece en «Ventas de hoy» y la lista no suma la cifra de la tarjeta. `(por verificar en pantalla)`; la lógica de dominio es de Odoo estándar.
- Arreglo: en vez de dominio XML, que la acción del menú sea `ir.actions.server` o reutilizar la acción del tablero (`tablero.py:73,78`) con los límites calculados; o `ir.actions.client` a `dcasa.tablero`. El `context` `{'search_default_salesperson': 0}` (línea 9) no hace nada.

**UI-07 · MEDIO · «Pedidos web por atender» no cuenta los pedidos web pendientes de pago**
- `dcasa_interfaz/models/tablero.py:87`: dominio `website_id != False AND state = 'sale' AND delivery_status != 'full'`. «Cotizaciones abiertas» (línea 80) excluye los del sitio (`website_id = False`). Un pedido web con transferencia/Yappy sin verificar queda en borrador o «enviado» y **no está en ninguna tarjeta**. `(por verificar: estado en que deja `sale` un pago pendiente)`.
- Además el detalle «Confírmalos por WhatsApp» (línea 90) contradice el filtro: lo que se cuenta ya está confirmado.
- Arreglo: contar aparte «Pedidos web por confirmar» (`state in draft/sent`, `website_id != False`, con transacción pendiente) y dejar «por atender» para entrega.

**UI-08 · MEDIO · Descuento libre para todo usuario interno**
- `dcasa_base/__init__.py:110-114`: `sale.group_discount_per_so_line` se implica en `base.group_user`; ninguna vista ni regla limita el %. Cualquier vendedora puede bajar un precio a 100 % o editar `price_unit`, y «Cobrar premio» (`dcasa_cobrar_premio_wizard.py`) ya inserta una línea negativa (`dcasa_cobrar_premio_wizard.py:49`). Es UX y control a la vez: el flujo está a un clic de error.
- Arreglo: limitar descuento por rol (campo «Desc. máx.» o aprobación sobre X %) o restringir `discount` y `price_unit` al grupo gerente; decidirlo con la dueña.

**UI-09 · MEDIO · Dos celulares en la ficha (sigue #31 a medias) y placeholder con el número de la tienda (sigue #96)**
- `dcasa_socios/views/res_partner_views.xml:30`: `dcasa_celular` con `placeholder="6026-1919"` (el WhatsApp de D'CASA). `AUDITORIA_UX.md` #96 pedía un placeholder neutro; no se hizo. Un cliente nuevo puede quedar con el teléfono de la tienda por copiar el ejemplo.
- `res_partner.py:25-28` y `_dcasa_asegurar_ficha` copian `phone` a `dcasa_celular` solo al crear la ficha; después son dos campos editables e independientes. El mismo problema ya estaba en `dcasa_base/views/res_partner_views.xml:11`, donde el ejemplo de RUC es el RUC de la propia empresa.
- Arreglo: placeholder «8 dígitos, p. ej. 6xxx-xxxx»; sincronizar (onchange de `phone` → `dcasa_celular` mientras estén vacíos) o dejar `dcasa_celular` de solo lectura con aviso «cámbialo en Teléfono».

**UI-10 · MEDIO · Ficha de socio: sigue siendo el formulario genérico de Contactos (sigue #81/#82)**
- `res_partner_views.xml:114`: la acción «Socios» abre `base.view_partner_form` completo; los puntos y el historial quedan en la última pestaña (`res_partner_views.xml:18-19`) y el botón «Puntos» (línea 10) queda primero, que sí ayuda. La lista (`res_partner_views.xml:78-87`) tiene 8 columnas y no hay kanban para móvil: en el teléfono el código y el nombre se cortan (`#82`).
- Arreglo: form propio con saldo + código + celular + botones de acción arriba; kanban `mobile` para la acción Socios.

**UI-11 · MEDIO · Premio de descuento: la vendedora no puede canjear en mostrador para un cliente sin PIN (sigue #36)**
- `dcasa_socios/wizard/wizard_views.xml:48` pide el «Código que enseña el cliente», que solo nace si el socio lo generó en `/socios` con su PIN; `dcasa_canje_views.xml:7` no permite crear. Si el cliente aún no reclamó su ficha no hay camino desde el mostrador. Es coherente con `CLAUDE.md` (regla 4 y 6) y `docs/SOCIOS.md`, así que puede ser decisión de diseño; lo dejo como **pregunta de negocio**: ¿se quiere un «Canjear premio» asistido (con PIN o código de factura)?

### BAJO

**UI-12 · BAJO · Menú «Socios → Compras» choca con la app «Compras»**: `dcasa_socios/views/menus.xml:10` llama «Compras» a lo que la acción titula «Compras con puntos». Junto al app «Compras» (proveedores, `iconos_data.xml:14-16`) confunde a la vendedora. Renombrar el menú a «Compras con puntos».

**UI-13 · BAJO · Tokens de texto con contraste justo**: `--dc-tinta-3` (#6B7690) da 4.55:1 sobre blanco (pasa), pero 4.2:1 sobre `--dc-niebla` (#F4F6FA) y 3.97:1 sobre `--dc-perla`, que es el fondo de `.o_dcasa_inicio` y `.o_dc_conta` (`interfaz.scss:18-25`, `contabilidad.scss:3-9`) con textos de 11-13 px (`.o_dcasa_cifra_detalle` .78rem, `.o_dc_nota`, `.o_dc_mov_fecha` .75rem). Oscurecer `--dc-tinta-3` a ~#5B6680 (≥4.6:1 sobre niebla).

**UI-14 · BAJO · Se quitó «Atajos de teclado» del menú de usuario**: `sin_odoo.js:58` elimina `documentation`, `support`, `shortcuts` y `odoo_account`; los tres primeros apuntan a odoo.com pero `shortcuts` abre la paleta con los atajos (Ctrl+K) y no sale del sistema. Quitarlo de la lista resta descubribilidad de teclado.

**UI-15 · BAJO · Lista «Lo más vendido»**: `inicio.xml:86`: `<li role="button" tabindex="0">` dentro de `<ol>` rompe la semántica de lista (un `li` con rol de botón deja de ser ítem) y solo responde a Enter (`t-on-keydown`), no a Espacio. Usar `<button>` dentro del `<li>`.

**UI-16 · BAJO · Orden de encabezados del Inicio**: `inicio.xml:6` pone un `<h2 class="visually-hidden">` antes del `<h1>` (línea 12). Mover el h2 oculto o quitarlo.

**UI-17 · BAJO · Punto amarillo sobre blanco en el saludo**: `interfaz.scss:67-75`: `.o_dcasa_inicio_fecha::before` es un punto `#FED00F` rodeado de `azul-50` sobre el héroe blanco; choca con la regla 1 de marca («el amarillo nunca toca el blanco»). Usar `--dc-azul-600` o sacarlo.

**UI-18 · BAJO · Barra superior translúcida (`backdrop-filter`)**: `global.scss:13`. La auditoría del sitio (#69) ya quejó el efecto «vidrio» por dejar ver texto debajo; además contradice «sistema plano» (regla 3). Fondo sólido `--dc-blanco`.

**UI-19 · BAJO · `@font-face` de Anton sin uso en el panel**: `interfaz.scss:4-8` declara Anton (y el TTF viaja en el módulo) pero ningún selector del backend la usa (el panel usa Inter por decisión). Quitar o usarla en el título del Inicio si se quiere la marca.

**UI-20 · BAJO · Tablero: 7 consultas para la gráfica semanal**: `tablero.py:94-100` hace un `search` + `mapped` por día; un `read_group` por `date_order:day` lo resuelve en una. No es UX pero la pantalla de entrada carga con eso.

**UI-21 · BAJO · `/socios`: detalles de pulido**
- `socios_templates.xml:209` «Te faltan 250» sin la palabra «puntos».
- `:105` `<label>` sin `for` para el cumpleaños (los selects sí traen `aria-label`).
- `:198-213` sin estado vacío si no hay premios activos (tarjeta «Premios» vacía).
- `:161-165` el QR va antes del enlace y no hay botón «Copiar» (sigue #93).
- Los errores de registro (`socios_aviso`, línea 7) llevan `role="alert"` pero no se enlazan al campo (`aria-describedby`/`aria-invalid`).

**UI-22 · BAJO · Conciliación/reportes**: sin estado de error ni `aria-busy` (`reportes.js:88-96`, `conciliacion.js:56-64`: si la llamada falla queda `cargando = true` para siempre); el buscador del libro mayor (`reportes.xml:150`) y el de conciliación (`conciliacion.xml:75`) solo tienen `placeholder`, sin `aria-label`.

---

## Verificado como resuelto (de `AUDITORIA_UX.md`)

| # | Tema | Evidencia |
|---|---|---|
| 3, 52 | Backend en español y hora de Panamá | `dcasa_base/__init__.py:91-105,134-141` (es_419, tz, `.`/`,` de Panamá) |
| 9 | Descuentos y variantes visibles | `dcasa_base/__init__.py:110-114` (ver UI-08: falta control) |
| 10 | Efectivo, Yappy, Tarjeta | `dcasa_base/__init__.py:8-12,78-81` |
| 12, 32, 34 | Buscar cliente por celular y producto por varias palabras | `dcasa_socios/models/res_partner.py:31-38` (`_search_display_name`); `dcasa_catalogo/models/product.py:21-35`; la búsqueda base de Contactos filtra por `display_name` |
| 13 | Aviso de celular duplicado antes de guardar | `res_partner.py:40-58` |
| 16, 22, 41 | ITBMS incluido y nombres claros | `dcasa_base/__init__.py:52-76` |
| 35 | Botón «Puntos» primero | `res_partner_views.xml:8-17` |
| 37 | Cotización por WhatsApp | `dcasa_catalogo/views/backend_views.xml:10-12`, `models/sale_order.py:11-30` (valida celular, mensaje con tuteo) |
| 38, 39 | «Ventas de hoy» e Inicio al entrar | `hoy_views.xml`, `dcasa_interfaz` (con la salvedad UI-06) |
| 43, 60, 74, 84, 100 | Factura: ITBMS coherente, pago real en vez de sello, RUC/cédula, fuentes de marca | `dcasa_invoice/views/report_invoice.xml`, `report_dcasa.scss:9-32` |
| 46, 47, 49, 50 | App del socio: etiqueta legible, fechas dd/MM/yyyy, confirmar y tocar ≥44 px, sin franja amarilla | `socios.scss:47-51,99-103`; `socios_templates.xml:184,186-191,203-208` |
| 51 | Nombre del almacén | `dcasa_base/__init__.py:128-131` |
| 77 | Lista de productos con foto, categoría y publicado | `backend_views.xml:30-47` |
| 85 | Textos de Socios con tilde | `dcasa_socios/models/*.py` (labels «Código de socio», «Celular del programa») |
| 98 | Sin enlaces a odoo.com en el menú | `sin_odoo.js:56-62` (ver UI-14) |

Siguen abiertos de esa lista: #36 (UI-11), #81-#83 (UI-02, UI-10), #96 (UI-09), #75 (Reset to Draft / Credit Note en facturas pagadas, sin restricción en `addons/`), #95 (pestaña «Other Info» con campos sin uso), #93 (copiar enlace).

## Lo que está bien hecho

- **Sistema de diseño coherente y plano**: tokens en un solo archivo (`tokens.scss`), escala de azules, radios/sombras mínimos (`sombra-2` de 6 % de opacidad), cifras tabulares, `prefers-reduced-motion` (`interfaz.scss:366-368`). Cumple la regla 3 de marca.
- **Inicio** (`inicio.xml`): saludo, 5 accesos del día a día, tarjetas clicables que abren la lista que las explica, gráfico con `role="img"` + `aria-label` por barra y foco que muestra el valor (no depende del hover), estados vacíos propios por panel, y responsive real (`@media` a 575/767/1199 px, accesos con scroll horizontal).
- **Filtros rápidos** (`filtros_rapidos.xml/js`): chips de un clic con `aria-pressed`, ícono de check además del color, separador por grupo, «Quitar filtros», y `role="group"` con etiqueta. Es de lo mejor del panel para una vendedora.
- **Permisos en el tablero**: cada cifra respeta `has_access('read')` (`tablero.py:48-61`), no inventa datos y se mide en hora de Panamá; las cifras se abren sobre la lista exacta que las produjo.
- **Conciliación bancaria**: flujo de dos paneles claro, casilla con `aria-label`, sugerencias marcadas, diferencia explicada («queda pendiente o regístrala sin factura»), estado «Todo conciliado» con la siguiente acción. Negativos entre paréntesis (no solo color).
- **Formularios de socios**: los asistentes explican la consecuencia antes de pulsar («El socio ve este motivo en su cuenta», «Se devuelven sus puntos…»), botones destructivos con `confirm`, acciones de riesgo restringidas a gerente (Ajustar, Suspender, Anular).
- **App del socio `/socios`**: móvil primero, labels con `for`, `autocomplete`/`inputmode` correctos, enlaces subrayados (WCAG 1.4.1), puntos con signo y color, cancelar/pedir con confirmación y 44 px, QR local (sin servicio externo), fechas en hora de Panamá, términos generados desde `puntos.json` (no pueden contradecir al sistema).
- **Factura**: bloque de cliente único para factura y cotización, monto en letras en español, pago real (fecha, forma, saldo) en vez de sello, fuentes de marca alojadas, amarillo solo entre azules.
- **Vocabulario**: español, tuteo, sin jerga de Odoo en los textos propios («Por cobrar», «Caja de hoy», «Lo más vendido»). «En desarrollo» en vez de «Enterprise» es una decisión honesta y está bien ejecutada (`en_desarrollo.xml`, `.js`).

## Plan de arreglo (orden sugerido)

1. UI-01 (parche de lista vacía): 10 líneas, afecta todas las pantallas.
2. UI-04 (foco): cambiar un token.
3. UI-02 + UI-03 (roles y menús): definir Vendedora/Gerencia en `dcasa_base`, ocultar `Reportes` a vendedora, condicionar «Registrar cobro» y «Caja de hoy», test de flujo completo con el usuario vendedora.
4. UI-06, UI-07 (números del tablero vs listas).
5. UI-05 (teclado en reportes) y UI-09/UI-10/UI-12 (ficha de socio y vocabulario).
6. UI-08 tras hablar con la dueña (política de descuentos) y UI-11 como decisión de negocio.
7. Bajos en una sola pasada de pulido.
