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

