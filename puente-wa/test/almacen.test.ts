import { beforeEach, describe, expect, it } from "vitest";
import {
  COPIAS_A_CONSERVAR,
  CONTACTO_VIGENTE_MS,
  PENDIENTES_MAX,
  PENDIENTE_MAX_MS,
  crearAlmacen,
  iniciarEsquema,
  type Almacen,
} from "../src/almacen";
import { crearCifrador } from "../src/cifrado";
import { sqlDePrueba } from "./ayuda/sql";

// Claves de PRUEBA: no son ningún secreto real.
const CLAVE = "clave-de-prueba-para-la-sesion-0123456789";
const OTRA = "otra-clave-de-prueba-distinta-9876543210-xyz";

const HORA = 3_600_000;
const DIA = 24 * HORA;

async function montar(clave = CLAVE, anterior?: string) {
  const bd = sqlDePrueba();
  iniciarEsquema(bd.sql);
  const reloj = { t: 1_800_000_000_000 };
  const cifrador = await crearCifrador(clave, anterior);
  const almacen = crearAlmacen({ sql: bd.sql, transaccion: bd.transaccion, cifrador, ahora: () => reloj.t });
  return { bd, reloj, almacen, cifrador };
}

describe("la sesión: get / set / del / lote", () => {
  let m: Awaited<ReturnType<typeof montar>>;
  let a: Almacen;
  beforeEach(async () => {
    m = await montar();
    a = m.almacen;
  });

  it("guarda y lee", async () => {
    expect(await a.get("creds")).toBe(null);
    await a.set("creds", '{"registrationId":1}');
    expect(await a.get("creds")).toBe('{"registrationId":1}');
    await a.set("creds", '{"registrationId":2}');
    expect(await a.get("creds")).toBe('{"registrationId":2}');
    await a.del("creds");
    expect(await a.get("creds")).toBe(null);
  });

  it("NADA queda en claro en el almacenamiento (ni valores ni copias)", async () => {
    await a.set("creds", '{"noiseKey":"SECRETO-DE-PRUEBA"}');
    await a.lote({ escribir: { "pre-key-1": '{"private":"SECRETO-DE-PRUEBA-2"}' } });
    a.copiar();
    for (const tabla of ["wa_auth", "wa_copias"]) {
      const v = m.bd.volcado(tabla);
      expect(v).not.toContain("SECRETO");
      expect(v).not.toContain("noiseKey");
      expect(v).toContain("v1.");
    }
  });

  it("lote: lee varias, devuelve null explícito para las que no existen", async () => {
    await a.lote({ escribir: { "pre-key-1": "uno", "pre-key-2": "dos" } });
    const r = await a.lote({ leer: ["pre-key-1", "pre-key-2", "pre-key-3"] });
    expect(r.valores).toEqual({ "pre-key-1": "uno", "pre-key-2": "dos", "pre-key-3": null });
    expect(r.leidas).toBe(3);
  });

  it("lote: escribe y borra en una sola petición", async () => {
    await a.lote({ escribir: { x: "1", y: "2", z: "3" } });
    const r = await a.lote({ escribir: { w: "4" }, borrar: ["x", "y"] });
    expect(r).toMatchObject({ escritas: 1, borradas: 2 });
    expect((await a.lote({ leer: ["w", "x", "y", "z"] })).valores).toEqual({ w: "4", x: null, y: null, z: "3" });
  });

  it("lote: las 812 llaves del emparejamiento caben en una petición (y se releen todas)", async () => {
    const llaves: Record<string, string> = {};
    for (let i = 1; i <= 812; i++) llaves[`pre-key-${i}`] = JSON.stringify({ keyId: i, keyPair: { private: "x".repeat(44) } });
    const t0 = Date.now();
    const w = await a.lote({ escribir: llaves });
    expect(w.escritas).toBe(812);
    const r = await a.lote({ leer: Object.keys(llaves) });
    expect(r.leidas).toBe(812);
    expect(Object.values(r.valores).every((v) => v !== null)).toBe(true);
    expect(r.valores["pre-key-812"]).toBe(llaves["pre-key-812"]);
    // Baileys corta el emparejamiento a los 30 s; aquí debe ser cosa de milisegundos.
    expect(Date.now() - t0).toBeLessThan(5000);
  });

  it("lote: la escritura es atómica (si algo falla a mitad, no queda a medias)", async () => {
    await a.lote({ escribir: { a: "1" } });
    // Se provoca un fallo a mitad: una clave que rompe el INSERT no existe, así que se fuerza desde SQL.
    m.bd.db.exec("CREATE TRIGGER falla BEFORE INSERT ON wa_auth WHEN NEW.clave = 'mala' BEGIN SELECT RAISE(ABORT, 'falla de prueba'); END");
    await expect(a.lote({ escribir: { b: "2", mala: "3", c: "4" }, borrar: ["a"] })).rejects.toThrow(/falla de prueba/);
    expect((await a.lote({ leer: ["a", "b", "c"] })).valores).toEqual({ a: "1", b: null, c: null });
  });

  it("un valor alterado en el almacenamiento se detecta al leerlo", async () => {
    await a.set("creds", "valor");
    m.bd.db.exec("UPDATE wa_auth SET valor = substr(valor, 1, length(valor) - 2) || 'AA' WHERE clave = 'creds'");
    await expect(a.get("creds")).rejects.toThrow(/alterado|otra fila/);
  });
});

