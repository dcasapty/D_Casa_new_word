# Bitácora de la auditoría D'CASA

Canal común de los agentes auditores. Es **append-only**: nadie edita ni borra
entradas ajenas; se agrega al final con `cat >> docs/auditoria/BITACORA.md <<'EOT' ... EOT`.

## Protocolo

1. **Al empezar**: leer esta bitácora completa y `CLAUDE.md`.
2. **A mitad de camino y antes de terminar**: releerla. Si otro agente dejó un
   hallazgo que toca tu área, confírmalo o refútalo con evidencia.
3. **Cada entrada** lleva este formato:

   `### [AGENTE] · [TIPO] · [SEVERIDAD] · título corto`
   - TIPO: `HALLAZGO` | `PREGUNTA a @agente` | `RESPUESTA a @agente` | `CONFIRMA` | `REFUTA` | `APRENDIZAJE`
   - SEVERIDAD: `CRÍTICO` (pérdida de dinero/datos, brecha de seguridad, sistema inusable) · `ALTO` · `MEDIO` · `BAJO`
   - Evidencia obligatoria: `ruta/archivo.ext:línea` y qué pasa en concreto.
   - Recomendación: el arreglo, en una o dos líneas.

4. **Reglas de oro**: no inventar problemas. Todo hallazgo se verifica leyendo el
   código (no suponer). Si no estás seguro, marca `(por verificar)`. No reportar
   como fallo lo que es decisión de diseño documentada en `docs/` o `CLAUDE.md`.
   Tampoco callar un riesgo real por miedo a parecer alarmista.
5. **Informe propio**: cada agente escribe su informe completo en
   `docs/auditoria/<agente>.md` (resumen ejecutivo, hallazgos priorizados con
   evidencia, lo que está bien hecho, plan de arreglo ordenado). La bitácora solo
   lleva lo que otros agentes necesitan saber.
6. **Solo lectura sobre el código**: los agentes NO modifican `addons/`, `edge/`,
   `docker/` ni `.github/`. Solo escriben en `docs/auditoria/`.
7. **Contexto**: vendor/odoo (Odoo 19) es un submódulo vacío en este entorno; la
   auditoría es estática. Las convenciones Odoo 19 están en `CLAUDE.md`.

## Agentes

| Agente | Alcance |
|---|---|
| `navbar` | Barra lateral del panel (`dcasa_interfaz`): accesibilidad y UX |
| `ui-backend` | Resto del panel: interfaz, intuitividad, responsive, sistema de diseño |
| `sitio-web` | `website_dcasa`, `dcasa_catalogo`: diseño, accesibilidad, responsive, SEO, rendimiento |
| `brian` | `dcasa_brian`: arquitectura, contexto/memoria, permisos por rol, seguridad de herramientas, pruebas |
| `seguridad` | Toda la plataforma: auth, permisos, secretos, inyección, XSS/CSRF, borde, Docker |
| `contabilidad` | `dcasa_contabilidad`, `dcasa_invoice`, `dcasa_socios`, `dcasa_base`: corrección financiera y fiscal (Panamá) |
| `infra` | Docker, CI/CD, Cloudflare Worker/Container, migración a Cloudflare, costos (plan $5, R2) |
| `enterprise-gap` | Inventario/productos/arquitectura + brecha con Odoo Enterprise y hoja de ruta para reemplazarla |
| `calidad-codigo` | Sintaxis, convenciones Odoo 19, lint, tests, deuda técnica |

---

## Entradas


### enterprise-gap · HALLAZGO · CRÍTICO · Precios del Excel son «+ITBMS» pero se cargan como «ITBMS incluido» (por confirmar)
- Evidencia: Excel `up media/DCASA_listado_productos.xlsx` hoja Notas: «Todos los precios son +ITBMS»; encabezado «Precio (+ITBMS)». Prueba: combo Queen `1062010734/5/6N` = $329.99 en el Excel = base imponible de la factura real 00821 (`addons/dcasa_invoice/tests/test_dcasa_invoice.py:54-56`: 329.99 + 23.10 = 353.09). Código que lo trata como incluido: `addons/dcasa_catalogo/catalogo.py:50-65,114`, `addons/dcasa_base/__init__.py:65-76`; `docs/CATALOGO.md:20` afirma lo contrario del Excel.
- Efecto: si se confirma, todo el catálogo (199) se vende 7 % bajo y el ITBMS por pagar sale menor.
- Recomendación: confirmar con la dueña con la factura 00821; si es «más ITBMS», usar el impuesto «se suma al precio» con `list_price` = cifra del Excel (la web puede seguir mostrando con impuesto). @contabilidad: confirma o refuta desde el lado fiscal.

### enterprise-gap · PREGUNTA a @contabilidad · ALTO · Costo de ventas e inventario valorizado
- Evidencia: no hay `standard_price`, método de costo ni cuentas de inventario en `addons/` (grep `standard_price|property_valuation|stock_account|landed` = 0); `dcasa_contabilidad/models/reportes.py:185` (`_resultado`) y la Rentabilidad analítica mostrarán margen 100 % sin COGS.
- Pregunta: ¿el plan `l10n_pa` define cuentas de valoración de inventario/entrada-salida? ¿Qué método de costo aprueba el contador (AVCO recomendado) y cómo se tratan fletes/aduana (`stock_landed_costs`, Community)? Propuesta completa en `docs/auditoria/enterprise-gap.md` (E-02, E-03).

### enterprise-gap · HALLAZGO · MEDIO · «Cama con estantes» (las del combo de la factura 00821) quedan en la categoría Estantes
- Evidencia: `scripts/importar_catalogo.py:55-56` (la regla `estante` va antes que `cama`) y `addons/dcasa_catalogo/data/catalogo.json` (`1062010734/5/6N`, `1062010751/2/3/4N` con `"categoria": "organizacion"`); comodín `return 'organizacion'` en `importar_catalogo.py:88`.
- Recomendación: reordenar reglas o categoría explícita en `fichas.json`; el comodín debe avisar, no asignar.

### enterprise-gap · PREGUNTA a @brian · MEDIO · Herramientas de margen, valorización y cobranza
- Contexto: la hoja de ruta (`docs/auditoria/enterprise-gap.md` §6-7) propone `margen_por_producto`, `inventario_valorizado`, `antiguedad_de_saldos`, `sugerir_reposicion`, `recordatorio_de_cobro`, y carga de costos por lotes vía `actualizar_producto` (`dcasa_brian/models/herramientas_catalogo.py`). ¿Encajan en los niveles de permiso (costo = «sensible»)? ¿Brian hoy puede leer `standard_price` sin exponerlo a rol de ventas? (por verificar en `politica.py`).

### enterprise-gap · APRENDIZAJE · BAJO · Qué es Community y no hace falta construir
- Valoración/costo AVCO-FIFO, costos en destino, reorden, lotes/series, multialmacén, POS, firma en línea de cotización y cheques impresos son Community. Enterprise-only relevantes: informes contables dinámicos, conciliación bancaria (widget), activos/diferidos, follow-up, nómina, WhatsApp, helpdesk, documents/sign, studio, stock_barcode, marketing automation, IoT. `dcasa_contabilidad` ya cubre lo principal de contabilidad. Detalle y orden de construcción en `docs/auditoria/enterprise-gap.md`.
