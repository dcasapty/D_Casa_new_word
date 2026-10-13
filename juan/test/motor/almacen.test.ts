/**
 * La memoria de trabajo de una conversación (SQLite del Durable Object, aquí el de Node): valores sueltos, mensajes,
 * cola de escrituras a Odoo, archivos temporales en trozos y fotos.
 */
import { describe, expect, it } from "vitest";
import { Cola, crearEsquema, Fotos, Kv, MEDIO_MAXIMO, MEDIO_VIDA_MS, Medios, Mensajes } from "../../src/motor/almacen";
import { bytesDeBlob, sqlDeDurableObject } from "../../src/motor/sql";
import { crearSqlNode } from "../helpers/sqlNode";

function nuevo() {
  const sql = crearSqlNode();
  crearEsquema(sql);
  return { sql, kv: new Kv(sql), mensajes: new Mensajes(sql), cola: new Cola(sql), medios: new Medios(sql), fotos: new Fotos(sql) };
}

describe("Kv", () => {
  it("texto, número y bandera; poner null borra", () => {
    const { kv } = nuevo();
    expect(kv.texto("x")).toBeNull();
    kv.poner("x", "hola");
    kv.poner("n", 42);
    kv.poner("b", true);
    expect([kv.texto("x"), kv.numero("n"), kv.bandera("b"), kv.bandera("no_existe")]).toEqual(["hola", 42, true, false]);
    kv.poner("b", false);
    expect(kv.bandera("b")).toBe(false);
    kv.poner("x", null);
    expect(kv.texto("x")).toBeNull();
  });

  it("sobrescribe sin duplicar y `numero` ignora lo que no es número", () => {
    const { kv } = nuevo();
    kv.poner("k", 1);
    kv.poner("k", 2);
    expect(kv.numero("k")).toBe(2);
    kv.poner("t", "no es número");
    expect(kv.numero("t")).toBeNull();
    kv.poner("v", "");
    expect(kv.numero("v")).toBeNull();
  });

  it("sumar parte de cero", () => {
    const { kv } = nuevo();
    expect(kv.sumar("c")).toBe(1);
    expect(kv.sumar("c", 4)).toBe(5);
  });
});

