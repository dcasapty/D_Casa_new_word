# Auditoría `enterprise-gap`: productos/inventario y brecha con Odoo Enterprise

Alcance: arquitectura de productos, inventario, compras, ventas, catálogo (199 productos) y mapa de
brecha con Odoo 19 Enterprise. Auditoría **estática** (`vendor/odoo` está vacío): lo que depende del
código de Odoo y no pude leer va marcado **(por verificar)**. Fecha: 30/09/2026.

## 1. Resumen ejecutivo

1. **Hallazgo principal (CRÍTICO, por confirmar con la dueña): los precios del Excel son «+ITBMS» (sin impuesto) y el
   catálogo los carga como si ya lo incluyeran.** La hoja «Notas» del Excel dice literal: *«Todos los precios son
   +ITBMS, tal como aparecen en las fichas»*, y el encabezado es «Precio (+ITBMS)». La factura real
   INV/2026/00821 lo confirma: el combo Queen `1062010734/5/6N` está en el Excel a **$329.99**, y esa factura tiene
   base imponible **$329.99** + ITBMS $23.10 = **$353.09** (`addons/dcasa_invoice/tests/test_dcasa_invoice.py:54-56`).
   Con el código actual el cliente pagaría 329.99 en total: **7 % menos en los 199 productos**. La documentación
   afirma lo contrario (`docs/CATALOGO.md:20`, `scripts/importar_catalogo.py:11-13`) y `docs/PLAN.md:77` lo deja como pregunta abierta.
2. **Inventario y contabilidad no están enlazados todavía**: ningún producto tiene costo, proveedor, valoración,
   lote/serie, código de barras ni regla de reorden. Sin costo no hay costo de ventas ni margen real.
3. **El catálogo está bien construido** (idempotente, no pisa cambios, tests, variantes por tamaño, fotos), con
   defectos de datos puntuales (categorías mal asignadas, códigos provisionales, precios por tamaño incoherentes).
4. **Brecha Enterprise**: lo grande ya está cubierto en `dcasa_contabilidad` (reportes, conciliación, presupuestos,
   cheques). Lo que falta por orden de valor para *este* negocio: costeo/valoración y costos de importación (casi todo es
   Community, solo configurar), cuentas por cobrar con antigüedad y seguimiento de pagos, factura electrónica DGI,
   nómina, activos fijos, y luego POS/código de barras. Studio, IoT, Planning y Marketing Automation **no** valen la pena ahora.

## 2. Hallazgos de datos, inventario y arquitectura

### E-01 · CRÍTICO (por confirmar) · Precios del Excel tratados como «ITBMS incluido»
- Evidencia: Excel `up media/DCASA_listado_productos.xlsx`, hoja Notas («Todos los precios son +ITBMS»), hoja
  Productos col. C «Precio (+ITBMS)»; `addons/dcasa_catalogo/catalogo.py:50-65` (crea «ITBMS 7% incluido») y `:114`
  (`taxes_id = impuesto incluido`, `list_price = base` del Excel); `addons/dcasa_base/__init__.py:65-76` (impuesto por defecto de la
  empresa también «incluido»); `docs/CATALOGO.md:20`. Prueba real: combo Queen $329.99 = base imponible de la factura 00821.
- Efecto: si «+ITBMS» es «más ITBMS», web, cotizaciones y facturas salen 7 % por debajo (pérdida de margen en todo el catálogo).
- Arreglo (aún no en producción, es barato): **confirmar con la dueña con una factura real** (una sola pregunta). Si se confirma:
  los productos llevan el impuesto `ITBMS 7% (se suma al precio)` con `list_price` = cifra del Excel, y la web sigue mostrando
  «impuestos incluidos» (`show_line_subtotals_tax_selection`, ya configurado en `catalogo.py:152`: verá 112.34 para 104.99). Cambiar
  `catalogo.py:114`, `dcasa_base/__init__.py:65-76` y las pruebas `test_precio_con_itbms_igual_al_excel`. El precio sigue siendo «copiado, no calculado» (regla 4 de CLAUDE.md). Además los textos de combo
  («Combo con colchón $349.99») heredan la misma base: aclarar «+ITBMS» en la ficha.
- Coordinado con `contabilidad` (afecta ITBMS por pagar y el total de la factura).

