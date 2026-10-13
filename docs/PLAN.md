# Plan — plataforma única de D'CASA

Puesto al día el 2026-10-12. Este documento tiene tres partes: de dónde se partió, qué se decidió y
**en qué va cada fase**. El detalle de lo que falta decidir o hacer la dueña está en
[PENDIENTES_DUENA.md](PENDIENTES_DUENA.md); la evaluación de cómo está todo, en [ESTADO.md](ESTADO.md).

## Punto de partida

| Fuente | Qué aporta | Estado |
|---|---|---|
| Odoo anterior en dcasapty.com | Facturas (INV/2026/…), órdenes (S00…), productos, clientes | Abandonado a medias, sin código fuente |
| `juanarrietabusiness-pixel/D-Casa` | Sitio Next.js: textos, categorías, FAQ, estructura | Contenido migrado a `website_dcasa` |
| `juanarrietabusiness-pixel/Agencia_Workspace` (Dcasa/) | ADN de marca: colores, fuentes, voz, logo | Aplicado en sitio, factura y panel |
| `abrinay1997-stack/DCasa-Referidos` | Programa de puntos y referidos de Abrinay (6 fases, reglas aprobadas) | Reglas llevadas a `dcasa_socios` — ver [SOCIOS.md](SOCIOS.md) |
| Factura INV/2026/00821 | Formato, ITBMS 7 %, combos, monto en letras | Reproducida en tests |

## Decisiones

1. **Odoo 19.0 Community** como base. Va como **submódulo** en `vendor/odoo`: el código fuente es
   nuestro y no se edita; todo cambio se hace con módulos en `addons/`. Así las actualizaciones de Odoo
   no pisan nuestro trabajo.
2. **El sitio web vive dentro de Odoo** (Website + eCommerce) en lugar de Next.js: el catálogo, el stock,
   los precios y los pedidos salen del mismo sistema que factura. El sitio Next.js queda como referencia
   de contenido. (Hoy el sitio se mantiene desde el código; el editor visual del panel está limitado a
   propósito: [auditoria/ronda7/constructor-web.md](auditoria/ronda7/constructor-web.md).)
3. **Cloudflare**: Worker delante (caché, seguridad, dominio) + **Container con Odoo y PostgreSQL
   adentro**, con respaldo continuo a R2. *Esta decisión cambió:* el plan original preveía una base
   gestionada (Neon/Supabase); se descartó por costo. Detalle en [ARQUITECTURA.md](ARQUITECTURA.md) y
   [auditoria/DECISION_Y_PLAN.md](auditoria/DECISION_Y_PLAN.md).
4. **Tests obligatorios** y despliegue automático solo si todo pasa (CI en GitHub Actions).
5. **Odoo se queda como sistema de gestión** (contabilidad, facturación, inventario, CRM); no se
   reconstruye fuera de él.

## Fases

Leyenda: ✅ hecho · 🟡 hecho en parte · ⬜ pendiente.

### Fase 1 — Base funcional ✅

- ✅ Odoo 19 como submódulo + estructura del repo, Makefile, docker-compose.
- ✅ `dcasa_base`: empresa real (RUC 155779346-2-2026 DV7), plan contable e ITBMS de Panamá, moneda USD,
  DV en contactos, apps (Ventas, Inventario, Facturación, Compras, CRM, Contactos), español por defecto.
- ✅ `dcasa_invoice`: factura con marca, RUC+DV del cliente, sello PAGADO digital con fecha, monto en
  letras en español, pie que no se corta.
- ✅ `dcasa_socios`: programa de puntos y referidos dentro de Odoo, con puntos automáticos al pagarse la
  factura, canjes cobrados en la venta y app del socio en `/socios` ([SOCIOS.md](SOCIOS.md)).
- ✅ `website_dcasa`: paleta y fuentes de la marca, inicio, pie, WhatsApp flotante, categorías de la
  tienda, página «Refiere y gana».
- ✅ Imagen Docker + Worker/Container de Cloudflare + CI/CD con etapas de pruebas.

### Fase 2 — Datos 🟡

- ⬜ **Socios de DCasa-Referidos**: migrarlos si ya hay socios reales en su D1 (fichas, saldos como
  asiento de migración; los PIN se reinician). Ver [SOCIOS.md](SOCIOS.md).
- 🟡 **Datos del Odoo anterior.**
  - ✅ Catálogo: `dcasa_catalogo` crea los productos con sus fotos ([CATALOGO.md](CATALOGO.md)).
  - 🟡 Existencias y costos: salen de capturas del sistema anterior, con lecturas dudosas y decisiones
    pendientes de la dueña ([inventario-anterior-informe.md](inventario-anterior-informe.md),
    [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md) puntos 1 a 4). Falta un conteo físico completo (el Escáner de [BARRAS.md](BARRAS.md) ya permite hacerlo).
  - ⬜ Clientes, historial de facturas y numeración (continuar desde la última INV/2026/…).
  - ⬜ Contactos repetidos del sistema anterior: lista de duplicados en Socios › Configuración
    ([CONTACTOS.md](CONTACTOS.md)).