describe("Mensajes", () => {
  it("el mismo id_mensaje no se puede insertar dos veces (un reintento del proveedor)", () => {
    const { mensajes } = nuevo();
    mensajes.insertar({ id_mensaje: "a", rol: "cliente", texto: "hola", ts: 1 });
    expect(mensajes.existe("a")).toBe(true);
    expect(mensajes.existe("b")).toBe(false);
    expect(() => mensajes.insertar({ id_mensaje: "a", rol: "cliente", texto: "hola", ts: 1 })).toThrow();
  });

  it("pendientes de la ráfaga: se marcan, se leen en orden y se limpian", () => {
    const { mensajes } = nuevo();
    const a = mensajes.insertar({ id_mensaje: "a", rol: "cliente", texto: "uno", ts: 1, pendiente: true });
    const b = mensajes.insertar({ id_mensaje: "b", rol: "cliente", texto: "dos", ts: 2, pendiente: true });
    mensajes.insertar({ id_mensaje: "c", rol: "bot", texto: "tres", ts: 3 });
    expect(mensajes.pendientes().map((m) => m.texto)).toEqual(["uno", "dos"]);
    mensajes.marcarPendientes([a], false);
    expect(mensajes.pendientes().map((m) => m.id)).toEqual([b]);
    mensajes.limpiarPendientes();
    expect(mensajes.pendientes()).toEqual([]);
  });

  it("`ultimos(n)` devuelve los n más recientes, en orden cronológico", () => {
    const { mensajes } = nuevo();
    for (let i = 1; i <= 6; i++) mensajes.insertar({ id_mensaje: `m${i}`, rol: i % 2 ? "cliente" : "bot", texto: `t${i}`, ts: i });
    expect(mensajes.ultimos(3).map((m) => m.texto)).toEqual(["t4", "t5", "t6"]);
  });

  it("cuenta los mensajes del cliente en las últimas 24 h (tope diario) y no los del bot", () => {
    const { mensajes } = nuevo();
    mensajes.insertar({ id_mensaje: "a", rol: "cliente", texto: "viejo", ts: 100 });
    mensajes.insertar({ id_mensaje: "b", rol: "cliente", texto: "nuevo", ts: 5000 });
    mensajes.insertar({ id_mensaje: "c", rol: "bot", texto: "bot", ts: 6000 });
    expect(mensajes.delClienteDesde(1000)).toBe(1);
  });

  it("textosDelCliente (anti-spam) trae los últimos primero; salientesDesde junta bot y vendedora", () => {
    const { mensajes } = nuevo();
    mensajes.insertar({ id_mensaje: "a", rol: "cliente", texto: "hola", ts: 1 });
    mensajes.insertar({ id_mensaje: "b", rol: "bot", texto: "buenas", ts: 2 });
    mensajes.insertar({ id_mensaje: "c", rol: "vendedora", texto: "te atiendo yo", ts: 3 });
    mensajes.insertar({ id_mensaje: "d", rol: "cliente", texto: "ok", ts: 4 });
    expect(mensajes.textosDelCliente(5)).toEqual(["ok", "hola"]);
    expect(mensajes.salientesDesde(0)).toEqual(["buenas", "te atiendo yo"]);
    expect(mensajes.salientesDesde(2)).toEqual(["te atiendo yo"]);
    expect(mensajes.hayDelNegocio()).toBe(true);
  });

  it("redactar tapa un secreto SOLO en los mensajes del cliente (el PIN no queda en el historial)", () => {
    const { mensajes } = nuevo();
    mensajes.insertar({ id_mensaje: "a", rol: "cliente", texto: "mi pin es 482913 gracias", ts: 1 });
    mensajes.insertar({ id_mensaje: "b", rol: "bot", texto: "482913 no lo repito", ts: 2 });
    mensajes.redactar("482913", "••••");
    expect(mensajes.ultimos(2).map((m) => m.texto)).toEqual(["mi pin es •••• gracias", "482913 no lo repito"]);
    mensajes.redactar("12", "XX"); // demasiado corto: no toca nada
    expect(mensajes.ultimos(2)[0].texto).toBe("mi pin es •••• gracias");
  });

  it("purgar borra lo viejo pero siempre conserva los últimos N", () => {
    const { mensajes } = nuevo();
    for (let i = 1; i <= 10; i++) mensajes.insertar({ id_mensaje: `m${i}`, rol: "cliente", texto: `t${i}`, ts: i });
    mensajes.purgar(100, 3);
    expect(mensajes.ultimos(10).map((m) => m.texto)).toEqual(["t8", "t9", "t10"]);
  });
});

describe("Cola de escrituras a Odoo", () => {
  it("vencidas en orden; reintentar suma un intento y aplaza; posponer no gasta intento", () => {
    const { cola } = nuevo();
    cola.agregar("mensaje", { a: 1 }, 1000);
    cola.agregar("herramienta", { b: 2 }, 1000);
    const [primera, segunda] = cola.vencidas(1000);
    expect([primera.tipo, segunda.tipo, primera.intentos]).toEqual(["mensaje", "herramienta", 0]);
    expect(JSON.parse(primera.cuerpo)).toEqual({ a: 1 });

    cola.reintentar(primera.id, 5000);
    cola.posponer(segunda.id, 7000);
    expect(cola.vencidas(1000)).toEqual([]);
    expect(cola.proxima()).toBe(5000);
    const despues = cola.vencidas(8000);
    expect(despues.map((f) => f.intentos)).toEqual([1, 0]);
  });

  it("borrar quita la fila; sin filas `proxima` es null; purgar quita lo muy viejo", () => {
    const { cola } = nuevo();
    expect(cola.proxima()).toBeNull();
    cola.agregar("mensaje", {}, 10);
    cola.agregar("mensaje", {}, 9000);
    cola.purgar(100);
    expect(cola.vencidas(1e9)).toHaveLength(1);
    cola.borrar(cola.vencidas(1e9)[0].id);
    expect(cola.vencidas(1e9)).toEqual([]);
  });
});