describe("estadoSesion (solo números, nunca material)", () => {
  it("sin sesión", async () => {
    const { almacen } = await montar();
    const e = await almacen.estadoSesion();
    expect(e).toMatchObject({ total: 0, vinculado: false, siguiente: null, sinSubir: null, instalacionCompleta: null });
    expect(almacen.hayCreds()).toBe(false);
  });

  it("instalación completa: sinSubir == siguiente (la señal que de verdad dice «terminó de instalarse»)", async () => {
    const { almacen } = await montar();
    await almacen.set("creds", JSON.stringify({ nextPreKeyId: 813, firstUnuploadedPreKeyId: 813, noiseKey: "SECRETO" }));
    await almacen.lote({
      escribir: { "pre-key-1": "a", "pre-key-2": "b", "app-state-sync-key-AAA": "c", "lid-mapping-123": "d", "session-x": "e" },
    });
    const e = await almacen.estadoSesion();
    expect(e).toMatchObject({
      vinculado: true,
      total: 6,
      preKeys: 2,
      appState: 1,
      lidMapping: 1,
      siguiente: 813,
      sinSubir: 813,
      instalacionCompleta: true,
    });
    expect(JSON.stringify(e)).not.toContain("SECRETO");
    expect(almacen.hayCreds()).toBe(true);
  });

  it("a medio instalar: quedan llaves sin subir aunque creds exista (el caso que se dio por bueno en el CRM de origen)", async () => {
    const { almacen } = await montar();
    await almacen.set("creds", JSON.stringify({ nextPreKeyId: 813, firstUnuploadedPreKeyId: 645 }));
    const e = await almacen.estadoSesion();
    expect(e.vinculado).toBe(true);
    expect(e.instalacionCompleta).toBe(false);
  });

  it("con la clave equivocada no revienta: los números quedan en null", async () => {
    const a = await montar();
    await a.almacen.set("creds", JSON.stringify({ nextPreKeyId: 5, firstUnuploadedPreKeyId: 5 }));
    const b = crearAlmacen({
      sql: a.bd.sql,
      transaccion: a.bd.transaccion,
      cifrador: await crearCifrador(OTRA),
      ahora: () => a.reloj.t,
    });
    const e = await b.estadoSesion();
    expect(e).toMatchObject({ vinculado: true, siguiente: null, instalacionCompleta: null });
  });
});

describe("poda de pre-keys (válvula manual)", () => {
  it("conserva las más recientes y no toca lo demás", async () => {
    const { almacen, reloj } = await montar();
    await almacen.set("creds", "c");
    for (let i = 1; i <= 30; i++) {
      reloj.t += 1000;
      await almacen.set(`pre-key-${i}`, String(i));
    }
    expect(almacen.podarPreKeys(10)).toBe(20);
    const r = await almacen.lote({ leer: ["pre-key-1", "pre-key-20", "pre-key-21", "pre-key-30", "creds"] });
    expect(r.valores).toEqual({ "pre-key-1": null, "pre-key-20": null, "pre-key-21": "21", "pre-key-30": "30", creds: "c" });
    expect(almacen.podarPreKeys(10)).toBe(0);
  });
});

