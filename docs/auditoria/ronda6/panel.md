# Ronda 6 · Panel de Odoo (back-office)

Fecha: 02/10/2026 · Alcance: lo que usan la dueña y las vendedoras en el panel (Inicio, ventas,
inventario, productos, clientes y Socios, facturas, menús). No se tocaron `website_dcasa`,
`dcasa_tienda_borde` ni `edge/`. No cambia ninguna regla de negocio de Socios ni de contabilidad.

## Cómo se midió

- Base `dcasa_t_panel` con **todos** los módulos de `addons/` y el catálogo real de `dcasa_catalogo`
  (237 productos, 268 variantes). Para que las listas pesen como en una tienda con historia se
  generaron datos de prueba: 1 500 clientes, 1 500 cotizaciones (1 100 confirmadas, en los últimos
  120 días), 800 facturas, 550 cobros (que dieron 550 socios y 550 asientos de puntos), 400 entregas
  validadas y existencias para todo el catálogo. Usuarios: `admin` (Gerencia) y una Vendedora con el
  rol `D'CASA / Vendedora`.
- Navegador real (Chromium sin caché) que entra con cada usuario y recorre Inicio, Cotizaciones,
  Pedidos, Productos (Ventas e Inventario), Existencias, Transferencias, Clientes, Socios, Facturas,
  Ventas de hoy y un formulario de cada tipo; cada pantalla dos veces (en frío y en caliente).
- En el servidor, la línea de log de cada petición trae **número de consultas SQL y tiempo**; se
  agrupó por pantalla. Además, conteo de consultas por campo de cada lista (para cazar N+1),
  `EXPLAIN ANALYZE` de las listas de Socios y `pg_stat_user_tables`.
- Los tiempos de navegador son de una máquina compartida (con otros Odoo corriendo): sirven para
  comparar, no como cifra absoluta. Las **consultas por pantalla** sí son estables.

## Hallazgos y mediciones (antes → después)

| # | Pantalla / tema | Antes | Después |
|---|---|---|---|
| P-1 | **Transferencias / Entregas** (lista, 80 filas) | **246 consultas**, 420–490 ms de servidor en cada carga | **8 consultas**, 45–120 ms |
| P-2 | **Clientes** (lista, primera vez) | 51 peticiones (un avatar de letra por fila, ~7 consultas c/u), ~400 consultas, **4,2–4,5 s de servidor** | 3 peticiones, 43 consultas, 0,2–0,3 s |
| P-3 | **Inicio** (`obtener_datos`) | 38 consultas (8 búsquedas que cargaban pedidos enteros para la semana) | 26 consultas, una sola lectura para «Vendido hoy» y la semana |
| P-4 | Primer ingreso de un administrador | `iap_enrich_auto`: 71 consultas, ~1 s y llamada a odoo.com (que además puede reemplazar el logo de la empresa) | no se llama |
| P-5 | Libro de puntos / Compras / Canjes (orden por fecha) | sin índice: con 200 000 asientos, 29 ms por página (escaneo y orden de toda la tabla) | con índice: 0,08 ms |
| U-1 | **Cotizaciones** para la dueña | filtro «Mis cotizaciones»: **lista vacía** (la dueña no cotiza) | abre las cotizaciones abiertas de toda la tienda |
| U-2 | **Ventas de hoy** (UI-06, abierto desde la ronda 1) | el día empezaba a la medianoche UTC (7 p. m. de Panamá): metía las ventas de anoche y no cuadraba con «Vendido hoy» | día de Panamá; la dirección `/odoo/ventas-de-hoy` recalcula al recargar |
| U-3 | Menús de la Vendedora | 96 entradas (editor HTML/CSS y SEO del sitio, facturas y pagos a proveedores, análisis de facturas, variantes, listas de precios…) | 55 entradas |
| U-4 | **Ventas › Clientes** | solo clientes con factura (quien solo pidió cotización no aparecía: 633 de 1 506) y «Nuevo» creaba una **empresa** | todos los clientes; «Nuevo» crea una persona |
| U-5 | Inicio de la Vendedora | sin cifra propia | tarjeta «Mis cotizaciones» (cuántas y por cuánto, abre la lista) |
| U-6 | Ficha de cliente (UI-09) | de ejemplo el RUC de D'CASA y el WhatsApp de la tienda en «Celular del programa» | ejemplos neutros |

Sin cambio (ya estaban bien o dependen de Odoo):

- Pedidos 17 consultas, Facturas 11, Productos 18 (+13 del panel de categorías), Socios 8, formulario
  de pedido/factura/producto 59–72 consultas: razonable para Odoo.
- **Peso del panel**: 9,3 MB sin comprimir (1,84 MB con gzip): `web.assets_web.min.js` 6,9 MB,
  CSS 1,2 MB y la hoja de impresión 1,2 MB. Lo propio de D'CASA son ~0,2 MB (1–2 %); el resto es
  Odoo y solo baja desinstalando apps (ver decisiones). Las URL llevan hash: se descarga una vez.
- **Carga del panel** (entrar → Inicio listo) sin caché: 3,7–5,2 s en local. La primera vez tras
  arrancar el servidor, las traducciones tardan ~3 s (se cachean por proceso).
