import { describe, expect, it } from "vitest";
import { LATIDOS_ANTES_DE_REINICIAR } from "../src/comun";
import { aplicarVigilancia, diarioNuevo, normalizarDiario, resumirEstado } from "../src/vigilancia";

const T0 = 1_800_000_000_000;
const MIN = 60_000;

describe("aplicarVigilancia: qué hacer en cada latido", () => {
  it("sano: todo al día, nada que hacer", () => {
    const { diario, accion } = aplicarVigilancia(diarioNuevo(), "sano", T0);
    expect(accion).toBe("nada");
    expect(diario).toMatchObject({ desconectadoSeguidos: 0, sinConexionDesde: null });
    expect(diario.ultimaConexionVista).toBe(new Date(T0).toISOString());
  });

  it("caído: primero se pide reconectar (lo barato) y se anota desde cuándo no hay conexión", () => {
    const r = aplicarVigilancia(diarioNuevo(), "caido", T0);
    expect(r.accion).toBe("pedir_reconexion");
    expect(r.diario).toMatchObject({ desconectadoSeguidos: 1, sinConexionDesde: T0 });
    // «desde cuándo» no se pisa en los latidos siguientes
    const r2 = aplicarVigilancia(r.diario, "caido", T0 + 30_000);
    expect(r2.diario.sinConexionDesde).toBe(T0);
    expect(r2.diario.desconectadoSeguidos).toBe(2);
  });

  it(`tras ${LATIDOS_ANTES_DE_REINICIAR} latidos caídos seguidos, el martillo (y la cuenta vuelve a cero)`, () => {
    let d = diarioNuevo();
    const acciones: string[] = [];
    for (let i = 0; i < LATIDOS_ANTES_DE_REINICIAR; i++) {
      const r = aplicarVigilancia(d, "caido", T0 + i * 30_000);
      acciones.push(r.accion);
      d = r.diario;
    }
    expect(acciones.slice(0, -1).every((a) => a === "pedir_reconexion")).toBe(true);
    expect(acciones.at(-1)).toBe("reiniciar");
    expect(d).toMatchObject({ reiniciosForzados: 1, desconectadoSeguidos: 0 });
  });

  it("un latido sano en medio corta la racha", () => {
    let d = diarioNuevo();
    for (let i = 0; i < LATIDOS_ANTES_DE_REINICIAR - 1; i++) d = aplicarVigilancia(d, "caido", T0).diario;
    d = aplicarVigilancia(d, "sano", T0).diario;
    expect(d.desconectadoSeguidos).toBe(0);
    expect(aplicarVigilancia(d, "caido", T0).accion).toBe("pedir_reconexion");
  });

  it("esperando a una persona (QR / desvinculado): NUNCA se reinicia (tumbaría el QR que está mirando)", () => {
    let d = diarioNuevo();
    for (let i = 0; i < 50; i++) {
      const r = aplicarVigilancia(d, "esperando-a-una-persona", T0 + i * 30_000);
      expect(r.accion).toBe("nada");
      d = r.diario;
    }
    expect(d.reiniciosForzados).toBe(0);
    expect(d.sinConexionDesde).toBe(T0); // pero sí cuenta como «sin conexión» para el estado y el aviso
  });

  it("no muta el diario que recibe", () => {
    const original = diarioNuevo();
    const copia = structuredClone(original);
    aplicarVigilancia(original, "caido", T0);
    expect(original).toEqual(copia);
  });
});

describe("normalizarDiario", () => {
  it("un diario viejo sin los campos nuevos no produce NaN", () => {
    const d = normalizarDiario({ latidos: 5 } as any);
    expect(d.latidos).toBe(5);
    expect(d.desconectadoSeguidos).toBe(0);
    expect(d.reiniciosForzados).toBe(0);
    expect(d.sinConexionDesde).toBe(null);
    expect(d.avisoActivo).toBe(false);
    const r = aplicarVigilancia(d, "caido", T0);
    expect(Number.isNaN(r.diario.desconectadoSeguidos)).toBe(false);
  });

  it("sin nada guardado, un diario nuevo", () => {
    expect(normalizarDiario(undefined)).toMatchObject({ latidos: 0, ultimoLatidoEn: null });
    expect(normalizarDiario(null)).toMatchObject({ latidos: 0 });
  });
});

describe("resumirEstado (lo que ve Juan en /api/estado)", () => {
  const base = { activo: true, vinculadoAlgunaVez: true, sinConexionDesde: null, ahora: T0 };

  it("conectado", () => {
    expect(resumirEstado({ ...base, conexion: "conectada" })).toEqual({ estado: "conectado", conectado: true, desconectadoMin: null });
  });

  it("necesita QR (sin vincular, esperando el código, o desvinculado desde el teléfono)", () => {
    expect(resumirEstado({ ...base, conexion: "esperando-qr", vinculadoAlgunaVez: false })).toMatchObject({ estado: "necesita_qr", conectado: false });
    expect(resumirEstado({ ...base, conexion: "desvinculada", sinConexionDesde: T0 - 7 * MIN })).toEqual({
      estado: "necesita_qr",
      conectado: false,
      desconectadoMin: 7,
    });
  });

  it("desconectado desde hace N min", () => {
    expect(resumirEstado({ ...base, conexion: "cerrada", sinConexionDesde: T0 - 12 * MIN - 5000 })).toEqual({
      estado: "desconectado",
      conectado: false,
      desconectadoMin: 12,
    });
    // El contenedor ni contesta: también es «desconectado» si antes estuvo vinculado.
    expect(resumirEstado({ ...base, conexion: null, sinConexionDesde: T0 - 3 * MIN })).toMatchObject({ estado: "desconectado", desconectadoMin: 3 });
  });

  it("iniciando: recién encendido, nunca estuvo vinculado", () => {
    expect(resumirEstado({ ...base, conexion: "arrancando", vinculadoAlgunaVez: false })).toMatchObject({ estado: "iniciando" });
    expect(resumirEstado({ ...base, conexion: null, vinculadoAlgunaVez: false, sinConexionDesde: T0 })).toMatchObject({ estado: "iniciando" });
  });

  it("apagado", () => {
    expect(resumirEstado({ ...base, activo: false, conexion: "conectada" })).toEqual({ estado: "apagado", conectado: false, desconectadoMin: null });
  });
});