describe("Medios (archivos del cliente, temporales)", () => {
  const bytesDe = (n: number) => Uint8Array.from({ length: n }, (_, i) => i % 251);

  it("guarda y lee igual, también cuando pasan de un trozo (900 KB) — el límite de una fila de SQLite", () => {
    const { medios } = nuevo();
    const datos = bytesDe(2_000_000);
    medios.guardar("m1", datos, "application/pdf", "recibo.pdf", 1000);
    const r = medios.leer("m1", 2000)!;
    expect(r.mime).toBe("application/pdf");
    expect(r.nombre).toBe("recibo.pdf");
    expect(r.bytes.byteLength).toBe(2_000_000);
    expect(r.bytes.every((b, i) => b === datos[i])).toBe(true);
  });

  it("un archivo vacío también se guarda (una parte)", () => {
    const { medios } = nuevo();
    medios.guardar("v", new Uint8Array(0), "text/plain", undefined, 1);
    expect(medios.leer("v", 2)).toMatchObject({ mime: "text/plain", nombre: null });
  });

  it("más de 12 MB: se rechaza", () => {
    const { medios } = nuevo();
    expect(() => medios.guardar("g", new Uint8Array(MEDIO_MAXIMO + 1), "x/y", undefined, 1)).toThrow(/demasiado grande/);
  });

  it("a los 2 días ya no se entrega, y purgar lo borra", () => {
    const { medios, sql } = nuevo();
    medios.guardar("m", bytesDe(10), "image/jpeg", undefined, 1000);
    expect(medios.leer("m", 1000 + MEDIO_VIDA_MS)).not.toBeNull();
    expect(medios.leer("m", 1000 + MEDIO_VIDA_MS + 1)).toBeNull();
    medios.purgar(1000 + MEDIO_VIDA_MS);
    expect(sql.todos("SELECT 1 FROM medios")).toEqual([]);
    expect(medios.leer("no-existe", 5)).toBeNull();
  });
});

describe("Fotos", () => {
  it("guarda por código, pisa el anterior y purga lo viejo", () => {
    const { fotos } = nuevo();
    fotos.guardar("F1", "https://sitio/a.jpg", "Cama Roma", 10);
    fotos.guardar("F1", "https://sitio/b.jpg", undefined, 20);
    expect(fotos.buscar("F1")).toEqual({ url: "https://sitio/b.jpg", nombre: null });
    expect(fotos.buscar("otra")).toBeUndefined();
    fotos.purgar(100);
    expect(fotos.buscar("F1")).toBeUndefined();
  });
});

describe("sqlDeDurableObject: la puerta hacia `ctx.storage.sql`", () => {
  /** Un `SqlStorage` falso que se porta como el de workerd: los BLOB entran y salen como ArrayBuffer. */
  function almacenComoWorkerd() {
    const base = crearSqlNode();
    const visto: unknown[][] = [];
    return {
      visto,
      almacen: {
        exec(q: string, ...b: unknown[]) {
          visto.push(b);
          for (const x of b) if (x instanceof Uint8Array) throw new Error("SqlStorage solo acepta ArrayBuffer para los BLOB");
          const params = b.map((x) => (x instanceof ArrayBuffer ? new Uint8Array(x) : x)) as (string | number | null | Uint8Array)[];
          const filas = /^\s*select/i.test(q) ? base.todos<Record<string, unknown>>(q, ...params) : (base.correr(q, ...params), []);
          const comoWorkerd = filas.map((f) => Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v instanceof Uint8Array ? v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength) : v])));
          return { toArray: () => comoWorkerd };
        },
      },
    };
  }

  it("el motor guarda archivos aunque workerd rechace las vistas Uint8Array (se pasan como ArrayBuffer)", () => {
    const { almacen, visto } = almacenComoWorkerd();
    const sql = sqlDeDurableObject(almacen);
    crearEsquema(sql);
    const medios = new Medios(sql);
    const datos = Uint8Array.from([1, 2, 3, 4, 5]);
    // Una vista con desplazamiento: si se pasara `.buffer` a secas, saldrían bytes de más.
    const vista = new Uint8Array(datos.buffer, 1, 3);
    medios.guardar("m", vista, "image/png", "x.png", 1);
    expect(visto.some((b) => b.some((x) => x instanceof ArrayBuffer && x.byteLength === 3))).toBe(true);
    expect([...medios.leer("m", 2)!.bytes]).toEqual([2, 3, 4]);
  });

  it("bytesDeBlob entiende ArrayBuffer (workerd), Uint8Array (Node) y devuelve vacío con otra cosa", () => {
    expect([...bytesDeBlob(new Uint8Array([1, 2]))]).toEqual([1, 2]);
    expect([...bytesDeBlob(new Uint8Array([3, 4]).buffer)]).toEqual([3, 4]);
    expect(bytesDeBlob(null).byteLength).toBe(0);
    expect(bytesDeBlob("texto").byteLength).toBe(0);
  });
});
