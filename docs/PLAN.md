# Plan — plataforma única de D'CASA

## Punto de partida

| Fuente | Qué aporta | Estado |
|---|---|---|
| Odoo actual en dcasapty.com | Facturas (INV/2026/…), órdenes (S00…), productos, clientes | Abandonado a medias, sin código fuente |
| `juanarrietabusiness-pixel/D-Casa` | Sitio Next.js: textos, categorías, FAQ, estructura | Contenido migrado a `website_dcasa` |
| `juanarrietabusiness-pixel/Agencia_Workspace` (Dcasa/) | ADN de marca: colores, fuentes, voz, logo | Aplicado en sitio y factura |
| `abrinay1997-stack/DCasa-Referidos` | Programa de puntos y referidos de Abrinay (6 fases, reglas aprobadas) | Reglas llevadas a `dcasa_socios` — ver [SOCIOS.md](SOCIOS.md) |
| Factura INV/2026/00821 | Formato, ITBMS 7 %, combos, monto en letras | Reproducida en tests |

## Decisiones

1. **Odoo 19.0 Community** como base (versión estable con un año de correcciones;
   la 20.0 acaba de salir). Odoo va como **submódulo** en `vendor/odoo`: el código
   fuente es nuestro y no se edita; todo cambio se hace con módulos en `addons/`.
   Así las actualizaciones de Odoo no pisan nuestro trabajo.
2. **El sitio web vive dentro de Odoo** (Website + eCommerce) en lugar de Next.js:
   D'CASA puede editarlo sola con el constructor visual, y el catálogo, el stock,
   los precios y los pedidos web salen del mismo sistema que factura. El sitio
   Next.js queda como referencia de contenido.
3. **Cloudflare**: Worker delante (caché, seguridad, dominio) + **Cloudflare
   Container** con la imagen de Odoo + **PostgreSQL gestionado** (Neon/Supabase),
   porque Cloudflare no ofrece PostgreSQL propio. Detalle en [ARQUITECTURA.md](ARQUITECTURA.md).
4. **Tests obligatorios** y despliegue automático solo si todo pasa (CI en GitHub Actions).

## Fases

### Fase 1 — Base funcional ✅ (este PR)

- [x] Odoo 19 como submódulo + estructura del repo, Makefile, docker-compose.
- [x] `dcasa_base`: empresa real (RUC 155779346-2-2026 DV7), plan contable e ITBMS
      de Panamá, moneda USD, DV en contactos, apps (Ventas, Inventario, Facturación,
      Compras, CRM, Contactos), categorías de producto, español por defecto.
- [x] `dcasa_invoice`: factura con marca, RUC+DV del cliente, sello PAGADO digital
      con fecha, monto en letras en español, pie que no se corta.
- [x] `dcasa_socios`: programa de puntos y referidos de Abrinay dentro de Odoo, con puntos automáticos al
      pagarse la factura, canjes cobrados en la venta y app del socio en `/socios` (ver [SOCIOS.md](SOCIOS.md)).
- [x] `website_dcasa`: paleta y fuentes de la marca, inicio, pie, WhatsApp flotante,
      categorías de la tienda, página «Refiere y gana».
- [x] Imagen Docker + Worker/Container de Cloudflare + CI/CD con 4 etapas de pruebas.

### Fase 2 — Datos

- [ ] **Migrar los socios de DCasa-Referidos** si ya hay socios reales en su D1
      (fichas, saldos como asiento de migración; los PIN se reinician). Ver SOCIOS.md.
- [ ] **Migrar datos del Odoo actual**: clientes, productos (con códigos como
      `DSRSOQ`, `1062010735N`), combos, stock inicial y numeración de facturas
      (continuar desde la última INV/2026/…). Si el Odoo actual es *Odoo Online*
      (Enterprise), no se puede restaurar el respaldo en Community: se exporta por
      CSV/XML-RPC. Necesitamos saber dónde está alojado y un usuario administrador.
- [ ] Fotos reales de productos y ambientes (el ADN prohíbe inventarlas).

### Fase 3 — Puesta en producción

- [ ] Cuenta de Cloudflare + base PostgreSQL (Neon) + secretos en GitHub → primer despliegue.
- [ ] Mover el DNS de `dcasapty.com` a Cloudflare y activar el dominio en `edge/wrangler.jsonc`.
- [ ] Correo saliente (SMTP) para enviar facturas y cotizaciones.
- [ ] Pasarela de pago para la tienda (Yappy / tarjeta) y métodos de entrega.
- [ ] Respaldos: PITR de Neon + copia diaria a R2.
- [ ] Capacitación: vendedoras (ventas, socios y canjes), bodega (inventario), dueño (reportes).

### Fase 4 — Mejoras

- [ ] **Factura electrónica DGI (Panamá)**: la facturación electrónica es obligatoria
      para cada vez más contribuyentes. Odoo Community no trae el conector con un PAC;
      hay que validar con el contador la fecha que aplica a D'CASA y desarrollar el
      módulo `l10n_pa_edi` con el PAC que elijan.
- [ ] Punto de venta (POS) en la tienda física, si lo quieren en lugar de órdenes de venta.
- [ ] Financiamiento/crédito: plan de pagos por cliente.
- [ ] Integración WhatsApp Business (catálogo y avisos de entrega).

## Pendiente de confirmar con D'CASA

- Color oficial: el logo mide `#1648C0`/`#FFD000` y el formulario dice `#1340B1`/`#FED00F` (se usó el formulario).
- ¿Los precios publicados en la web incluyen ITBMS? Hoy se muestran sin ITBMS, como en la factura.
- Pendientes que Abrinay dejó para Marcial: tope de puntos por compra (hoy 50.000), qué
  productos entran como premio y adónde apuntan los QR impresos (usar `dcasapty.com/socios`).