- 🟡 **Fotos reales**: hay las del proveedor; falta la sesión de fotos propia (el ADN prohíbe inventarlas).

### Fase 3 — Puesta en producción 🟡

- 🟡 Cloudflare, R2, secretos de GitHub y despliegue: funcionando en **staging**. **Producción todavía no se ha
  desplegado nunca** (no existe el Worker `dcasa`); sus secretos obligatorios están cargados desde 2026-10-13. A
  producción se sale a mano (*Run workflow* → `desplegar_en = produccion`, desde `main`): un merge no despliega.
- ⬜ **Cargar los datos reales del Odoo anterior** (exportación en JSON/CSV: contactos, productos, existencias,
  facturas): importador, ensayo en staging y carga el día del corte. Antes: decidir con el contador si el historial de
  facturas se carga como facturas o como saldos iniciales.
- ⬜ Mover el DNS de `dcasapty.com` a Cloudflare y activar el dominio en `edge/wrangler.jsonc`.
- ⬜ Correo saliente (SMTP) para enviar facturas y cotizaciones (hoy no hay servidor de correo saliente).
- ⬜ Pasarela de pago para la tienda (Yappy / tarjeta) y métodos de entrega.
- ✅ Respaldos: WAL continuo y `pg_dump` diario cifrados a R2, con simulacro de restauración en cada
  ejecución de CI ([OPERACION.md](OPERACION.md)). *(Reemplaza el «PITR de Neon» del plan original.)*
- ⬜ Capacitación: vendedoras (ventas, socios y canjes, Escáner), bodega (inventario), dueña (reportes).
- 🟡 Seguridad de acceso: doble factor y puerta del equipo construidos; en staging, la puerta está en modo
  «avisar» y producción los tiene apagados ([SEGURIDAD_ACCESO.md](SEGURIDAD_ACCESO.md)).

### Fase 4 — Mejoras 🟡

- 🟡 **Factura electrónica DGI (Panamá)**: `dcasa_fe_pa` está listo y apagado; falta elegir el PAC y
  confirmar con el contador la fecha que aplica a D'CASA ([FACTURA_ELECTRONICA.md](FACTURA_ELECTRONICA.md)).
- ⬜ Punto de venta (POS) en la tienda física, si lo quieren en lugar de órdenes de venta.
- ⬜ Financiamiento/crédito: plan de pagos por cliente.
- ✅ WhatsApp y mensajería: **Juan**, el asistente de los clientes, con puente de WhatsApp por QR
  ([JUAN.md](JUAN.md)); el plan B con la cuenta oficial de Meta está documentado
  ([JUAN_PLAN_B.md](JUAN_PLAN_B.md)).

## Construido fuera del plan original

| Qué | Dónde |
|---|---|
| **Brian**, asistente de IA para el equipo (panel, Telegram, MCP) | [BRIAN.md](BRIAN.md) |
| **CRM automático** (etapas por hechos, temperatura, «a quién escribirle hoy») | [CRM_AUTOMATICO.md](CRM_AUTOMATICO.md) |
| Contabilidad a medida, consolidación de empresas y nómina de Panamá | [CONTABILIDAD.md](CONTABILIDAD.md) · [CONSOLIDACION.md](CONSOLIDACION.md) · [NOMINA.md](NOMINA.md) |
| Contactos sin duplicados | [CONTACTOS.md](CONTACTOS.md) |
| El equipo en Odoo (Empleados) | [EQUIPO.md](EQUIPO.md) |
| **Lector de códigos de barras**: Escáner, conteo y etiquetas numeradas | [BARRAS.md](BARRAS.md) |
| Interfaz propia del panel (inicio, íconos, favicon) | `addons/dcasa_interfaz` |
| Caché de páginas en el borde, adjuntos en R2, sesiones en PostgreSQL | [ARQUITECTURA.md](ARQUITECTURA.md) |

## Resuelto con D'CASA

- ITBMS (2026-10-01, la dueña): los precios del Excel y del catálogo son **sin ITBMS** y el 7 % se suma
  encima (factura INV/2026/00821: 329.99 + 23.10 = 353.09). La web muestra «$39.99 + ITBMS»; carrito,
  cotización y factura muestran subtotal, ITBMS y total.
- Etiquetas de códigos de barras (2026-10-11): un rollo numerado del proveedor de etiquetas (`DC0001`…),
  asignado producto por producto desde el Escáner. Ver [BARRAS.md](BARRAS.md).

## Pendiente de confirmar con D'CASA

- Color oficial: el logo mide `#1648C0`/`#FFD000` y el formulario dice `#1340B1`/`#FED00F` (se usó el formulario).
- Pendientes que Abrinay dejó para Marcial: tope de puntos por compra (hoy 50.000), qué productos entran
  como premio y adónde apuntan los QR impresos (usar `dcasapty.com/socios`).