describe("copias de la sesión", () => {
  it("copiar guarda las mismas filas cifradas y listarCopias las ve", async () => {
    const { almacen } = await montar();
    await almacen.set("creds", "C");
    await almacen.lote({ escribir: { "pre-key-1": "P1", "session-a": "S" } });
    const { copia, filas } = almacen.copiar();
    expect(filas).toBe(3);
    expect(copia).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$/);
    expect(almacen.listarCopias()).toEqual([{ copia, creada: expect.any(String), filas: 3 }]);
    const archivo = almacen.filasDeCopia(copia);
    expect(archivo.map((f) => f.clave)).toEqual(["creds", "pre-key-1", "session-a"]);
    expect(archivo.every((f) => f.valor.startsWith("v1."))).toBe(true);
  });

  it(`conserva solo las últimas ${COPIAS_A_CONSERVAR} (una por día)`, async () => {
    const { almacen, reloj } = await montar();
    await almacen.set("creds", "C");
    const hechas: string[] = [];
    for (let d = 0; d < COPIAS_A_CONSERVAR + 3; d++) {
      hechas.push(almacen.copiar().copia);
      reloj.t += DIA;
    }
    const lista = almacen.listarCopias().map((c) => c.copia);
    expect(lista.length).toBe(COPIAS_A_CONSERVAR);
    expect(lista).toEqual(hechas.slice(-COPIAS_A_CONSERVAR).reverse());
    // Y las filas de las copias podadas también se fueron.
    expect(almacen.filasDeCopia(hechas[0])).toEqual([]);
    expect(almacen.ultimaCopiaEn()).toBe(reloj.t - DIA);
  });

  it("ultimaCopiaEn es null si nunca se copió", async () => {
    const { almacen } = await montar();
    expect(almacen.ultimaCopiaEn()).toBe(null);
  });
});

describe("restaurar (procedimiento de recuperación)", () => {
  it("devuelve la sesión a como estaba en la copia", async () => {
    const { almacen, reloj } = await montar();
    await almacen.set("creds", "BUENA");
    await almacen.lote({ escribir: { "pre-key-1": "uno", "session-a": "sa" } });
    const { copia } = almacen.copiar();

    // Después la sesión se daña: se pierde creds y se cuela basura.
    reloj.t += HORA;
    await almacen.del("creds");
    await almacen.lote({ escribir: { "pre-key-9": "basura" }, borrar: ["session-a"] });

    const r = await almacen.restaurar(almacen.filasDeCopia(copia));
    expect(r.filas).toBe(3);
    expect((await almacen.lote({ leer: ["creds", "pre-key-1", "session-a", "pre-key-9"] })).valores).toEqual({
      creds: "BUENA",
      "pre-key-1": "uno",
      "session-a": "sa",
      "pre-key-9": null,
    });
  });

  it("no restaura una copia sin credenciales", async () => {
    const { almacen } = await montar();
    await almacen.set("creds", "ORIGINAL");
    await expect(almacen.restaurar([{ clave: "pre-key-1", valor: "v1.a.b.c", actualizado_en: 1 }])).rejects.toThrow(/creds/);
    expect(await almacen.get("creds")).toBe("ORIGINAL"); // no se tocó nada
  });

  it("no restaura una copia hecha con OTRA clave (dejaría la sesión ilegible)", async () => {
    const origen = await montar(OTRA);
    await origen.almacen.set("creds", "DE-OTRA-CLAVE");
    const { copia } = origen.almacen.copiar();
    const filas = origen.almacen.filasDeCopia(copia);

    const destino = await montar(CLAVE);
    await destino.almacen.set("creds", "ORIGINAL");
    await expect(destino.almacen.restaurar(filas)).rejects.toThrow(/clave/);
    expect(await destino.almacen.get("creds")).toBe("ORIGINAL"); // intacto
  });

  it("si falla a mitad, la sesión original queda intacta (transacción)", async () => {
    const { almacen, bd } = await montar();
    await almacen.set("creds", "ORIGINAL");
    await almacen.set("creds", "ORIGINAL");
    const { copia } = almacen.copiar();
    const filas = almacen.filasDeCopia(copia);
    bd.db.exec("CREATE TRIGGER falla BEFORE INSERT ON wa_auth WHEN NEW.clave = 'rara' BEGIN SELECT RAISE(ABORT, 'falla'); END");
    await expect(almacen.restaurar([...filas, { clave: "rara", valor: filas[0].valor, actualizado_en: 1 }])).rejects.toThrow();
    expect(await almacen.get("creds")).toBe("ORIGINAL");
  });
});