### E-02 · ALTO · Sin costos, proveedores ni valoración: no hay costo de ventas ni margen
- Evidencia: `addons/dcasa_catalogo/catalogo.py:109-120` no define `standard_price` ni `seller_ids`; el Excel no trae costo
  (`scripts/importar_catalogo.py:155`: solo código, nombre, precios, combo, stock, observaciones). `grep` de `standard_price`,
  `property_valuation`, `stock_account`, `landed` en `addons/`: cero resultados. Las categorías (`dcasa_base/data/product_category_data.xml`,
  `dcasa_catalogo/data/product_category_data.xml`) no fijan método de costo ni cuentas de inventario.
- Efecto: costo 0 → el estado de resultados (`dcasa_contabilidad/models/reportes.py:185`) y la «Rentabilidad analítica» muestran margen 100 %;
  el inventario vale $0 en el balance aunque haya mercancía.
- Arreglo: en el módulo nuevo `dcasa_inventario` (ver hoja de ruta) fijar por categoría costo **promedio (AVCO)** y valoración
  automática con cuentas del plan `l10n_pa`; cargar costo y proveedor por producto (plantilla CSV que la dueña llena); comprar por órdenes de compra para que el
  costo nazca de la recepción. Comportamiento exacto de los valores por defecto de Odoo 19 en `stock_account`: (por verificar).

### E-03 · ALTO · Costos de importación sin dónde vivir
- Los códigos (`XHT022`, `ZQ…`, `HYI…`) parecen de proveedor asiático de importación. El flete, aduana y seguro cambian el costo real de cada mueble.
  Odoo Community trae `stock_landed_costs` (**Community**, no Enterprise, por verificar el nombre exacto en v19), no está en ningún `depends`
  (`addons/dcasa_base/__manifest__.py:25-34`).
- Arreglo: añadir `stock_landed_costs` a `dcasa_inventario`; prorrateo por valor o volumen.

### E-04 · MEDIO · Categorización errónea de las camas con estantes (producto estrella)
- Evidencia: `scripts/importar_catalogo.py:55-56`: la regla `estante|librero|…` va **antes** que `cama|…`. Resultado verificado en
  `addons/dcasa_catalogo/data/catalogo.json`: `1062010734/5/6N` y `1062010751/2/3/4N` («Cama con estantes», las del combo de la factura real
  00821) salen como `organizacion` (categoría interna «Estantes y organización» y categoría web equivalente), no «Recámaras y camas».
  Además el comodín `return 'organizacion'` (línea 88) oculta cualquier nombre que no calce.
- Arreglo: mover la regla `cama|camarote` antes de `estante`, o mejor, una columna `categoria` explícita en `fichas.json`; el comodín debe lanzar error/avisar en `CATALOGO_REVISAR.md`.
  Mismo patrón para `Sofá cama` (queda en salas, aceptable). Regenerar JSON y correr `actualizar_catalogo` (hoy no re-categoriza productos existentes).

### E-05 · MEDIO · Códigos provisionales y sin esquema de SKU
- Evidencia (`catalogo.json`): códigos que salen de nombres de archivo, no del proveedor: `hd`, `orlando`, `up001`, `lt-148`, `butterfly-bed`,
  `butterfly-bed-up-bed`, `clb0119018`, `SOFA-CAMA-SIN-CODIGO`; mezcla de mayúsculas/minúsculas (12 códigos) y 3 con `/` (`1062010734/5/6N`, `1062010751/2/3/4N`, `YMO-001/03`).
  `catalogo.py:144` deriva la referencia de variante como `CODIGO-TAMAÑO` y `catalogo.py:40-42` el xmlid en minúsculas: dos códigos que solo difieran en mayúsculas
  colisionarían (hoy no hay, verificado) y el segundo se omitiría en silencio (`catalogo.py:102-103`). Odoo no exige unicidad de `default_code` (no hay constraint en el catálogo).
- Sin código de barras en ningún producto (`barcode` no aparece en `catalogo.py`).
- Arreglo: definir un SKU interno D'CASA (p. ej. `CAT-000123`) y guardar el código del proveedor como `product.supplierinfo.product_code`;
  añadir `models.Constraint` único de `default_code` por empresa; generar EAN/código interno para etiquetas.

