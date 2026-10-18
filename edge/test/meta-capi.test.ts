import { describe, expect, it, vi } from "vitest";

import {
  SECRETOS_PARA_ARRANCAR,
  VARIABLES_DEL_CONTENEDOR,
  handleRequest,
  respuestaArrancando,
  respuestaSalud,
  secretosFaltantes,
  variablesDelContenedor,
} from "../src/handler";

// Token de Meta inventado para la prueba (no es de nadie).
const TOKEN_META = "EAAprueba0000000000000000000000000000tokendemeta";
const SECRETOS = {
  ADMIN_PASSWORD: "clave-admin",
  R2_ENDPOINT: "https://cuenta.r2.cloudflarestorage.com",
  R2_BUCKET: "dcasa-respaldos",
  R2_ACCESS_KEY_ID: "id",
  R2_SECRET_ACCESS_KEY: "secreto",
  PGBACKREST_CIPHER_PASS: "cifrado",
};

describe("META_CAPI_TOKEN (Conversions API de Meta, docs/META_EVENTOS.md)", () => {
  it("llega al contenedor cuando existe; vacío no se pasa", () => {
    expect(VARIABLES_DEL_CONTENEDOR).toContain("META_CAPI_TOKEN");
    expect(variablesDelContenedor({ ...SECRETOS, META_CAPI_TOKEN: TOKEN_META }).META_CAPI_TOKEN).toBe(TOKEN_META);
    expect(variablesDelContenedor({ ...SECRETOS, META_CAPI_TOKEN: "" })).not.toHaveProperty("META_CAPI_TOKEN");
    expect(variablesDelContenedor(SECRETOS)).not.toHaveProperty("META_CAPI_TOKEN");
  });

  it("es opcional: sin él el contenedor arranca igual", () => {
    expect(SECRETOS_PARA_ARRANCAR).not.toContain("META_CAPI_TOKEN");
    expect(secretosFaltantes(SECRETOS)).toEqual([]);
  });

  it("nunca aparece en una respuesta al navegador (salud, arranque, ni lo que contesta Odoo)", async () => {
    const env = { ...SECRETOS, META_CAPI_TOKEN: TOKEN_META };
    // /__edge/health con el contenedor apagado, con secretos que faltan y con Odoo respondiendo.
    const respuestas: Response[] = [
      respuestaSalud({ contenedor: "stopped", faltan: secretosFaltantes({ ...env, R2_BUCKET: "" }) }),
      respuestaSalud({ contenedor: "healthy", faltan: secretosFaltantes(env), odoo: { status: 200, cuerpo: '{"base":"ok"}' } }),
      respuestaArrancando(new Request("https://dcasapty.com/shop")),
    ];
    const forward = vi.fn(async () => new Response("<html>tienda</html>", { status: 200 }));
    respuestas.push(
      await handleRequest(new Request("https://dcasapty.com/__edge/health"), {
        forward,
        salud: async () => ({ contenedor: "healthy", faltan: secretosFaltantes(env), odoo: { status: 200 } }),
      }),
      await handleRequest(new Request("https://dcasapty.com/shop"), { forward }),
    );
    for (const respuesta of respuestas) {
      const texto = await respuesta.text();
      const cabeceras = JSON.stringify([...respuesta.headers.entries()]);
      expect(texto).not.toContain(TOKEN_META);
      expect(texto).not.toContain("META_CAPI_TOKEN");
      expect(cabeceras).not.toContain(TOKEN_META);
    }
  });
});
