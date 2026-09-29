# CLAUDE.md — reglas de este repositorio

## Proyecto

ERP + sitio web de **D'CASA Panamá** (retail de muebles, La Chorrera) sobre
**Odoo 19 Community**, desplegado en **Cloudflare** (Worker + Container).

## Estructura

- `vendor/odoo` — Odoo 19.0 como submódulo. **No se modifica nunca.** Para
  cambiar comportamiento se hereda desde un módulo en `addons/`.
- `addons/` — módulos propios, prefijo `dcasa_` (o `website_dcasa`). Campos nuevos
  en modelos de Odoo llevan prefijo `dcasa_` (o `l10n_pa_` si es de localización).
- `edge/` — Worker de Cloudflare (TypeScript). La lógica testeable vive en
  `src/routing.ts` y `src/handler.ts`, sin dependencias de Cloudflare.
- `docker/` — imagen de producción; `entrypoint.sh` instala/actualiza módulos.

## Comandos

- `scripts/test.sh [modulos]` — instala en base limpia y corre tests (PostgreSQL local).
- `make run DB=dcasa` / `make init` / `make update` — ver `Makefile`.
- `cd edge && npm test && npm run typecheck`.
- `ruff check addons`.

## Convenciones Odoo 19

- Vistas `<list>` (no `<tree>`), `invisible="expr"` (no `attrs`), `<chatter/>`.
- Constraints SQL con `models.Constraint(...)` (no `_sql_constraints`).
- `res.users.group_ids` (no `groups_id`). `self.env._('...')` para textos traducibles.
- Tests: `@tagged('post_install', '-at_install')`. Todo cambio lleva test.
- Adjuntos en base de datos (`ir_attachment.location = db`): el contenedor no tiene disco persistente.

## Reglas de marca (ADN: Agencia_Workspace/Dcasa)

1. Azul `#1340B1`, amarillo `#FED00F`. **El amarillo nunca toca el blanco**: CTAs
   amarillos solo sobre azul; texto sobre blanco en azul o navy.
2. Anton (titulares, caja alta) · Oswald (subtítulos) · Inter (cuerpo).
3. Sistema plano: sin degradados ni sombras dramáticas.
4. **No inventar contenido**: ni precios, ni cifras, ni testimonios.
5. CTA único: **Escríbenos por WhatsApp** (+507 6026-1919, configurable en el sitio).
6. Voz: el pana que sabe de casas; tuteo; nada de "remate" ni "¡¡CORRE!!".

## Datos reales de la empresa

D'CASA Panamá · RUC 155779346-2-2026 DV7 · Avenida Las Américas, Urbanización
Santa Clara, Local 4550 PB-1, La Chorrera · +507 6026-1919 · info@dcasapty.com.