### E-06 · MEDIO · Precios por tamaño incoherentes (ya señalados, sin decisión)
- `ZEM-KING`: Queen $229.99 > King $199.99; `81904`: Queen $109.99 > King $105.99 (`docs/CATALOGO_REVISAR.md:16,18`). La dueña decidió sobre precios duplicados y fotos
  (`CATALOGO_REVISAR.md:44-46`), **no sobre estos dos ni `XHT022-F-W` sin Queen**. `catalogo.py:105-107,141` toma el mínimo como base y deja `price_extra` negativo/positivo: funciona técnicamente,
  pero sin decisión se publican precios probablemente errados.
- `ZEM-KING` (nombre «king») con variante Queen: revisar el código.

### E-07 · MEDIO · Los precios del catálogo no se pueden actualizar después de la carga
- `catalogo.py:102-103` (omite lo que existe) y `:157-185` (solo nombres, medidas, combo, categoría web): un Excel con precios nuevos no llega a Odoo.
  Es coherente con «no pisar lo de la dueña» (`docs/CATALOGO.md:30`), pero no hay otro camino (ni lista de precios).
- Arreglo: lista de precios `Catálogo proveedor` o wizard «Actualizar precios desde Excel» con vista previa y confirmación; Brian puede ejecutarlo (`actualizar_producto` ya existe).

### E-08 · MEDIO · Inventario arranca en 0, venta sin existencias y sin reorden
- `catalogo.py:113` `allow_out_of_stock_order=True` y `is_storable=True`; Excel «Stock = Sin confirmar» en los 219 registros (verificado). Decisión documentada
  (`docs/CATALOGO.md:24`), no es fallo. Consecuencia: toda entrega dejará existencias negativas hasta que se cargue el conteo inicial; no hay plantilla de inventario inicial
  ni reglas de reabastecimiento (`stock.warehouse.orderpoint`: cero en `addons/`). Brian ya ajusta existencias (`dcasa_brian/models/herramientas_catalogo.py:293-320`).
- Arreglo: conteo inicial por plantilla CSV (con costo, E-02); reglas mín/máx solo para los ~20 productos de más rotación cuando haya ventas reales; aviso de existencia negativa en el tablero.

### E-09 · BAJO · Sin lotes/series, sin multi-almacén, sin listas de precios
- Un solo almacén «D'CASA La Chorrera» (`dcasa_base/__init__.py:129-131`), sin ubicaciones (piso/bodega/dañados), sin seguimiento. Para mueblería de 1 tienda es razonable;
  **seguimiento por serie** solo valdría para colchones con garantía (opcional, Community). Lista de precios: solo se ajusta la moneda (`dcasa_base/__init__.py:42-48`); no hay
  listas (mayoristas, descuento de socios). Descuento por línea está activo (`:111`).

### E-10 · BAJO · Datos y categorías
- Categorías sin uso: Comedores, Exteriores, Electrodomésticos, Decoración (`dcasa_base/data/product_category_data.xml`), y `muebles_tv` se mapea a «Salas» interna
  (`catalogo.py:27`) aunque tiene categoría web propia. 103 de 199 productos (52 %) van a «Recámaras y camas»: demasiado ancha para reportes. Sugerencia: subcategorías (camas, mesas de noche, peinadoras, colchones).
- Sin foto: 11 productos no publicados; `CATALOGO_REVISAR.md` ya lo lista. Bien resuelto.
- `docs/ARQUITECTURA.md:38` dice que solo instala 4 módulos; `docker/entrypoint.sh:18` instala 8. Documentación desfasada (BAJO).

### E-11 · BAJO · Punto de venta (POS)
- No se usa: `dcasa_*` no depende de `point_of_sale` y el plan lo deja para fase 4 (`docs/PLAN.md:75`). El flujo actual (cotización → orden → entrega → factura → cobro en diarios
  Efectivo/Yappy/Tarjeta, `dcasa_base/__init__.py:8-12`) sirve si la caja es una vendedora con ordenador. `point_of_sale` es **Community**. No activarlo antes de decidir la factura electrónica:
  el POS debe emitir el documento fiscal que exija la DGI (validar con el contador; la obligación y el equipo fiscal no los asumo).