describe("recifrar (rotación de WA_SESION_CLAVE)", () => {
  it("vuelve a cifrar con la clave nueva y luego ya no hace falta la anterior", async () => {
    const vieja = await montar(CLAVE);
    await vieja.almacen.set("creds", "DATO");
    await vieja.almacen.lote({ escribir: { "pre-key-1": "uno", "pre-key-2": "dos" } });

    // Se despliega la clave nueva con la anterior al lado.
    const conAmbas = crearAlmacen({
      sql: vieja.bd.sql,
      transaccion: vieja.bd.transaccion,
      cifrador: await crearCifrador(OTRA, CLAVE),
      ahora: () => vieja.reloj.t,
    });
    expect(await conAmbas.get("creds")).toBe("DATO");
    expect(await conAmbas.recifrar()).toEqual({ revisadas: 3, recifradas: 3 });
    expect(await conAmbas.recifrar()).toEqual({ revisadas: 3, recifradas: 0 });

    // Ahora basta con la nueva.
    const soloNueva = crearAlmacen({
      sql: vieja.bd.sql,
      transaccion: vieja.bd.transaccion,
      cifrador: await crearCifrador(OTRA),
      ahora: () => vieja.reloj.t,
    });
    expect((await soloNueva.lote({ leer: ["creds", "pre-key-1", "pre-key-2"] })).valores).toEqual({
      creds: "DATO",
      "pre-key-1": "uno",
      "pre-key-2": "dos",
    });
  });
});

describe("envíos y topes", () => {
  it("reserva, lista y devuelve lo que no salió", async () => {
    const { almacen, reloj } = await montar();
    const ids = almacen.reservarEnvios("50761111111", 4, false);
    expect(ids.length).toBe(4);
    expect(almacen.enviosRecientes()).toHaveLength(4);
    almacen.liberarEnvios(ids.slice(3)); // solo salieron 3
    expect(almacen.enviosRecientes()).toHaveLength(3);
    expect(almacen.enviosRecientes()[0]).toEqual({ ts: reloj.t, para: "50761111111", frio: false });
  });

  it("lo de hace más de un día se olvida", async () => {
    const { almacen, reloj } = await montar();
    almacen.reservarEnvios("50761111111", 2, true);
    reloj.t += DIA + 1000;
    expect(almacen.enviosRecientes()).toEqual([]);
  });

  it("esFrio: quien nos escribió hace poco no es «nuevo»", async () => {
    const { almacen, reloj } = await montar();
    expect(almacen.esFrio("50761111111")).toBe(true);
    almacen.marcarEntrante("50761111111");
    expect(almacen.esFrio("50761111111")).toBe(false);
    expect(almacen.esFrio("50762222222")).toBe(true);
    reloj.t += CONTACTO_VIGENTE_MS + 1000;
    expect(almacen.esFrio("50761111111")).toBe(true);
  });

  it("recuerda los ids enviados un par de horas", async () => {
    const { almacen, reloj } = await montar();
    almacen.anotarEnviados(["A", "B"]);
    reloj.t += HORA;
    almacen.anotarEnviados(["C"]);
    expect(almacen.enviadosRecientes().map((e) => e.id)).toEqual(["A", "B", "C"]);
    reloj.t += HORA + 1000;
    almacen.anotarEnviados([]);
    expect(almacen.enviadosRecientes().map((e) => e.id)).toEqual(["C"]);
  });
});

describe("entrantes pendientes (si Juan no está disponible)", () => {
  it("se guardan cifrados y salen en orden", async () => {
    const { almacen, bd } = await montar();
    await almacen.encolarPendiente('{"id_mensaje":"A","texto":"Hola, quiero una cama"}');
    await almacen.encolarPendiente('{"id_mensaje":"B"}');
    expect(bd.volcado("wa_pendientes")).not.toContain("quiero una cama");
    expect(almacen.contarPendientes()).toBe(2);
    const p = await almacen.pendientes(10);
    expect(p.map((x) => JSON.parse(x.cuerpo).id_mensaje)).toEqual(["A", "B"]);
    almacen.fallarPendiente(p[0].id);
    expect((await almacen.pendientes(1))[0].intentos).toBe(1);
    almacen.borrarPendiente(p[0].id);
    expect(almacen.contarPendientes()).toBe(1);
  });

  it("tienen tope de antigüedad y de cantidad", async () => {
    const { almacen, reloj } = await montar();
    await almacen.encolarPendiente("viejo");
    reloj.t += PENDIENTE_MAX_MS + 1000;
    await almacen.encolarPendiente("nuevo");
    expect((await almacen.pendientes(10)).map((p) => p.cuerpo)).toEqual(["nuevo"]);

    for (let i = 0; i < PENDIENTES_MAX + 5; i++) await almacen.encolarPendiente(`m${i}`);
    expect(almacen.contarPendientes()).toBe(PENDIENTES_MAX);
    const primeros = await almacen.pendientes(1);
    expect(primeros[0].cuerpo).not.toBe("nuevo"); // se descartaron los más viejos
  });
});
