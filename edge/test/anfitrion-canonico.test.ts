/**
 * El dominio canónico (CANONICAL_HOST) es el que Odoo usa para armar sus direcciones: fotos de productos, el PDF de una cotización,
 * los webhooks. Si apunta a un dominio que todavía no existe (staging.dcasapty.com mientras staging vive en workers.dev) esas
 * direcciones no abren y Telegram no puede bajar la foto ni el PDF. El despliegue lo toma de URL_SITIO cuando nadie lo fijó a mano.
 */
import { describe, expect, it } from "vitest";
import desplegar from "../../.github/workflows/desplegar.yml?raw";
import wranglerJsonc from "../wrangler.jsonc?raw";

describe("CANONICAL_HOST en el despliegue", () => {
  it("si la variable está vacía, el despliegue usa el anfitrión de URL_SITIO", () => {
    expect(desplegar).toMatch(/if \[ -z "\$\{CANONICAL_HOST:-\}" \] && \[ -n "\$\{URL_SITIO:-\}" \]/);
    expect(desplegar).toContain('anfitrion="${URL_SITIO#*://}"');
    expect(desplegar).toContain('anfitrion="${anfitrion%%/*}"');
    expect(desplegar).toContain('CANONICAL_HOST="$anfitrion"');
  });

  it("solo acepta un nombre de dominio válido (nada de rutas, puertos ni espacios)", () => {
    expect(desplegar).toContain('[[ "$anfitrion" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]]');
  });

  it("lo hace ANTES de armar los argumentos de wrangler, que es donde se pasa --var CANONICAL_HOST", () => {
    const derivar = desplegar.indexOf('CANONICAL_HOST="$anfitrion"');
    const armar = desplegar.indexOf("args=(--config wrangler.desplegar.json --secrets-file");
    const pasar = desplegar.indexOf("for name in CANONICAL_HOST");
    expect(derivar).toBeGreaterThan(-1);
    expect(derivar).toBeLessThan(armar);
    expect(armar).toBeLessThan(pasar);
  });

  it("wrangler.jsonc sigue con los dominios definitivos (la derivación solo se usa si la variable está vacía)", () => {
    expect(wranglerJsonc).toContain('"CANONICAL_HOST": "dcasapty.com"');
    expect(wranglerJsonc).toContain('"CANONICAL_HOST": "staging.dcasapty.com"');
  });
});