## 3. Lo que está bien hecho
- **Catálogo idempotente y respetuoso**: crea solo lo que falta, no pisa cambios de la dueña, con xmlid `noupdate` (`catalogo.py:92-154`, tests `test_idempotente_y_respeta_cambios`, `test_actualizar_no_pisa_cambios`).
- **Modelo de Odoo 19 correcto**: `type='consu'` + `is_storable` (`catalogo.py:111-112`), variantes por atributo «Tamaño», `price_extra` por tamaño, fotos múltiples con portada elegida.
- **No se inventa nada**: precios copiados, duplicados anotados en `CATALOGO_REVISAR.md`, medidas solo si están impresas en la foto, sin foto → sin publicar.
- Cantidades enteras (`dcasa_base/__init__.py:122-125`), almacén con nombre de la tienda, búsqueda multipalabra de variantes (`models/product.py:205-222`).
- 199 códigos únicos verificados (219 filas del Excel, 20 repetidas), sin nombres web duplicados (verificado en el JSON; hay test).
- Brian puede consultar existencias por almacén y ajustarlas con rol de gerente de inventario y nivel «sensible» (`herramientas_catalogo.py:81-92, 293-320`).
- `dcasa_contabilidad`: los reportes leen solo asientos publicados; conciliación reversible; cheque en letras. Una base sólida para reemplazar `account_reports`/`account_accountant`.

## 4. Enlace inventario ↔ contabilidad ↔ sitio web (estado actual)
| Enlace | Estado |
|---|---|
| Producto = plantilla única para inventario, ventas y web | Sí (`dcasa_catalogo` depende de `website_sale_stock`) |
| Venta web → orden → entrega → factura | Flujo estándar de Odoo; existencia 0 permitida (E-08) |
| Entrega → asiento de costo de ventas / inventario | **No configurado** (E-02): sin costo ni valoración automática |
| Compra → recepción → costo → cuenta por pagar | Módulo `purchase` instalado; sin proveedores ni costos cargados (E-02, E-03) |
| Factura → ITBMS → reporte | Sí, pero depende de E-01 |
| Factura pagada → puntos de socio | Sí (`dcasa_socios`) |
| Web → precio con ITBMS | `show_line_subtotals_tax_selection='tax_included'` (`catalogo.py:152`); correcto si E-01 se resuelve con impuesto «se suma» |

## 5. Mapa de brecha Enterprise (Odoo 19)
Leyenda: **EE** = Enterprise-only; **CE** = ya en Community; **(pv)** = por verificar en v19. Prioridad para D'CASA: P0 crítico, P1 alto, P2 medio, P3 bajo/no. Esfuerzo S (días), M (1-3 semanas), L (más de un mes).

