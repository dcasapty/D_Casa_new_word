/**
 * Revisión adversarial (rvf) de «Busca con una foto» en el borde (fallaba con el código revisado).
 *
 * Una conexión IPv6 recibe una red /64 entera (2^64 direcciones). Con la IP completa como llave del freno, quien cambiaba
 * de dirección dentro de su /64 en cada foto nunca llegaba al límite de 6 por minuto. Ahora la llave es la /64 (I2).
 */
import { describe, expect, it, vi } from "vitest";

import { filtrarAutomatizados, LIMITES, LimitadorMemoria, RUTA_FOTO } from "../src/bots";

const SITIO = "https://dcasapty.com";

describe("rvf: freno de fotos e IPv6", () => {
  it("cambiar de dirección dentro de la misma /64 no da fotos nuevas", async () => {
    const limitador = new LimitadorMemoria(LIMITES.foto);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const estados: number[] = [];
    for (let n = 1; n <= LIMITES.foto + 2; n++) {
      const req = new Request(SITIO + RUTA_FOTO, {
        method: "POST",
        headers: { "CF-Connecting-IP": `2001:db8:1:2::${n.toString(16)}` },
        body: "foto=x",
      });
      estados.push((await filtrarAutomatizados(req, new URL(req.url), { foto: limitador }))?.status ?? 200);
    }
    warn.mockRestore();
    expect(estados.slice(LIMITES.foto)).toEqual([303, 303]);
  });
});
