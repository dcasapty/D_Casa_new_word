/**
 * Issue #24 · Messenger e Instagram: Meta devuelve por el webhook el ECO de lo que manda la Página (`is_echo`, `propio: true`), y a
 * veces llega ANTES de que la Send API conteste o entre una burbuja y otra. Si el motor no sabe todavía que eso lo mandó él, lo toma
 * por una vendedora escribiendo desde la bandeja de Meta (`humanoIntervino`) y el bot calla 120 minutos tras su primera respuesta.
 * Lo que va a salir se anota ANTES de enviarlo (como hace el puente de WhatsApp con sus ids).
 */
import { describe, expect, it } from "vitest";
import { sinNegritas, type CanalId, type Entrante, type ResultadoEnvio, type Saliente } from "../../src/canales/tipos";
import { crearMundo, type Mundo } from "../helpers/mundo";

function mundoMeta(canal: CanalId = "messenger") {
  const m = crearMundo({ canal, idExterno: "PSID-1", config: { canales_activos: { [canal]: true } } });
  m.canal.cap = { ...m.canal.cap, ventana24h: true, maxTexto: 1900 };
  return m;
}

/** El eco de Meta: lo escribió la Página (sin la negrita de WhatsApp, que Meta no entiende), con un `mid` que el motor aún no conoce. */
let n = 0;
const ecoDe = (m: Mundo, extra: Partial<Entrante>): Entrante => m.entrante(undefined, { propio: true, id_mensaje: `m_eco_${++n}`, nombre: undefined, ...extra });

/** Mientras el canal envía, Meta ya entrega los ecos de lo que se está mandando (y el motor los atiende en paralelo). */
function ecosDuranteElEnvio(m: Mundo, ecos: (s: Saliente) => Entrante[]) {
  const acciones: string[] = [];
  const enviar = m.canal.enviar.bind(m.canal);
  m.canal.enviar = async (canal: CanalId, salida: Saliente): Promise<ResultadoEnvio> => {
    for (const e of ecos(salida)) acciones.push((await m.motor.ingest(e)).accion);
    return enviar(canal, salida);
  };
  return acciones;
}

describe("el eco del propio bot en Messenger e Instagram (issue #24)", () => {
  for (const canal of ["messenger", "instagram"] as const) {
    it(`${canal}: el eco de la respuesta que llega MIENTRAS se envía no calla al bot`, async () => {
      const m = mundoMeta(canal);
      m.guion([{ texto: "Claro, tenemos camas queen.\n\nSi prefieres, escribe *persona* y te atiende una vendedora." }, { texto: "La queen mide 160 x 200 cm." }]);
      const acciones = ecosDuranteElEnvio(m, (s) => s.burbujas.map((b) => ecoDe(m, { texto: sinNegritas(b) })));
      await m.conversar("hola, ¿tienen camas queen?");
      expect(acciones.length).toBeGreaterThan(0);
      expect(acciones.every((a) => a === "eco")).toBe(true);
      expect(m.motor.silencio()).toBe(false);
      expect(m.odoo.mensajes.filter((x) => x.autor === "vendedora")).toHaveLength(0);
      // Y el bot sigue contestando el siguiente mensaje (antes callaba 120 minutos).
      const antes = m.canal.salidas.length;
      await m.conversar("¿y cuánto mide?");
      expect(m.canal.salidas.length).toBe(antes + 1);
    });
  }

  it("la foto que manda el bot vuelve como eco sin texto, y tampoco es una vendedora", async () => {
    const m = mundoMeta();
    m.guion([
      { llamadas: [{ nombre: "ver_producto", args: { codigo: "CAMA-Q-001" } }] },
      { llamadas: [{ nombre: "enviar_foto_producto", args: { codigo: "CAMA-Q-001" } }] },
      { texto: "Te mando la foto de la Cama Queen Milán." },
    ]);
    const acciones = ecosDuranteElEnvio(m, (s) => s.medios.map(() => ecoDe(m, { adjuntos: [{ tipo: "imagen", url: "https://cdn.fbsbx.com/eco.jpg" }] })));
    await m.conversar("¿me mandas la foto de la cama CAMA-Q-001?");
    expect(m.canal.salidas.at(-1)?.medios).toHaveLength(1);
    expect(acciones).toEqual(["eco"]);
    expect(m.motor.silencio()).toBe(false);
  });

  it("después del envío, el eco sin la negrita (y sin id conocido) se sigue reconociendo como propio", async () => {
    const m = mundoMeta();
    m.canal.idsDevueltos = false;
    m.guion([{ texto: "Si prefieres, escribe *persona* y te atiende una vendedora." }]);
    await m.conversar("hola");
    const r = await m.motor.ingest(ecoDe(m, { texto: "Si prefieres, escribe persona y te atiende una vendedora." }));
    expect(r.accion).toBe("eco");
    expect(m.motor.silencio()).toBe(false);
  });

  it("una vendedora que escribe de verdad desde la bandeja de Meta, aun en pleno envío del bot, sí calla al bot", async () => {
    const m = mundoMeta();
    m.guion([{ texto: "Claro, tenemos camas queen." }]);
    const acciones = ecosDuranteElEnvio(m, () => [ecoDe(m, { texto: "Hola, soy Ana de D'CASA, te atiendo yo." })]);
    await m.conversar("hola");
    expect(acciones).toEqual(["propio"]);
    expect(m.motor.silencio()).toBe(true);
  });

  it("una foto que una vendedora manda después de que el bot terminó de enviar sí es de ella (lo «en vuelo» se suelta al terminar)", async () => {
    const m = mundoMeta();
    m.guion([
      { llamadas: [{ nombre: "ver_producto", args: { codigo: "CAMA-Q-001" } }] },
      { llamadas: [{ nombre: "enviar_foto_producto", args: { codigo: "CAMA-Q-001" } }] },
      { texto: "Te mando la foto." },
    ]);
    await m.conversar("¿me mandas la foto de la cama CAMA-Q-001?");
    await m.pasar(60_000);
    const r = await m.motor.ingest(ecoDe(m, { adjuntos: [{ tipo: "imagen", url: "https://cdn.fbsbx.com/de-ana.jpg" }] }));
    expect(r.accion).toBe("propio");
  });

  it("lo «en vuelo» de un envío que se cortó por un reinicio vence solo (no se queda tragando mensajes de las vendedoras)", async () => {
    const m = mundoMeta();
    m.guion([
      { llamadas: [{ nombre: "ver_producto", args: { codigo: "CAMA-Q-001" } }] },
      { llamadas: [{ nombre: "enviar_foto_producto", args: { codigo: "CAMA-Q-001" } }] },
      { texto: "Te mando la foto." },
    ]);
    let cortar = true;
    const enviar = m.canal.enviar.bind(m.canal);
    m.canal.enviar = async (canal: CanalId, salida: Saliente) => {
      if (cortar) {
        cortar = false;
        await new Promise<never>(() => {}); // el objeto se reinició a mitad del envío: nunca vuelve
      }
      return enviar(canal, salida);
    };
    void m.conversar("hola");
    for (let i = 0; i < 50; i++) await new Promise((r) => setTimeout(r, 0));
    await m.pasar(10 * 60_000);
    const r = await m.motor.ingest(ecoDe(m, { adjuntos: [{ tipo: "imagen", url: "https://cdn.fbsbx.com/de-ana.jpg" }] }));
    expect(r.accion).toBe("propio");
  });
});