| # | Función | ¿Enterprise? | Ya existe en `addons/` | Falta | Prior. | Esf. | Riesgo |
|---|---|---|---|---|---|---|---|
| 1 | Contabilidad completa (`account_accountant`): informes, cierres | EE (informes dinámicos `account_reports`) | `dcasa_contabilidad`: ER, balance, comprobación, mayor, ITBMS, analítica | Antigüedad de saldos (cobrar/pagar), libro de terceros, flujo de caja, cierre de ejercicio/bloqueo de fechas (fechas de bloqueo: CE (pv)) | P1 | M | Medio: cifras deben cuadrar con el contador |
| 2 | Conciliación bancaria | EE (widget) | Hecha: `conciliacion.py`, importador CSV | Reglas de conciliación guardadas, conciliación por lote; sincronización bancaria (EE y sin cobertura Panamá (pv), no hacer) | P3 | S | Bajo |
| 3 | Presupuestos | EE | `presupuesto.py` (cuenta + analítica, % ejecutado) | Alertas de sobre-ejecución, presupuesto por mes | P3 | S | Bajo |
| 4 | Cheques / lotes de pago | Impresión de cheques CE (`account_check_printing`); pago por lote EE | Formato D'CASA con letras | Depósito por lote, cheque postfechado | P3 | S | Bajo |
| 5 | Activos fijos y diferidos (`account_asset`) | EE | Nada | Depreciación de mobiliario/vehículo | P2 | M | Medio (asientos automáticos) |
| 6 | Seguimiento de cobros/fiados (`account_followup`) | EE | `facturas_pendientes` y `clientes_que_deben` de Brian | Niveles de recordatorio por WhatsApp/correo, plan de pagos (fase 4 del plan) | P1 | M | Bajo |
| 7 | Factura electrónica Panamá (`l10n_pa_edi`) | EE o no existe (pv) | Solo la pantalla «En desarrollo» (`static/src/js/en_desarrollo.js`) | Integración con PAC, CUFE, QR, notas de crédito | P0 (legal) | L | **Alto**: plazo y PAC (por definir con el contador) |
| 8 | Nómina Panamá (`hr_payroll`) | EE | Solo plan en `en_desarrollo.js` | Fichas, planilla, CSS/SE/ISR, décimo tercer mes, asiento | P1 | L | Alto: tasas validadas por contador |
| 9 | Gastos / reembolsos (`hr_expense`) | CE (pv) | Plan «reembolsos» | Conectar con nómina | P3 | S | Bajo |
| 10 | Consolidación | EE | Plan en pantalla | Solo con 2+ empresas | P3 (no aplica) | L | n/a |
| 11 | Inventario: valoración (estándar/AVCO/FIFO), costos en destino, reorden, lotes/series, multi-almacén, rutas | **CE** | Nada configurado | Configurar (E-02/E-03/E-08): casi todo es configuración + módulo `dcasa_inventario` | **P0** | M | Medio: cuentas de inventario deben mapear al plan `l10n_pa` |
| 12 | Código de barras (`stock_barcode`) | EE (la app); escaneo en POS/ventas CE | `barcode` solo en búsquedas de Brian | Etiquetas EAN, pistola en recepción/entrega; app móvil de bodega propia (PWA) | P2 | M | Bajo |
| 13 | Punto de venta | **CE** (`point_of_sale`) | No se usa (E-11) | Decidir tras factura electrónica | P2 | M | Medio: fiscal |
| 14 | Sitio web/eCommerce avanzado | Base CE; EE: A/B testing, dashboard de ventas web, suscripciones, alquiler | `website_dcasa` (portada, SEO local, datos estructurados), Yappy/pago pendiente | Pasarela Yappy/tarjeta (plan fase 3); carrito abandonado CE (pv) | P1 | M | Medio |
| 15 | Studio (personalización sin código) | EE | `dcasa_brian` «el constructor» crea registros; modo desarrollador CE edita campos/vistas, `base_automation` CE (pv) | Brian que proponga módulos/campos como parche versionado en git | P3 | L | Alto: cambios sin revisión; evitar |
| 16 | Firma electrónica (`sign`) | EE | Firma en línea de cotización: **CE** (`sale`, portal) | Firmar contratos/garantías aparte | P3 | M | Bajo |
| 17 | Documentos (`documents`) | EE | Adjuntos en base de datos (`dcasa_base`) y chatter CE | Bóveda de facturas de proveedor con OCR | P2 | M | Bajo; coste de almacenamiento en Neon |
| 18 | Helpdesk / posventa | EE | Nada; chatter CE | Garantías y reclamos: tickets simples sobre `mail.thread` propio | P2 | M | Bajo |
| 19 | WhatsApp (módulo `whatsapp`) | EE | `sale.order.action_dcasa_whatsapp` (enlace `wa.me`), botón flotante | API de WhatsApp Business (plantillas, avisos de entrega, cobros). Requiere cuenta Meta | P1 | M | Medio: cuota y política de Meta |
| 20 | Marketing automation | EE | `mass_mailing` base CE (pv), socios con cumpleaños (`dcasa_socios`) | Campañas por segmentos/puntos | P3 | M | Bajo |
| 21 | App móvil | La app oficial también conecta a Community (pv) | Interfaz responsive, Telegram + MCP (Brian) | PWA instalable para vendedoras/bodega | P2 | M | Bajo |
| 22 | Planeación/Citas/Servicio en campo | EE (pv citas) | Nada | Agenda de entregas e instalaciones (calendario de transporte) | P2 | M | Bajo |
| 23 | IoT, VoIP, Knowledge, Approvals, PLM, Calidad | EE | Nada | No aplica a la mueblería hoy | P3 | n/a | n/a |
| 24 | Informes/tableros (Spreadsheet edición) | Lectura de tableros CE; edición EE | Tablero «Inicio» propio (`dcasa_interfaz/models/tablero.py`) | Tablero de inventario y margen (depende de E-02) | P1 | S | Bajo |

