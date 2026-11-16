/**
 * Los topes de las notas de voz en el Durable Object `Global`: las de Andrés cuentan como un mensaje (red, día, presupuesto) y tienen
 * su tope por sesión; las de Brian del panel, su tope por usuario, por día y su techo del mes. Solo horas y llaves ofuscadas: nunca el
 * audio ni el texto.
 */
import { describe, expect, it } from "vitest";
import { AlmacenGlobal, MODELO_DE_LA_VOZ, PROVEEDOR_DE_LA_VOZ, TopesDeLaTienda, type ReservaVozPanel, type ReservaVozTienda } from "../../src/motor/global";
import { USO_VACIO } from "../../src/motor/precios";
import { crearSqlNode } from "../helpers/sqlNode";

const AHORA = Date.UTC(2026, 10, 16, 15, 0);
const voz = (extra: Partial<ReservaVozTienda> = {}): ReservaVozTienda => ({
  red: "red-a",
  red48: null,
  dia: "2026-11-16",
  mes: "2026-11",
  sesion: "sesion-a",
  porSesion: 3,
  porRed: 60,
  porDia: 1000,
  porRedDia: 50,
  proveedor: PROVEEDOR_DE_LA_VOZ,
  presupuestoUsd: 30,
  reservaUsd: 0.001,
  ...extra,
});

describe("TopesDeLaTienda.reservarVoz (Andrés)", () => {
  it("el tope por sesión (por hora), con el tiempo que falta para volver a poder", () => {
    const t = new TopesDeLaTienda(crearSqlNode());
    for (let i = 0; i < 3; i++) expect(t.reservarVoz(voz(), AHORA + i * 1000).ok).toBe(true);
    const r = t.reservarVoz(voz(), AHORA + 10_000);
    expect(r).toEqual({ ok: false, motivo: "tope_sesion", reintentarEn: 3590 });
    // Otra sesión sigue pudiendo; y pasada la hora, esta también.
    expect(t.reservarVoz(voz({ sesion: "sesion-b" }), AHORA + 10_000).ok).toBe(true);
    expect(t.reservarVoz(voz(), AHORA + 3600_001).ok).toBe(true);
  });

  it("cuenta como un mensaje en los topes de red y del día (comparte la cuenta con los mensajes)", () => {
    const t = new TopesDeLaTienda(crearSqlNode());
    expect(t.reservar({ ...voz(), reservaUsd: 0 }, AHORA).ok).toBe(true);
    expect(t.reservar({ ...voz(), reservaUsd: 0 }, AHORA).ok).toBe(true);
    expect(t.reservarVoz(voz({ porRed: 2 }), AHORA)).toEqual({ ok: false, motivo: "tope_red" });
    expect(t.reservarVoz(voz({ red: "otra", porDia: 2 }), AHORA)).toEqual({ ok: false, motivo: "tope_dia" });
    // Un rechazo por red no gasta el tope de la sesión.
    expect(t.reservarVoz(voz({ red: "otra" }), AHORA).ok).toBe(true);
  });

  it("el presupuesto de la tienda: lo gastado más lo apartado más esta nota", () => {
    const t = new TopesDeLaTienda(crearSqlNode());
    const r = t.reservarVoz(voz({ presupuestoUsd: 0.0015, reservaUsd: 0.001 }), AHORA);
    expect(r.ok).toBe(true);
    expect(t.reservarVoz(voz({ sesion: "otra", presupuestoUsd: 0.0015, reservaUsd: 0.001 }), AHORA)).toEqual({ ok: false, motivo: "presupuesto" });
    expect(t.reservarVoz(voz({ presupuestoUsd: 0 }), AHORA + 1)).toEqual({ ok: false, motivo: "presupuesto" });
  });

  it("su gasto va en la tienda (renglón propio, proveedor cloudflare), suma en el presupuesto y no en las respuestas", () => {
    const t = new TopesDeLaTienda(crearSqlNode());
    const r = t.reservarVoz(voz(), AHORA);
    if (!r.ok) throw new Error("debía pasar");
    t.cerrar(r.id, [{ mes: "2026-11", proveedor: PROVEEDOR_DE_LA_VOZ, modelo: MODELO_DE_LA_VOZ, uso: USO_VACIO, usd: 0.0004, estimado: false }]);
    const g = t.gastoMes("2026-11", "2026-11-16", AHORA);
    expect(g.usd).toBeCloseTo(0.0004, 10);
    expect(g.turnos).toBe(0);
    expect(g.porModelo).toEqual([{ proveedor: "cloudflare", modelo: "notas de voz (Whisper)", usd: 0.0004, turnos: 1, estimado: false }]);
    expect(g.enVueloUsd).toBe(0);
  });

  it("la tabla de la sesión solo guarda la hora y la llave ofuscada", () => {
    const sql = crearSqlNode();
    const t = new TopesDeLaTienda(sql);
    t.reservarVoz(voz(), AHORA);
    const columnas = sql.todos<{ name: string }>("PRAGMA table_info(tienda_voz)").map((c) => c.name);
    expect(columnas.sort()).toEqual(["id", "sesion", "ts"]);
  });
});

const panel = (extra: Partial<ReservaVozPanel> = {}): ReservaVozPanel => ({
  usuario: "u1",
  dia: "2026-11-16",
  mes: "2026-11",
  porUsuarioHora: 2,
  porDia: 3,
  topeMesUsd: 5,
  concepto: "cloudflare:notas-de-voz-del-panel",
  ...extra,
});

describe("AlmacenGlobal.reservarVozPanel (Brian del panel)", () => {
  it("tope por usuario por hora y por día entre todos", () => {
    const g = new AlmacenGlobal(crearSqlNode());
    expect(g.reservarVozPanel(panel(), AHORA)).toEqual({ ok: true });
    expect(g.reservarVozPanel(panel(), AHORA + 1000)).toEqual({ ok: true });
    expect(g.reservarVozPanel(panel(), AHORA + 2000)).toEqual({ ok: false, motivo: "tope_usuario", reintentarEn: 3598 });
    expect(g.reservarVozPanel(panel({ usuario: "u2" }), AHORA)).toEqual({ ok: true });
    expect(g.reservarVozPanel(panel({ usuario: "u3" }), AHORA)).toEqual({ ok: false, motivo: "tope_dia" });
  });

  it("el techo del mes: lo anotado en su renglón de Cloudflare; 0 = apagado", () => {
    const g = new AlmacenGlobal(crearSqlNode());
    g.registrarGasto("2026-11", "cloudflare:notas-de-voz-del-panel", USO_VACIO, 5, false);
    expect(g.reservarVozPanel(panel(), AHORA)).toEqual({ ok: false, motivo: "tope_mes" });
    expect(g.reservarVozPanel(panel({ mes: "2026-12" }), AHORA)).toEqual({ ok: true });
    expect(g.reservarVozPanel(panel({ mes: "2026-12", topeMesUsd: 0, usuario: "u9" }), AHORA)).toEqual({ ok: false, motivo: "tope_mes" });
  });

  it("su gasto es de Cloudflare: no suma en el de Juan ni en sus turnos", () => {
    const g = new AlmacenGlobal(crearSqlNode());
    g.registrarGasto("2026-11", "cloudflare:notas-de-voz-del-panel", USO_VACIO, 0.002, false);
    const m = g.gastoMes("2026-11");
    expect(m.usd).toBe(0);
    expect(m.turnos).toBe(0);
    expect(m.cloudflare).toEqual([{ concepto: "cloudflare:notas-de-voz-del-panel", usd: 0.002, lecturas: 1, estimado: false }]);
  });
});
