import { describe, expect, it } from "vitest";

describe.skipIf(!process.env.ODOO_INTEGRACION_URL)("humo", () => {
  it("Odoo responde", async () => {
    const r = await fetch(`${process.env.ODOO_INTEGRACION_URL}/web/health`);
    expect(r.status).toBe(200);
  });
});