## 6. Hoja de ruta priorizada (orden de construcción)

| Orden | Entrega | Por qué en este orden | Esf. | Depende de |
|---|---|---|---|---|
| 0 | **Resolver E-01** (precio con/sin ITBMS) y corregir categorías E-04, SKU E-05, tamaños E-06 | Afecta dinero en cada venta; barato antes de producción | S | Dueña + contador |
| 1 | `dcasa_inventario`: costo AVCO + valoración automática por categoría, proveedores, plantilla CSV de conteo inicial y costos, landed costs (E-02, E-03, E-08) | Sin esto no hay margen, ni balance de inventario, ni reorden | M | 0 |
| 2 | Compras reales: órdenes de compra, recepción, cuentas por pagar, reorden mín/máx en top 20 | Cierra el ciclo inventario↔contabilidad | S-M | 1 |
| 3 | Cuentas por cobrar: antigüedad de saldos, estado de cuenta de cliente, seguimiento por WhatsApp (filas 1 y 6) en `dcasa_contabilidad` | Hay ventas a crédito/financiamiento (plan fase 4) | M | 0 |
| 4 | Factura electrónica DGI (fila 7) | Obligación legal; depende de elegir PAC; trabajo largo, empezar la elección en paralelo a 1-3 | L | Contador + PAC |
| 5 | Nómina (fila 8) | Legal, pero con pocos empleados puede seguir externa al principio | L | Contador |
| 6 | Activos fijos (fila 5) y cierre de ejercicio | Útil al primer cierre anual | M | 1 |
| 7 | Pasarela de pago Yappy/tarjeta y WhatsApp Business API (filas 14, 19) | Conversión y cobranza | M | Cuentas externas |
| 8 | Código de barras y PWA de bodega; decisión POS (filas 12, 13, 21) | Cuando haya volumen de movimientos | M | 1 y 4 |
| 9 | Posventa/garantías, agenda de entregas, documentos (filas 17, 18, 22) | Mejoras | M | — |

No construir: IoT, VoIP, consolidación, Studio propio, marketing automation (filas 10, 15, 20, 23) mientras el negocio tenga una tienda y una empresa.

## 7. Cómo Brian puede ayudar a construir y operar
- **Hoy** (`dcasa_brian/models/herramientas_catalogo.py`): buscar/ver/crear/actualizar producto, publicar en web, ajustar existencias, `existencias_bajas`. Base buena para la carga de costos y el conteo inicial.
- **Carga asistida**: pegar el CSV de costos/proveedores y que Brian llame `actualizar_producto` por lotes con confirmación (nivel «sensible» si toca costo), con informe de diferencias antes de aplicar.
- **Herramientas nuevas sugeridas** (siguiendo «Para cada función nueva», `docs/BRIAN.md:92`): `margen_por_producto`, `inventario_valorizado`, `antiguedad_de_saldos`, `sugerir_reposicion`, `recordatorio_de_cobro` (prepara el mensaje de WhatsApp, no lo envía sin confirmación), `cierre_de_mes` (ya hay `guia_cierre_mes`).
- **Como constructor del repo**: Brian no debe modificar código en producción. El flujo seguro es que redacte el parche en una rama/PR con pruebas (las reglas del repo exigen un test por cambio) y una persona lo apruebe; los módulos de las filas 1-8 se prestan porque cada uno tiene reglas verificables (cuadre de balance, ITBMS, conciliación).
- **Regla «no inventar»**: para nómina, ITBMS y factura electrónica, Brian solo aplica tasas y reglas que el contador validó y que estén en un JSON versionado (mismo patrón que `puntos.json` de socios).

## 8. Preguntas abiertas para la dueña/contador
1. ¿«+ITBMS» en el Excel significa «más ITBMS» (precio sin impuesto)? Mostrar la factura 00821 como prueba. (E-01)
2. ¿Hay costos y proveedores por producto? ¿Cómo llegan los costos de importación (flete, aduana)? (E-02, E-03)
3. ¿Precio correcto de `ZEM-KING`, `81904` y el Queen de `XHT022-F-W`? (E-06)
4. ¿Fecha límite de factura electrónica para D'CASA y PAC elegido? (fila 7)
5. ¿Se vende a crédito/financiado hoy? (fila 6)
