# Prototipo: Brian nativo en Cloudflare (auditoría ronda 3)

No se despliega. Informe completo: `../brian-agente.md` (§5).

```bash
npm ci
npm run typecheck      # Worker (workers-types) + tests (node)
npm test               # 31 pruebas; BRIAN_SIN_WORKERD=1 omite las 2 que levantan workerd con `wrangler dev`
npx wrangler deploy --dry-run --outdir /tmp/brian-dist
python3 costos/calcular.py
```

- `src/nucleo/`: lógica sin dependencias de Cloudflare (bucle, ruteo, libro, confirmaciones, herramientas, Odoo JSON-2).
- `src/proveedores/`: Meta/OpenAI (Chat Completions compatible), Anthropic (Messages API), simulado.
- `src/agente.ts`, `src/libro_do.ts`, `src/index.ts`: capa Cloudflare (`agents` Agent por conversación, DO único del libro).
- `data/precios.json`: precios con fuente y fecha; `null` = PENDIENTE (no se rellena).
- Requiere Node 22 (usa `node:sqlite` en las pruebas).
