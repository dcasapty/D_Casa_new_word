# Auditorías y decisiones de arquitectura

Registro de cómo se llegó al sistema actual: auditorías hechas por rondas (la última, el 2026-10-10), su
bitácora y la decisión de arquitectura. **Son registros históricos**: describen el sistema en el momento en que
se escribieron. Siguen aquí porque el código, los scripts y los demás documentos los citan (por ejemplo
`docs/auditoria/ronda3/datos.md`). Si algo difiere de la documentación vigente, manda la vigente
([`../README.md`](../README.md)).

**Lo que sigue vivo** de estas auditorías está en los issues del repositorio (hallazgos que quedaron para después)
y en [`../PENDIENTES_DUENA.md`](../PENDIENTES_DUENA.md).

## Para empezar

| Documento | Qué es |
|---|---|
| [DECISION_Y_PLAN.md](DECISION_Y_PLAN.md) | La decisión de arquitectura (todo en Cloudflare, PostgreSQL en el contenedor) y sus mediciones. |
| [INFORME_FINAL.md](INFORME_FINAL.md) | Síntesis de la primera auditoría (9 agentes): veredicto, causa común de los fallos de seguridad y plan por prioridad. |
| [BITACORA.md](BITACORA.md) | El registro de hallazgos y aprendizajes de todas las rondas, en orden. |

## Primera auditoría (informes por área)

[seguridad.md](seguridad.md) · [calidad-codigo.md](calidad-codigo.md) · [infra.md](infra.md) ·
[contabilidad.md](contabilidad.md) · [enterprise-gap.md](enterprise-gap.md) (brecha con Odoo Enterprise) ·
[sitio-web.md](sitio-web.md) · [ui-backend.md](ui-backend.md) · [navbar.md](navbar.md) · [brian.md](brian.md)

## Rondas

| Ronda | Tema | Informes |
|---|---|---|
| 2 | Brian (modelos, eventos, lectura de Excel, pruebas) y costos de Cloudflare | [`ronda2/`](ronda2/): `brian-evals`, `brian-eventos`, `brian-excel`, `brian-modelos`, `cf-costos`; el prototipo del extractor de Excel está en `brian-excel-prototipo/` |
| 3 | Dónde vive la base, Odoo medido de verdad, sitio en el borde, motor de documentos de Brian | [`ronda3/`](ronda3/): `datos`, `odoo-medicion`, `cf-plataforma`, `reconstruccion`, `sitio-edge`, `brian-agente`, `brian-documentos`, `brian-habilidades` (cada uno con sus prototipos y medidas) |
| 4 | Costos que crecen, rendimiento, borrar conversaciones de Brian | [`ronda4/`](ronda4/) |
| 5 | Pagos en línea, apartados y abonos | [`ronda5/pagos-y-apartados.md`](ronda5/pagos-y-apartados.md) |
| 6 | Auditoría final de la integración, diseño, panel, contabilidad, Brian | [`ronda6/`](ronda6/) |
| 7 | Constructor web, Juan (CRM de WhatsApp), factura, Socios en la web | [`ronda7/`](ronda7/) (con facturas y cotización de muestra) |
| 8 | CRM, Juan y Brian | [`ronda8/crm-juan-brian.md`](ronda8/crm-juan-brian.md) |

## Reglas para esta carpeta

- No se borran informes ni prototipos: otros archivos los citan por ruta.
- Un hallazgo nuevo va a un issue; cuando se corrige, el issue se cierra con un comentario. Esta carpeta no se
  reescribe para reflejarlo.
- Los prototipos (`*-prototipo/`, `brian-agente/`, `brian-documentos/`, `datos/`, `odoo-medicion/`…) son experimentos de
  medición; no forman parte del sistema que se despliega.
