## Resumen

<!-- ¿Qué cambia y por qué? Dos o tres frases, en español. -->

## Cambios

<!-- Lista corta: módulos, modelos, vistas, rutas, edge/, docker/, docs/. -->

-

## Brian

Toda función nueva de la plataforma tiene que poder usarla Brian (ver `docs/BRIAN.md`).

- **¿Qué herramienta nueva o cambiada?** <!-- nombre (verbo_objeto), archivo herramientas_*.py -->
- **Nivel de permiso:** <!-- lectura · construccion · sensible (pide confirmación) -->
- **Grupos que la ven:** <!-- p. ej. sales_team.group_sale_salesman -->
- **Qué NO puede hacer:** <!-- límites y prohibiciones que aplica (politica.py) -->
- **Si no lleva herramienta, por qué:** <!-- p. ej. es solo estética del sitio web -->

## Pruebas

<!-- Comandos que corriste y resultado. -->

- [ ] `scripts/test.sh <módulos>`
- [ ] `ruff check addons`
- [ ] `cd edge && npm test && npm run typecheck` (si toca el Worker)

## Capturas

<!-- Pantallas del panel, del sitio, del chat de Brian o de Telegram, si aplica. -->

## Checklist

- [ ] La función nueva tiene herramienta de Brian o se explica por qué no
- [ ] Respeta `docs/BRIAN.md` (niveles y prohibiciones)
- [ ] Tests
- [ ] Sin secretos en el repo (claves, tokens, contraseñas: solo como secretos de Cloudflare / GitHub)
- [ ] Reglas de marca y de Socios de `CLAUDE.md` (sin cifras ni contenido inventado)
