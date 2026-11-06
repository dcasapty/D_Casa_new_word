/**
 * La bandeja de Meta (WhatsApp Cloud, Messenger, Instagram). El webhook guarda el mensaje crudo en el Durable Object ANTES de
 * contestarle 200 a Meta (`guardarRecibido`) y lo atiende después. Si el Worker no alcanza (se reinicia, se le acaba el tiempo,
 * falla el Durable Object a mitad), la alarma lo atiende desde la bandeja: nada se pierde y nada se contesta dos veces.
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

const MINUTO = 60_000;
const RESCATE = 2 * MINUTO;
const ENCENDIDO = { canales_activos: { whatsapp_cloud: true } };

function nube(op: Parameters<typeof crearMundo>[0] = {}) {
  const m = crearMundo({ canal: "whatsapp_cloud", config: ENCENDIDO, ...op });
  m.guion([{ texto: "Claro, ¿qué medida de cama buscas?" }]);
  return m;
}

describe("guardar antes del 200", () => {
  it("guarda el mensaje crudo sin bajar nada ni llamar a Odoo, y arma la alarma de rescate", async () => {
    const m = nube();
    const e = m.entrante("Hola, ¿tienen camas?");
    expect(await m.motor.guardarRecibido(e)).toEqual({ nuevo: true, pendiente: true });
    expect(m.motor.resumen().bandeja).toBe(1);
    expect(m.alarmaProgramada()).toBe(m.ahora() + RESCATE);
    expect(m.odoo.mensajes).toEqual([]);
    expect(m.odoo.pedidosDeConfig).toBe(0);
  });

  it("el mismo id (Meta reintenta) no es nuevo: ni mientras espera en la bandeja ni después de atenderlo", async () => {
    const m = nube();
    const e = m.entrante("Hola");
    expect((await m.motor.guardarRecibido(e)).nuevo).toBe(true);
    expect((await m.motor.guardarRecibido({ ...e })).nuevo).toBe(false);
    await m.motor.ingest(e); // lo que hace el Worker justo después del 200
    expect(m.motor.resumen().bandeja).toBe(0);
    expect((await m.motor.guardarRecibido({ ...e })).nuevo).toBe(false);
  });

  it("un mensaje sin id_mensaje no se guarda (no se podría reconocer su reintento): el webhook contesta 500", async () => {
    const m = nube();
    await expect(m.motor.guardarRecibido(m.entrante("hola", { id_mensaje: "" }))).rejects.toThrow(/id_mensaje/);
  });

  it("lo normal: el Worker lo atiende enseguida, se borra de la bandeja y se contesta UNA vez", async () => {
    const m = nube();
    const e = m.entrante("Hola, ¿tienen camas?");
    await m.motor.guardarRecibido(e);
    await m.motor.ingest(e);
    await m.pasar(RESCATE + 20_000);
    expect(m.canal.salidas).toHaveLength(1);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente").map((x) => x.id_mensaje)).toEqual([e.id_mensaje]);
  });
});

describe("el rescate (el Worker no alcanzó a atenderlo)", () => {
  it("pasados 2 minutos la alarma lo atiende: se registra en Odoo y se contesta una vez; un reintento de Meta no lo repite", async () => {
    const m = nube();
    const e = m.entrante("Hola, ¿tienen camas?");
    await m.motor.guardarRecibido(e);
    await m.pasar(RESCATE - 1000);
    expect(m.odoo.mensajes).toEqual([]); // todavía le toca al Worker
    await m.pasar(1000 + 20_000); // rescate + ráfaga de 15 s
    expect(m.motor.resumen().bandeja).toBe(0);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente").map((x) => [x.id_mensaje, x.texto])).toEqual([[e.id_mensaje, "Hola, ¿tienen camas?"]]);
    expect(m.canal.salidas).toHaveLength(1);
    expect(m.registros.some((r) => /esperaba en la bandeja/.test(r.mensaje))).toBe(true);

    expect((await m.motor.guardarRecibido({ ...e })).nuevo).toBe(false);
    await m.motor.ingest({ ...e }); // y si el Worker llega tarde, es un repetido
    await m.pasar(RESCATE + 20_000);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("con la configuración de Odoo desconocida no decide (el canal parecería apagado): espera y lo atiende cuando Odoo vuelve", async () => {
    const m = nube();
    m.odoo.caido = true; // Odoo dormido y ninguna copia de la configuración
    const e = m.entrante("Hola");
    await m.motor.guardarRecibido(e);
    await m.pasar(RESCATE + 1000);
    expect(m.motor.resumen().bandeja).toBe(1);
    const [fila] = m.motor.bandeja.todas();
    // No es un fallo del mensaje: no cuenta como intento y se mira otra vez en 2 minutos (sin esperas que crezcan).
    expect([fila.intentos, fila.proximo - m.ahora()]).toEqual([0, RESCATE - 1000]);
    expect(m.canal.salidas).toEqual([]);
    expect(m.registros.some((r) => r.nivel === "warn" && /espera la configuración de Odoo/.test(r.mensaje))).toBe(true);

    m.odoo.caido = false;
    await m.pasar(10 * MINUTO);
    expect(m.motor.resumen().bandeja).toBe(0);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente")).toHaveLength(1);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("si atenderlo falla, se reintenta con esperas cada vez más largas (no se descarta)", async () => {
    const m = nube();
    const e = m.entrante("Hola");
    await m.motor.guardarRecibido(e);
    const original = m.deps.config;
    let fallas = 2;
    m.deps.config = async () => {
      if (fallas-- > 0) throw new Error("el motor falló");
      return original();
    };
    await m.pasar(RESCATE);
    const [f1] = m.motor.bandeja.vencidas(m.ahora() + 24 * 3600_000);
    expect([f1.intentos, f1.proximo - m.ahora()]).toEqual([1, RESCATE]);
    await m.pasar(RESCATE);
    const [f2] = m.motor.bandeja.vencidas(m.ahora() + 24 * 3600_000);
    expect([f2.intentos, f2.proximo - m.ahora()]).toEqual([2, 2 * RESCATE]);
    await m.pasar(2 * RESCATE + 20_000);
    expect(m.motor.resumen().bandeja).toBe(0);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("canal APAGADO en Odoo: se suelta sin registrar ni contestar (como el webhook)", async () => {
    const m = nube({ config: { canales_activos: { whatsapp_cloud: false } } });
    await m.motor.guardarRecibido(m.entrante("Hola"));
    await m.pasar(RESCATE + 20_000);
    expect(m.motor.resumen().bandeja).toBe(0);
    expect(m.odoo.mensajes).toEqual([]);
    expect(m.motor.mensajes.ultimos(10)).toEqual([]);
    expect(m.canal.salidas).toEqual([]);
  });

  it("el archivo se vuelve a pedir al canal por su `ref` (el media_id) y queda para Odoo", async () => {
    const m = nube({ urlPublica: "https://juan.example" });
    const pedidos: string[] = [];
    Object.assign(m.canal, {
      descargar: async (ref: string) => {
        pedidos.push(ref);
        return { bytes: new Uint8Array([1, 2, 3]), mime: "image/jpeg" };
      },
    });
    await m.motor.guardarRecibido(m.entrante("así la quiero", { adjuntos: [{ tipo: "imagen", mime: "image/jpeg", ref: "MEDIA9" }] }));
    await m.pasar(RESCATE + 1000);
    expect(pedidos).toEqual(["MEDIA9"]);
    const [cliente] = m.odoo.mensajes.filter((x) => x.autor === "cliente");
    expect(cliente.adjuntos?.[0]).toMatchObject({ tipo: "imagen", mime: "image/jpeg" });
    expect(cliente.adjuntos?.[0].url).toMatch(/^https:\/\/juan\.example\/media\//);
  });

  it("no toca un mensaje que se está atendiendo en ese momento (una nota de voz lenta): no se procesa dos veces", async () => {
    let abrir!: () => void;
    const puerta = new Promise<void>((r) => (abrir = r));
    let transcripciones = 0;
    const m = nube({
      transcribir: async () => {
        transcripciones++;
        await puerta;
        return "busco una cama queen";
      },
    });
    const e = m.entrante(undefined, { adjuntos: [{ tipo: "audio", mime: "audio/ogg", bytes: new Uint8Array([5, 5, 5]) }] });
    await m.motor.guardarRecibido(e);
    const atendiendo = m.motor.ingest(e); // el Worker, todavía transcribiendo
    await m.pasar(RESCATE + 1000); // vence el rescate mientras tanto
    expect(m.motor.resumen().bandeja).toBe(1);
    abrir();
    await atendiendo;
    await m.pasar(RESCATE + 20_000);
    expect(transcripciones).toBe(1);
    expect(m.motor.resumen().bandeja).toBe(0);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente")).toHaveLength(1);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("«Borrar mis datos» también vacía la bandeja", async () => {
    const m = nube();
    await m.motor.guardarRecibido(m.entrante("Hola"));
    await m.motor.olvidar();
    expect(m.motor.resumen().bandeja).toBe(0);
  });
});

describe("revisión adversarial del 2026-11-06", () => {
  const delCliente = (m: ReturnType<typeof nube>) => m.odoo.mensajes.filter((x) => x.autor === "cliente").map((x) => x.texto);

  it("1 · una caída de Odoo más larga que una hora no deja el mensaje sin contestar: se mira cada 2 min y se contesta al volver", async () => {
    const m = nube();
    m.odoo.caido = true;
    await m.motor.guardarRecibido(m.entrante("Hola, ¿tienen camas?"));
    await m.pasar(75 * MINUTO);
    expect(m.motor.bandeja.todas()[0].intentos).toBe(0);
    m.odoo.caido = false;
    await m.pasar(RESCATE + 20_000);
    expect(delCliente(m)).toEqual(["Hola, ¿tienen camas?"]);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("1 · ni con 3 horas de Odoo caído se vuelve «vencido»: lo que esperó por culpa nuestra se contesta (el canal lo permite 24 h)", async () => {
    const m = nube();
    m.odoo.caido = true;
    await m.motor.guardarRecibido(m.entrante("Hola"));
    await m.pasar(3 * 3600_000);
    m.odoo.caido = false;
    await m.pasar(RESCATE + 20_000);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("2 · lo que esperaba en la bandeja se atiende ANTES que un mensaje posterior: en orden en Odoo y una sola respuesta", async () => {
    const m = nube();
    await m.motor.guardarRecibido(m.entrante("A: busco una cama")); // el Worker no lo atendió (configuración desconocida en su isolate)
    await m.pasar(30_000);
    const b = m.entrante("B: queen");
    await m.motor.guardarRecibido(b);
    await m.motor.ingest(b); // el Worker sí atiende el segundo
    await m.pasar(RESCATE + 3 * MINUTO);
    expect(delCliente(m)).toEqual(["A: busco una cama", "B: queen"]);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("2 · el rescate atiende también lo más viejo aunque su espera no haya vencido, en orden", async () => {
    const m = nube();
    const original = m.deps.config;
    let fallas = 2;
    m.deps.config = async () => {
      if (fallas-- > 0) throw new Error("falla pasajera");
      return original();
    };
    await m.motor.guardarRecibido(m.entrante("A: primero")); // falla a los 2 y a los 4 min: su próximo intento queda a los 8
    await m.pasar(4.5 * MINUTO);
    await m.motor.guardarRecibido(m.entrante("B: después")); // vence a los 6,5 min, antes que A
    await m.pasar(2 * MINUTO + 1000);
    expect(delCliente(m)).toEqual(["A: primero", "B: después"]);
  });

  it("3 · «Borrar mis datos» a mitad de un rescate: nada de lo borrado vuelve a guardarse ni llega a Odoo", async () => {
    let abrir!: () => void;
    const puerta = new Promise<void>((r) => (abrir = r));
    const m = nube({
      transcribir: async () => {
        await puerta;
        return "nota";
      },
    });
    Object.assign(m.canal, { descargar: async () => ({ bytes: new Uint8Array([1, 2]), mime: "audio/ogg" }) });
    await m.motor.guardarRecibido(m.entrante(undefined, { adjuntos: [{ tipo: "audio", mime: "audio/ogg", ref: "M1" }] }));
    await m.motor.guardarRecibido(m.entrante("Y: mi cédula es 8-123-456"));
    const alarma = m.pasar(RESCATE + 1000); // el rescate de X se queda transcribiendo
    for (let i = 0; i < 50; i++) await new Promise((r) => setTimeout(r, 0));
    await m.motor.olvidar();
    abrir();
    await alarma;
    await m.pasar(10 * MINUTO);
    expect(m.motor.mensajes.ultimos(10)).toEqual([]);
    expect(m.motor.resumen()).toMatchObject({ cola: 0, bandeja: 0 });
    expect(m.deps.sql.uno<{ n: number }>("SELECT COUNT(*) AS n FROM medios")?.n).toBe(0);
    expect(m.odoo.mensajes).toEqual([]);
  });

  it("3 · «Borrar mis datos» mientras el Worker atiende una nota de voz (cualquier canal): se suelta sin guardar", async () => {
    let abrir!: () => void;
    const puerta = new Promise<void>((r) => (abrir = r));
    const m = crearMundo({
      transcribir: async () => {
        await puerta;
        return "mi dirección es…";
      },
    });
    const atendiendo = m.motor.ingest(m.entrante(undefined, { adjuntos: [{ tipo: "audio", mime: "audio/ogg", bytes: new Uint8Array([5, 5]) }] }));
    for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 0));
    await m.motor.olvidar();
    abrir();
    expect((await atendiendo).accion).toBe("olvidado");
    expect(m.motor.mensajes.ultimos(10)).toEqual([]);
    expect(m.motor.resumen().cola).toBe(0);
    expect(m.deps.sql.uno<{ n: number }>("SELECT COUNT(*) AS n FROM medios")?.n).toBe(0);
  });

  it("4 · un eco que Meta vuelve a entregar después de 15 min no se toma por una persona escribiendo (el bot no se calla)", async () => {
    const m = nube();
    m.guion([{ texto: "Claro, ¿qué medida buscas?" }]);
    await m.motor.ingest(m.entrante("hola"));
    await m.pasar(16_000);
    const eco = m.entrante("Claro, ¿qué medida buscas?", { propio: true, id_mensaje: "wamid.ECO" });
    await m.motor.guardarRecibido(eco);
    expect((await m.motor.ingest(eco)).accion).toBe("eco");
    await m.pasar(20 * MINUTO);
    expect(await m.motor.guardarRecibido({ ...eco })).toEqual({ nuevo: false, pendiente: false });
    expect((await m.motor.ingest({ ...eco })).accion).toBe("duplicado"); // y si el Worker lo trae tarde, tampoco
    expect(m.motor.silencio()).toBe(false);
  });

  it("4 · lo soltado por canal apagado tampoco vuelve como nuevo si Meta lo entrega otra vez", async () => {
    const m = nube({ config: { canales_activos: { whatsapp_cloud: false } } });
    const e = m.entrante("Hola");
    await m.motor.guardarRecibido(e);
    await m.pasar(RESCATE + 1000);
    expect(m.motor.resumen().bandeja).toBe(0);
    expect((await m.motor.guardarRecibido({ ...e })).nuevo).toBe(false);
  });

  it("5 · `pendiente`: lo guardado que nadie atiende se puede atender desde el reintento; mientras se atiende o ya atendido, no", async () => {
    let abrir!: () => void;
    const puerta = new Promise<void>((r) => (abrir = r));
    const m = nube({
      transcribir: async () => {
        await puerta;
        return "busco una cama";
      },
    });
    const e = m.entrante(undefined, { adjuntos: [{ tipo: "audio", mime: "audio/ogg", bytes: new Uint8Array([5]) }] });
    expect(await m.motor.guardarRecibido(e)).toEqual({ nuevo: true, pendiente: true });
    expect(await m.motor.guardarRecibido({ ...e })).toEqual({ nuevo: false, pendiente: true }); // la respuesta se perdió: atiéndelo
    const atendiendo = m.motor.ingest(e);
    expect(await m.motor.guardarRecibido({ ...e })).toEqual({ nuevo: false, pendiente: false });
    abrir();
    await atendiendo;
    expect(await m.motor.guardarRecibido({ ...e })).toEqual({ nuevo: false, pendiente: false });
  });

  it("6 · si el objeto se cae justo después de guardar el mensaje, igual queda para contestar (guardado y marcado van juntos)", async () => {
    const m = nube();
    const e = m.entrante("Hola, ¿tienen camas?");
    await m.motor.guardarRecibido(e);
    const fijar = m.deps.fijarAlarma;
    let caida = true;
    m.deps.fijarAlarma = async (ts) => {
      if (caida) {
        caida = false;
        throw new Error("el Durable Object se reinició");
      }
      return fijar(ts);
    };
    await expect(m.motor.ingest(e)).rejects.toThrow(/reinició/);
    await m.pasar(RESCATE + 20_000);
    expect(m.canal.salidas).toHaveLength(1);
  });

  it("mientras el rescate atiende un mensaje, el Worker que llega tarde con el mismo no lo procesa otra vez (no se paga dos veces)", async () => {
    let abrir!: () => void;
    const puerta = new Promise<void>((r) => (abrir = r));
    let transcripciones = 0;
    const m = nube({
      transcribir: async () => {
        transcripciones++;
        await puerta;
        return "busco una cama queen";
      },
    });
    Object.assign(m.canal, { descargar: async () => ({ bytes: new Uint8Array([1]), mime: "audio/ogg" }) });
    const e = m.entrante(undefined, { adjuntos: [{ tipo: "audio", mime: "audio/ogg", ref: "M7" }] });
    await m.motor.guardarRecibido(e);
    const alarma = m.pasar(RESCATE + 1000); // el rescate se queda transcribiendo
    for (let i = 0; i < 50; i++) await new Promise((r) => setTimeout(r, 0));
    expect((await m.motor.ingest({ ...e, adjuntos: [{ tipo: "audio", mime: "audio/ogg", bytes: new Uint8Array([1]) }] })).accion).toBe("duplicado");
    abrir();
    await alarma;
    await m.pasar(20_000);
    expect(transcripciones).toBe(1);
    expect(m.canal.salidas).toHaveLength(1);
  });
});