- **Índices**: los campos `dcasa_` que se buscan (`dcasa_celular`, `dcasa_socio_codigo`,
  `dcasa_telefono_digitos`, `dcasa_referido_por_id`, `partner_id`/`tipo`/`estado` de los modelos de
  Socios) ya tenían índice. Faltaban solo las fechas de orden de las tres listas de Socios (P-5).
- **Cálculos guardados y crons**: ningún compute almacenado propio se recalcula de más; confirmar una
  venta cuesta ~80–90 consultas (~100 ms). Los crons propios son livianos (Socios cada hora con
  `limit=500`; R2 cada 30 min no hace nada sin credenciales; depuración mensual).
- La columna «estadísticas» de Clientes (`application_statistics`, las pastillas de ventas y
  facturas) cuesta ~40 consultas por página en frío: se dejó porque es útil.

## Qué se cambió

Commits en esta rama (todo con tests `post_install`):

1. `dcasa_interfaz/views/panel_views.xml` (nuevo) — solo vistas, acciones y menús; los permisos
   (ACL) no cambian:
   - Lista de transferencias: «Transportista» de solo lectura en la lista, así Odoo no pide
     `allowed_carrier_ids`, que se calcula fila por fila (P-1). Nueva dependencia explícita de
     `stock_delivery` (ya estaba instalado).
   - Columnas que no se usan pasan a opcionales (siguen en el menú de columnas): «Actividades» en
     cotizaciones/pedidos y clientes; avatar y país en clientes (P-2); costo en la lista de productos
     de Inventario (precio y existencias siguen a la vista; la foto y el código ya estaban).
   - Cotizaciones abre «Cotizaciones» (abiertas, de todas) en vez de «Mis cotizaciones» (U-1).
   - Ventas › Clientes con acción propia: sin filtro de facturas y creando personas (U-4).
     Facturación › Clientes queda como Odoo.
   - Menús solo para quien los usa (U-3): Sitio web (editores del sitio), Facturación › Proveedores
     y › Reportes (contabilidad), variantes y listas de precios (Gerencia).
2. `dcasa_interfaz/models/tablero.py` — semana y «Vendido hoy» en una lectura, cada venta en su día
   de Panamá (P-3); tarjeta «Mis cotizaciones» para quien no es Gerencia (U-5);
   `_dcasa_configurar_panel` (se repite en cada actualización) apaga el enriquecimiento IAP (P-4).
3. `dcasa_base` — «Ventas de hoy» como acción de servidor con los límites del día en la hora de quien
   mira (`sale.order._dcasa_accion_ventas_de_hoy`, U-2); placeholder neutro del RUC (U-6).
4. `dcasa_socios` — `index=True` en `ocurrido_en`, `registrada_en` y `solicitado_en` (P-5); placeholder
   neutro del celular (U-6). Ninguna regla del programa cambia.

Tests nuevos: `dcasa_interfaz/tests/test_panel.py` (10), `test_ventas_de_hoy_con_el_dia_de_panama`
en `dcasa_base`, `TestIndicesDeListas` en `dcasa_socios`. Los métodos nuevos son privados
(`test_superficie_rpc` no cambia). `ruff check addons` limpio.

## Mejoras más grandes que necesitan decisión de la dueña (en orden)

1. **¿La vendedora debe ver el costo?** Hoy lo ve en el formulario del producto y en Inventario
   (en la lista ya quedó oculto por defecto). Ocultarlo por grupo (solo Gerencia) es un cambio de
   permisos de campo, por eso no se hizo sin preguntar.
2. **Mermas y conteos**: la vendedora puede «Desechar» e iniciar «Inventario físico». ¿Solo Gerencia?
3. **¿Se usa CRM?** Si no, ocultar la app a las vendedoras quita 10 entradas más del menú (Mi flujo,
   Pronóstico, Leads…). Igual la app «Contactos», que duplica Ventas › Clientes.
4. **Ficha propia de socio** (UI-10): saldo, código, celular y acciones arriba, y versión para celular.
   La lista de Clientes podría mostrar «Celular del programa» y «Código de socio».
5. **Cotizaciones viejas**: «Cotizaciones abiertas» suma también las de hace meses. ¿Vencerlas solas
   según su validez (p. ej. 30 días) para que la cifra del Inicio sea la que de verdad se puede cerrar?
6. **Módulos que hablan con odoo.com** (`partner_autocomplete`, `iap`, `sms`, `snailmail`,
   `crm_iap_mine`): no se usan y envían datos a Odoo. Desinstalarlos aligera el panel y elimina
   llamadas externas; requiere probar en una copia de producción.
7. **Peso del panel**: la única palanca real es desinstalar apps que no se usen (p. ej. CRM, o
   Compras si no se usa). El código del editor del sitio va en el mismo paquete para todos: ocultar
   el menú no lo hace más liviano.
8. **Nombres de menús de Odoo** («Órdenes», «Traslados», «Órdenes para crear ventas adicionales»):
   renombrarlos a lenguaje de tienda («Pedidos», «Entregas»…) exige mantener traducciones propias.
9. **Brian para vendedoras**: hoy ven «Telegram» e «Importaciones de productos». ¿Solo Gerencia?
